"""One coordinator for direct and workflow provider operations."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, TypeVar, overload

from pydantic import TypeAdapter

from . import codec
from .artifacts import (
    Artifact,
    ArtifactError,
    ArtifactHandle,
    ArtifactMap,
    ArtifactStore,
)
from .errors import BotpipeError, BudgetExceeded, UncertainOperation
from .models import Result
from .policy import Policy, SandboxMode
from .prompts import Prompt
from .providers import (
    ProviderPolicyError,
    ProviderRequest,
    ProviderTimeoutError,
    provider_request_from_snapshot,
    provider_request_snapshot,
)
from .provider_checkpoints import (
    EmptyCheckpoint,
    IntentCheckpoint,
    NotDispatchedCheckpoint,
    PreparingCheckpoint,
    ProviderCheckpoint,
    ProviderCheckpointError,
    ProviderLifecycle,
    RecoveryAction,
    RespondedCheckpoint,
    RetryAuthorizedCheckpoint,
    ValidatedCheckpoint,
    ValidationFailedCheckpoint,
    canonical_provider_response,
    provider_attempt_identity,
    provider_recovery_outcome,
)
from .runtime import current_run
from .recovery import Completed, Unknown, cancellation_evidence, recover_outcome

T = TypeVar("T")


class OutputValidationError(ValueError):
    """The completed provider turn did not satisfy its output contract."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def execute_provider(
    adapter, session, prompt, *, input=None, reads=(), writes=(), returns=str,
    policy=None, name=None, output_retries=2, workspace=None, operation="run",
    instructions=None, settings=None, allow_commands=(), timeout=None,
    affinity=None,
):
    """Prepare, journal, dispatch, validate and capture one provider invocation."""
    ctx = current_run()
    ctx.check_replay_fence()
    if operation not in {"generate", "query", "run"}:
        raise ValueError(f"Unknown provider operation: {operation}")
    if operation != "run" and writes:
        raise TypeError(f"{operation} cannot declare provider-written artifacts")
    if not isinstance(output_retries, int) or isinstance(output_retries, bool) or output_retries < 0:
        raise ValueError("output_retries must be a nonnegative integer")
    authored_policy = Policy.resolve(ctx.policy, policy)
    effective = authored_policy.effective()
    if operation != "run":
        effective = effective.restrict_read_only()
    target = Path(workspace).resolve() if workspace is not None else ctx.workspace
    if not target.is_dir():
        raise ValueError(f"Provider workspace is not a directory: {target}")
    semantic_affinity = dict(affinity or {})
    semantic_affinity["model"] = effective.model
    capabilities = getattr(adapter, "capabilities", None)
    adapter_version = getattr(capabilities, "version", None)
    if adapter_version is not None:
        semantic_affinity["adapter_version"] = adapter_version
    native_affinity = getattr(adapter, "session_affinity", None)
    if callable(native_affinity):
        native_affinity = native_affinity()
        if not isinstance(native_affinity, Mapping):
            raise TypeError("adapter session_affinity() must return a mapping")
        semantic_affinity["native"] = dict(native_affinity)
    session_key = (
        session.bind(ctx, adapter.name, target, affinity=semantic_affinity)
        if session is not None
        else None
    )
    if (
        ctx.parallel_branch
        and effective.sandbox_mode != SandboxMode.READ_ONLY
        and target == ctx.workspace
    ):
        raise BotpipeError(
            "Parallel editing requires a separate workspace= for each branch; use read_only for shared-workspace reviews"
        )
    if isinstance(writes, Artifact):
        writes = (writes,)
    writes = tuple(writes)
    if not all(isinstance(item, Artifact) for item in writes):
        raise TypeError("writes must contain Artifact declarations")
    if writes and effective.sandbox_mode == SandboxMode.READ_ONLY:
        raise ProviderPolicyError(
            "read_only cannot create artifacts; use a writable isolated workspace for parallel outputs"
        )
    store = ArtifactStore(
        ctx.folder,
        workspace=target,
        forbidden_paths=(
            ctx.client.journal.path,
            ctx.workspace / ".botpipe-workspace.lock",
            target / ".botpipe-workspace.lock",
        ),
    )
    read_store = ArtifactStore(
        ctx.folder,
        workspace=target,
        forbidden_paths=(
            ctx.client.journal.path,
            ctx.workspace / ".botpipe-workspace.lock",
            target / ".botpipe-workspace.lock",
        ),
    )
    root_read_store = ArtifactStore(
        ctx.folder,
        workspace=ctx.workspace,
        forbidden_paths=(
            ctx.client.journal.path,
            ctx.workspace / ".botpipe-workspace.lock",
        ),
    )
    if isinstance(reads, ArtifactHandle):
        reads = (reads,)
    elif isinstance(reads, ArtifactMap):
        reads = tuple(reads.values())
    elif isinstance(reads, (str, Path)):
        reads = (reads,)
    rendered = (
        prompt if isinstance(prompt, Prompt) else Prompt.inline(str(prompt))
    ).render(input)
    schema = None if returns is str else codec.schema_for(returns)
    with ctx._guard:
        lock = ctx._session_locks.setdefault(session_key, threading.Lock()) if session_key is not None else threading.Lock()
        workspace_lock = ctx._workspace_locks.setdefault(
            str(target), threading.Lock()
        )
    if not lock.acquire(blocking=False):
        raise BotpipeError(
            "Concurrent calls cannot share one mutable Session; use separate sessions"
        )
    acquired_workspace = False
    target_ownership = ExitStack()
    target_lease = None
    provider_operation_id = None
    try:
        if ctx.parallel_branch and effective.sandbox_mode != SandboxMode.READ_ONLY:
            acquired_workspace = workspace_lock.acquire(blocking=False)
            if not acquired_workspace:
                raise BotpipeError(
                    "Concurrent editing branches cannot share a workspace"
                )
        def ensure_target_fence(checkpoint):
            nonlocal target_lease
            if target_lease is not None:
                target_lease.validate()
                return
            request_data = checkpoint.request_data
            claim_operation = operation
            claim_policy = effective
            if request_data is not None:
                claim_operation = request_data["operation"]
                claim_policy = Policy.from_dict(request_data["policy"]).effective()
            read_claim = (
                claim_operation in {"query", "generate"}
                or claim_policy.sandbox_mode == SandboxMode.READ_ONLY
            )
            if read_claim:
                context = ctx.client._read_ownership(
                    ctx.run_id, workspace=target, parent=ctx.workspace_leases,
                    operation_id=provider_operation_id, recovery=True,
                )
            else:
                context = ctx.client._ownership(
                    ctx.run_id, workspace=target, parent=ctx.workspace_leases,
                    recovery=True, operation_id=provider_operation_id,
                )
            target_lease = target_ownership.enter_context(context)

        def dynamic_read_fence(directory):
            parents = ctx.workspace_leases
            if target_lease is not None:
                parents = (*parents, target_lease)
            return ctx.client._read_ownership(
                ctx.run_id, workspace=directory, parent=parents,
                operation_id=provider_operation_id or ctx.operation_id,
            )

        def scope_root(value):
            root = Path(value)
            return (root if root.is_absolute() else target / root).resolve()

        def authorize_live_read(observed, *, absolute_read):
            live_policy = effective.intersect(ctx.current_policy_ceiling)
            explicit_allow = (
                authored_policy.allow_read is not None
                or ctx.current_policy_ceiling.allow_read is not None
            )
            allowed = (
                any(
                    observed == root or observed.is_relative_to(root)
                    for root in map(scope_root, live_policy.allow_read or ())
                )
                if explicit_allow
                else (
                    observed.is_relative_to(target)
                    or (
                        absolute_read
                        and observed.is_relative_to(ctx.workspace)
                    )
                )
            )
            denied = any(
                observed == root or observed.is_relative_to(root)
                for root in map(scope_root, live_policy.deny_read or ())
            )
            if not allowed or denied:
                reason = "deny_read" if denied else "allow_read"
                raise ProviderPolicyError(
                    f"Raw read path is outside the effective {reason} scope: {observed}"
                )

        handles = []
        for read in reads:
            if isinstance(read, ArtifactHandle):
                read.read_bytes()
                handles.append(read)
                continue
            path = Path(read)
            absolute_read = path.is_absolute()
            path = path if absolute_read else target / path
            path = Path(os.path.abspath(path))

            def snapshot(path=path, absolute_read=absolute_read):
                source_store = (
                    read_store
                    if path.is_relative_to(target)
                    else root_read_store
                )
                recovered = source_store.published(ctx.operation_id)
                if recovered is not None:
                    return recovered
                observed = path.resolve()
                authorize_live_read(observed, absolute_read=absolute_read)
                if (
                    not (
                        observed.is_relative_to(target)
                        or (
                            absolute_read
                            and observed.is_relative_to(ctx.workspace)
                        )
                    )
                    or not observed.is_file()
                ):
                    raise ArtifactError(
                        f"Read path must be a file in the workspace: {path}"
                    )
                with dynamic_read_fence(observed.parent) as lease:
                    content = observed.read_bytes()
                    lease.validate()
                    return source_store.publish(
                        Artifact.raw(observed, name=path.stem),
                        content,
                        ctx.operation_id,
                    )

            handles.append(
                ctx.operation(
                    "read", {"path": str(path)}, snapshot, retry_safe=True
                )
            )

        inputs = {
            "session": session_key,
            "operation": operation,
            "provider": adapter.name,
            "provider_config": semantic_affinity.get("provider_config", {}),
            "provider_profile": semantic_affinity.get("profile"),
            "adapter_version": adapter_version,
            "instructions": instructions,
            "settings": dict(settings or {}),
            "allow_commands": [list(argv) for argv in allow_commands],
            "prompt": rendered,
            "input": input,
            "reads": handles,
            "writes": [a.to_record() for a in writes],
            "schema": schema,
            "policy": effective.to_dict(),
            "workspace": str(target),
            "output_retries": output_retries,
        }

        def execute_attempt(recover=False):
            nonlocal provider_operation_id
            operation_id = provider_operation_id = ctx.operation_id
            fresh_response = False
            row = ctx.journal.get(operation_id)
            checkpoint = ProviderCheckpoint.from_record(row.get("response"))
            # The operation is durable before admission. Durable request facts,
            # when present, select the recovered claim rather than current policy.
            ensure_target_fence(checkpoint)
            generation = checkpoint.generation
            authorized = isinstance(checkpoint, RetryAuthorizedCheckpoint)

            def save_terminal(terminal_checkpoint):
                saved = ctx.journal.get(operation_id)
                saved_checkpoint = ProviderCheckpoint.from_record(
                    saved.get("response")
                )
                update = None
                if session is not None and not isinstance(
                    saved_checkpoint, RespondedCheckpoint
                ):
                    update = session.advancement(terminal_checkpoint.response.session_id)
                ctx.save_response(operation_id, terminal_checkpoint.to_record(), session_update=update)
                if session is not None:
                    session.advanced(ctx.journal.get(operation_id)["session_revision"])

            prepared_generation = checkpoint.attempt_generation
            artifact_operation = (
                f"{operation_id}:generation:{prepared_generation}"
            )

            def rollback():
                try:
                    store.rollback(artifact_operation)
                except (OSError, ArtifactError) as exc:
                    raise UncertainOperation(
                        f"Artifact rollback is incomplete; resume after resolving the conflict: {exc}",
                        operation_id,
                    ) from exc

            def restore():
                try:
                    store.restore(artifact_operation)
                except (OSError, ArtifactError) as exc:
                    raise UncertainOperation(
                        f"Artifact restoration is incomplete; resume after resolving the conflict: {exc}",
                        operation_id,
                    ) from exc
                nonlocal checkpoint
                if (
                    isinstance(checkpoint, NotDispatchedCheckpoint)
                    and checkpoint.restoration_pending
                ):
                    checkpoint = replace(checkpoint, restoration_pending=False)
                    ctx.save_response(operation_id, checkpoint.to_record())

            if isinstance(checkpoint, NotDispatchedCheckpoint):
                if checkpoint.restoration_pending:
                    restore()
                if checkpoint.error_kind == "policy_error":
                    raise ProviderPolicyError(checkpoint.error)
                if checkpoint.error_kind == "budget_error":
                    raise BudgetExceeded(checkpoint.error)
                if ctx.journal.run(ctx.run_id).get("cancel_requested_at") is not None:
                    raise UncertainOperation(checkpoint.error, operation_id)
                feedback = (
                    checkpoint.repairs[-1].get("output_error", {}).get("message")
                    if checkpoint.repairs
                    else None
                )
                checkpoint = PreparingCheckpoint(
                    checkpoint.generation,
                    feedback,
                    repairs=checkpoint.repairs,
                )
                ctx.save_response(operation_id, checkpoint.to_record())

            if isinstance(checkpoint, ValidationFailedCheckpoint):
                # The provider completed, then validation failed. Finish
                # an interrupted rollback before replaying that failure.
                rollback()
                error = checkpoint.output_error
                failure = (
                    OutputValidationError if error["retryable"] else TypeError
                )
                raise failure(error["message"])
            if isinstance(checkpoint, ValidatedCheckpoint):
                try:
                    captured = store.captured(artifact_operation)
                except (OSError, ArtifactError) as exc:
                    raise UncertainOperation(
                        f"Artifact capture needs recovery: {exc}", operation_id
                    ) from exc
                if captured is not None:
                    return Result(
                        codec.decode(checkpoint.validated_value),
                        captured,
                        combined_usage(checkpoint),
                        operation_id,
                        run_id=ctx.run_id,
                        metadata=checkpoint.response.metadata,
                    )
            preparing = isinstance(
                checkpoint, (EmptyCheckpoint, PreparingCheckpoint)
            )
            feedback = (
                checkpoint.feedback
                if isinstance(checkpoint, PreparingCheckpoint)
                else None
            )
            try:
                destinations = store.destinations(writes)
            except (OSError, ArtifactError) as exc:
                if not isinstance(checkpoint, EmptyCheckpoint):
                    raise UncertainOperation(
                        f"Artifact destinations changed during an unfinished operation: {exc}",
                        operation_id,
                    ) from exc
                raise
            complete_prompt = rendered
            if input is not None:
                serial = (
                    input.model_dump(mode="json")
                    if hasattr(input, "model_dump")
                    else input
                )
                complete_prompt += "\n\nInput:\n" + _json(serial)
            if handles:
                complete_prompt += (
                    "\n\nRead these immutable input artifacts:\n"
                    + _json(
                        [
                            {
                                "name": h.name,
                                "path": str(h.path),
                                "kind": h.kind,
                                "content": h.read_bytes().decode(
                                    "utf-8", errors="replace"
                                ),
                            }
                            for h in handles
                        ]
                    )
                )
            if writes:
                complete_prompt += (
                    "\n\nWrite the declared artifacts to these exact paths. Required files must be created in this turn:\n"
                    + _json(
                        [
                            {**a.to_record(), "path": str(destinations[a.name])}
                            for a in writes
                        ]
                    )
                )
            if schema is not None:
                complete_prompt += (
                    "\n\nReturn only JSON matching this schema:\n"
                    + _json(schema)
                )
            if feedback:
                complete_prompt += (
                    "\n\nRepair the previous output contract failure and produce all required files again:\n"
                    + feedback
                )
            binding = ctx.journal.session(session_key) or {}
            request_timeout = (
                min(ctx.limits.timeout, timeout)
                if timeout is not None
                else ctx.limits.timeout
            )
            request_data = checkpoint.request_data
            if request_data is None:
                request = ProviderRequest(
                    operation=operation,
                    instructions=instructions,
                    settings=dict(settings or {}),
                    allow_commands=allow_commands,
                    operation_id=operation_id,
                    prompt=complete_prompt,
                    workspace=target,
                    session_id=binding.get("native_session_id"),
                    output_schema=schema,
                    policy=effective,
                    artifacts=destinations,
                    receipt_dir=ctx.folder / "receipts",
                    timeout=request_timeout,
                    attempt=prepared_generation + 1,
                    reads=tuple(handle.path for handle in handles),
                    read_fence=dynamic_read_fence,
                )
                request_data = provider_request_snapshot(
                    request, provider=adapter.name
                )
                request = provider_request_from_snapshot(
                    request_data,
                    operation_id=operation_id,
                    workspace=target,
                    output_schema=schema,
                    timeout=request_timeout,
                    attempt=prepared_generation + 1,
                    provider=adapter.name,
                    read_fence=dynamic_read_fence,
                )
            else:
                request = provider_request_from_snapshot(
                    request_data,
                    operation_id=operation_id,
                    workspace=target,
                    output_schema=schema,
                    timeout=request_timeout,
                    attempt=prepared_generation + 1,
                    provider=adapter.name,
                    read_fence=dynamic_read_fence,
                )

            def recorded_recovery():
                evidence = cancellation_evidence(
                    ctx.journal.events(ctx.run_id),
                    operation_id=operation_id,
                    identity=provider_attempt_identity(checkpoint),
                )
                outcome = (
                    evidence
                    if evidence is not None
                    else recover_outcome(adapter, request)
                )
                return provider_recovery_outcome(outcome)

            evidence = cancellation_evidence(
                ctx.journal.events(ctx.run_id),
                operation_id=operation_id,
                identity=provider_attempt_identity(checkpoint),
            )
            if isinstance(evidence, Unknown):
                raise UncertainOperation(evidence.detail, operation_id)
            if (
                isinstance(evidence, Completed)
                and isinstance(checkpoint, RespondedCheckpoint)
                and evidence.response.to_record() != checkpoint.response.to_record()
            ):
                raise UncertainOperation(
                    "Cancellation evidence conflicts with the provider checkpoint",
                    operation_id,
                )

            recovery_outcome = None
            if (
                recover
                and not isinstance(checkpoint, RespondedCheckpoint)
                and (authorized or not preparing)
            ):
                # Validate recovered terminal evidence before claiming a
                # session or preparing/restoring any artifact destination.
                recovery_outcome = recorded_recovery()
                early_action = ProviderLifecycle.recovery_action(
                    checkpoint, recovery_outcome
                )
                if authorized:
                    if early_action not in {
                        RecoveryAction.USE_RESPONSE,
                        RecoveryAction.START_RETRY,
                    }:
                        raise UncertainOperation(
                            recovery_outcome.detail
                            or "Provider is not confirmed stopped; retry is blocked",
                            operation_id,
                        )
                elif early_action is not RecoveryAction.USE_RESPONSE:
                    raise UncertainOperation(
                        recovery_outcome.detail
                        or "Provider intent has no durable response; reconcile before retrying",
                        operation_id,
                    )

            def preflight_new_dispatch(request):
                nonlocal request_data
                from .streaming import require_live_capability

                dispatch_policy = effective.intersect(ctx.current_policy_ceiling)
                request = replace(request, policy=dispatch_policy)
                request_data = provider_request_snapshot(
                    request, provider=adapter.name
                )
                require_live_capability(adapter)
                adapter.validate_request(request)
                return request

            def save_cancelled(exc, *, release_session=False):
                nonlocal checkpoint
                checkpoint = NotDispatchedCheckpoint(
                    generation,
                    request_data,
                    False,
                    "cancellation_error",
                    str(exc),
                    repairs=checkpoint.repairs,
                )
                ctx.save_response(operation_id, checkpoint.to_record())
                if release_session and session is not None:
                    session.release(ctx, operation_id)
                raise exc

            if not recover or preparing:
                try:
                    request = preflight_new_dispatch(request)
                    ctx.check_cancelled()
                except UncertainOperation as exc:
                    save_cancelled(exc)
                except ProviderPolicyError:
                    if isinstance(checkpoint, PreparingCheckpoint):
                        restore()
                    raise
            terminal = isinstance(checkpoint, RespondedCheckpoint)
            if session is not None and not terminal:
                lease = session.claim(ctx, operation_id)
                if not checkpoint.request_data:
                    request = replace(request, session_id=lease.native_session_id)
                    request_data = provider_request_snapshot(
                        request, provider=adapter.name
                    )
            if isinstance(checkpoint, EmptyCheckpoint):
                # Validate paths before any destination can move. This
                # marker proves a resumed preparation has not dispatched.
                store.destinations(writes)
                checkpoint = PreparingCheckpoint(
                    generation, repairs=checkpoint.repairs
                )
                ctx.save_response(operation_id, checkpoint.to_record())
            try:
                destinations = (
                    store.destinations(writes)
                    if authorized
                    else store.prepare(writes, artifact_operation)
                )
            except (OSError, ArtifactError) as exc:
                raise UncertainOperation(
                    f"Artifact preparation is incomplete; resume after resolving the conflict: {exc}",
                    operation_id,
                ) from exc
            if authorized:
                # Reconcile before touching destinations: the previous
                # process may still be writing them, or its completed
                # response may already be recoverable from a receipt.
                outcome = recovery_outcome
                assert outcome is not None
                action = ProviderLifecycle.recovery_action(checkpoint, outcome)
                if action is RecoveryAction.USE_RESPONSE:
                    generation = prepared_generation
                    checkpoint = ProviderLifecycle.completed(
                        checkpoint, outcome.response
                    )
                    save_terminal(checkpoint)
                elif action is RecoveryAction.START_RETRY:
                    rollback()
                    artifact_operation = (
                        f"{operation_id}:generation:{generation}"
                    )
                    try:
                        request = preflight_new_dispatch(request)
                        ctx.check_cancelled()
                        destinations = store.prepare(writes, artifact_operation)
                    except UncertainOperation as exc:
                        save_cancelled(exc, release_session=True)
                    except ProviderPolicyError as exc:
                        checkpoint = NotDispatchedCheckpoint(
                            generation,
                            request_data,
                            False,
                            "policy_error",
                            str(exc),
                            repairs=checkpoint.repairs,
                        )
                        ctx.save_response(operation_id, checkpoint.to_record())
                        if session is not None:
                            session.release(ctx, operation_id)
                        raise
                    except (OSError, ArtifactError) as exc:
                        raise UncertainOperation(
                            f"Artifact preparation is incomplete; resume after resolving the conflict: {exc}",
                            operation_id,
                        ) from exc
                    request = replace(
                        request, artifacts=destinations, attempt=generation + 1
                    )
                    request_data = provider_request_snapshot(
                        request, provider=adapter.name
                    )
                else:
                    raise UncertainOperation(
                        outcome.detail
                        or "Provider is not confirmed stopped; retry is blocked",
                        operation_id,
                    )
            if isinstance(checkpoint, RespondedCheckpoint):
                response = checkpoint.response
            else:
                if authorized or preparing or not recover:
                    checkpoint = IntentCheckpoint(
                        generation,
                        request_data,
                        repairs=checkpoint.repairs,
                    )
                    ctx.save_response(
                        operation_id,
                        checkpoint.to_record(),
                    )
                dispatched = False
                try:
                    if recover and not authorized and not preparing:
                        outcome = recovery_outcome
                        assert outcome is not None
                        action = ProviderLifecycle.recovery_action(
                            checkpoint, outcome
                        )
                        if action is not RecoveryAction.USE_RESPONSE:
                            raise UncertainOperation(
                                outcome.detail
                                or "Provider intent has no durable response; reconcile before retrying",
                                operation_id,
                            )
                        response = outcome.response
                    else:
                        if not getattr(
                            adapter, "_reserves_dispatch", False
                        ):
                            from .dispatches import Dispatch

                            dispatch = Dispatch(adapter, request)
                            request = replace(request, timeout=dispatch.timeout)
                            dispatched = True
                            dispatch.started()
                            try:
                                response = canonical_provider_response(
                                    adapter.run(request)
                                )
                            except BaseException as exc:
                                dispatch.finish(
                                    "timed_out"
                                    if isinstance(exc, ProviderTimeoutError)
                                    else "failed"
                                    if isinstance(exc, Exception)
                                    else "interrupted",
                                    usage=getattr(exc, "usage", None),
                                    error=exc,
                                )
                                raise
                            dispatch.finish(
                                "completed",
                                usage=getattr(response, "usage", None),
                            )
                        else:
                            response = adapter.run(request)
                        fresh_response = True
                except BudgetExceeded as exc:
                    if not dispatched:
                        checkpoint = NotDispatchedCheckpoint(
                            generation,
                            request_data,
                            True,
                            "budget_error",
                            str(exc),
                            repairs=checkpoint.repairs,
                        )
                        ctx.save_response(operation_id, checkpoint.to_record())
                        restore()
                        if session is not None:
                            session.release(ctx, operation_id)
                    else:
                        raise UncertainOperation(
                            str(exc), operation_id
                        ) from exc
                    raise
                except ProviderPolicyError as exc:
                    if dispatched:
                        raise UncertainOperation(
                            str(exc), operation_id
                        ) from exc
                    checkpoint = NotDispatchedCheckpoint(
                        generation,
                        request_data,
                        True,
                        "policy_error",
                        str(exc),
                        repairs=checkpoint.repairs,
                    )
                    ctx.save_response(operation_id, checkpoint.to_record())
                    restore()
                    if session is not None:
                        session.release(ctx, operation_id)
                    raise
                except Exception as exc:
                    raise UncertainOperation(str(exc), operation_id) from exc
                try:
                    response = canonical_provider_response(response)
                except ProviderCheckpointError as exc:
                    raise UncertainOperation(
                        f"Provider returned an invalid response: {exc}",
                        operation_id,
                    ) from exc
                checkpoint = RespondedCheckpoint(
                    generation,
                    request_data,
                    response,
                    repairs=checkpoint.repairs,
                )
                save_terminal(checkpoint)
            try:
                if isinstance(checkpoint, ValidatedCheckpoint):
                    value = codec.decode(checkpoint.validated_value)
                elif returns is str:
                    value = response.text
                else:
                    text = response.text.strip()
                    fenced = re.fullmatch(
                        r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL
                    )
                    value = TypeAdapter(returns).validate_json(
                        fenced.group(1) if fenced else text
                    )
                if not isinstance(checkpoint, ValidatedCheckpoint):
                    # Persist normalized state before capture. Recovery
                    # can finish the same result without rerunning hooks.
                    value_record = codec.encode(value)
                    codec.encode(
                        Result(
                            value, ArtifactMap(), response.usage, operation_id, run_id=ctx.run_id, metadata=response.metadata
                        )
                    )
                    checkpoint = ValidatedCheckpoint(
                        generation=checkpoint.generation,
                        request=checkpoint.request,
                        response=checkpoint.response,
                        artifact_resolution=checkpoint.artifact_resolution,
                        validated_value=value_record,
                        repairs=checkpoint.repairs,
                    )
                    save_terminal(checkpoint)
                artifacts = store.capture(
                    writes,
                    artifact_operation,
                    recover=not fresh_response,
                    expected_digests=(checkpoint.artifact_resolution or {}).get(
                        "digests"
                    ),
                )
            except (ValueError, TypeError) as exc:
                retryable = isinstance(exc, ValueError)
                checkpoint = ProviderLifecycle.validation_failed(
                    checkpoint,
                    message=str(exc),
                    retryable=retryable,
                )
                save_terminal(checkpoint)
                rollback()
                if retryable:
                    raise OutputValidationError(str(exc)) from exc
                raise
            except OSError as exc:
                raise UncertainOperation(
                    f"Artifact publication is incomplete; resume to finish it: {exc}",
                    operation_id,
                ) from exc
            return Result(
                value,
                artifacts,
                combined_usage(checkpoint),
                operation_id,
                run_id=ctx.run_id,
                metadata=response.metadata,
            )

        def combined_usage(checkpoint):
            usage = {}
            attempts = [
                ProviderCheckpoint.from_record(record)
                for record in checkpoint.repairs
            ]
            if isinstance(checkpoint, RespondedCheckpoint):
                attempts.append(checkpoint)
            for completed in attempts:
                for key, value in completed.response.usage.items():
                    if isinstance(value, (int, float)) and not isinstance(
                        value, bool
                    ):
                        usage[key] = usage.get(key, 0) + value
                    else:
                        usage[key] = value
            return usage

        def execute(recover=False):
            while True:
                try:
                    return execute_attempt(recover)
                except OutputValidationError as exc:
                    operation_id = ctx.operation_id
                    saved = ctx.journal.get(operation_id)
                    checkpoint = ProviderCheckpoint.from_record(
                        saved.get("response")
                    )
                    if session is not None and saved.get("session_revision") is not None:
                        session.advanced(saved["session_revision"])
                    exc.usage = combined_usage(checkpoint)
                    if (
                        not isinstance(checkpoint, ValidationFailedCheckpoint)
                        or len(checkpoint.repairs) >= output_retries
                    ):
                        raise
                    attempt_record = checkpoint.to_record()
                    attempt_record.pop("repairs", None)
                    checkpoint = PreparingCheckpoint(
                        checkpoint.generation + 1,
                        str(exc),
                        repairs=(*checkpoint.repairs, attempt_record),
                    )
                    ctx.save_response(operation_id, checkpoint.to_record())
                    recover = False

        result = ctx.operation(
            "provider",
            inputs,
            execute,
            recover=lambda: execute(True),
            name=name,
        )
        if session is not None:
            saved = ctx.journal.get(result.operation_id)
            if saved.get("session_revision") is not None:
                session.advanced(saved["session_revision"])
        return result
    finally:
        target_ownership.close()
        if acquired_workspace:
            workspace_lock.release()
        lock.release()



def execute_decision(
    adapter,
    *,
    state,
    questions,
    settings=None,
    timeout=None,
    name=None,
    provider_config=None,
):
    """Record a native typed decision without a conversation or file transaction."""
    from .dispatches import Dispatch
    from .jev import DecisionRequest, DecisionResponse
    from .providers import CapabilityError
    from .recovery import Completed

    ctx = current_run()
    if not callable(getattr(adapter, "decide", None)):
        raise CapabilityError(f"{adapter.name} does not support typed decisions")
    inputs = {
        "provider": adapter.name,
        "provider_config": dict(provider_config or {}),
        "adapter_version": getattr(
            getattr(adapter, "capabilities", None), "version", None
        ),
        "state": state,
        "questions": questions,
        "settings": dict(settings or {}),
    }

    def execute(recover=False):
        operation_id = ctx.operation_id
        row = ctx.journal.get(operation_id)
        checkpoint = row.get("response") or {}
        if "validated_value" in checkpoint:
            return codec.decode(checkpoint["validated_value"])
        request = DecisionRequest(
            operation_id=operation_id,
            state=state,
            questions=questions,
            receipt_dir=ctx.folder / "receipts",
            timeout=min(ctx.limits.timeout, timeout) if timeout is not None else ctx.limits.timeout,
            settings=dict(settings or {}),
        )
        if checkpoint.get("phase") == "intent":
            outcome = recover_outcome(adapter, request)
            if not isinstance(outcome, Completed):
                raise UncertainOperation(outcome.detail or "Decision outcome is uncertain; reconcile the original attempt", operation_id)
            response = outcome.response
        else:
            adapter.validate_request(request)
            ctx.check_cancelled()
            ctx.save_response(operation_id, {"phase": "intent"})
            dispatch = Dispatch(adapter, request)
            dispatch.started()
            try:
                response = adapter.decide(request)
                if not isinstance(response, DecisionResponse):
                    raise TypeError("Decision adapter returned an invalid response")
                response.to_record()
            except BaseException as exc:
                dispatch.finish("interrupted", error=exc)
                raise UncertainOperation(str(exc), operation_id) from exc
            dispatch.finish("completed", usage=response.usage)
        if not isinstance(response, DecisionResponse):
            raise UncertainOperation("Recovered response is not a typed decision", operation_id)
        response.to_record()
        result = Result(dict(response.answers), ArtifactMap(), dict(response.usage), operation_id, run_id=ctx.run_id, metadata={**response.metadata, "model": response.model})
        ctx.save_response(operation_id, {"phase": "validated", "validated_value": codec.encode(result), "usage": dict(response.usage)})
        return result

    return ctx.operation("decision", inputs, execute, recover=lambda: execute(True), name=name)
