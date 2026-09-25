"""Durable provider operation coordinator shared by workflows and direct SDK calls."""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from . import codec
from .artifacts import (
    Artifact,
    ArtifactError,
    ArtifactHandle,
    ArtifactMap,
    ArtifactStore,
)
from .errors import (
    BudgetExceeded,
    CancellationRequested,
    UncertainOperation,
)
from .locks import session_lock
from .models import Result, StreamEvent
from .policy import Policy, SandboxMode
from .prompts import Prompt
from .provider_checkpoints import (
    EmptyCheckpoint,
    IntentCheckpoint,
    NotDispatchedCheckpoint,
    ProviderCheckpoint,
    ProviderLifecycle,
    RecoveryAction,
    RespondedCheckpoint,
    RetryAuthorizedCheckpoint,
    ValidatedCheckpoint,
    ValidationFailedCheckpoint,
)
from .providers import (
    ProviderPolicyError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
)
from .recovery import Stopped, recover_outcome
from .runtime import _cancellation_event, current_run
from .session_bindings import SessionBinding


class OutputValidationError(ValueError):
    """A completed turn did not satisfy its declared output type."""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def execute_provider_operation(
    session,
    prompt,
    *,
    input=None,
    reads=(),
    writes=(),
    returns=str,
    policy=None,
    name=None,
    output_retries=2,
    retry_safe=True,
    workspace=None,
    operation="run",
    instructions=None,
    settings=None,
    tools=(),
    timeout=None,
    on_event=None,
):
    ctx = current_run()
    event_callback = _best_effort(on_event)
    if (
        not isinstance(output_retries, int)
        or isinstance(output_retries, bool)
        or output_retries < 0
    ):
        raise ValueError("output_retries must be a nonnegative integer")
    effective = Policy.resolve(ctx.policy, policy).effective()
    if operation in {"query", "generate"}:
        effective = effective.merged(
            {"sandbox_mode": "read_only", "network": "none"}
        ).effective()
    elif operation != "run":
        raise ValueError(f"unknown provider operation: {operation}")
    session_key = session.bind(ctx) if session is not None else None
    target = Path(workspace).resolve() if workspace is not None else ctx.workspace
    if not target.is_dir():
        raise ValueError(f"Provider workspace is not a directory: {target}")
    if isinstance(writes, Artifact):
        writes = (writes,)
    writes = tuple(writes)
    if not all(isinstance(item, Artifact) for item in writes):
        raise TypeError("writes must contain Artifact declarations")
    if writes and effective.sandbox_mode == SandboxMode.READ_ONLY:
        raise ProviderPolicyError(
            "read_only cannot declare output artifacts; use run with a writable sandbox"
        )
    store = ArtifactStore(
        ctx.folder,
        workspace=target,
        allowed_roots=(ctx.task_folder,),
        forbidden_paths=ctx.client.protected_paths(ctx.folder),
        state_dir=ctx.client.state_dir,
    )
    read_store = ArtifactStore(
        ctx.folder,
        workspace=ctx.workspace,
        forbidden_paths=ctx.client.protected_paths(ctx.folder),
        state_dir=ctx.client.state_dir,
    )
    if isinstance(reads, ArtifactHandle):
        reads = (reads,)
    elif isinstance(reads, ArtifactMap):
        reads = tuple(reads.values())
    elif isinstance(reads, (str, Path)):
        reads = (reads,)
    handles = []
    for read in reads:
        if isinstance(read, ArtifactHandle):
            read.read_bytes()
            handles.append(read)
        else:
            path = Path(read)
            path = path if path.is_absolute() else ctx.workspace / path
            path = Path(os.path.abspath(path))

            def snapshot(path=path):
                recovered = read_store.published(ctx.operation_id)
                if recovered is not None:
                    return recovered
                observed = path.resolve()
                allowed_root = next(
                    (
                        root
                        for root in (ctx.workspace, ctx.task_folder)
                        if observed.is_relative_to(root)
                    ),
                    None,
                )
                if allowed_root is None or not observed.is_file():
                    raise ArtifactError(
                        f"Read path must be in the workspace or task artifacts: {path}"
                    )
                source_store = ArtifactStore(
                    ctx.folder,
                    workspace=allowed_root,
                    forbidden_paths=ctx.client.protected_paths(ctx.folder),
                    state_dir=ctx.client.state_dir,
                )
                return source_store.publish(
                    Artifact.raw(observed, name=path.stem),
                    observed.read_bytes(),
                    ctx.operation_id,
                )

            handles.append(
                ctx.operation("read", {"path": str(path)}, snapshot, retry_safe=True)
            )
    rendered = (
        prompt if isinstance(prompt, Prompt) else Prompt.inline(str(prompt))
    ).render(input)
    schema = None if returns is str else codec.schema_for(returns)
    wait_timeout = timeout if timeout is not None else ctx.limits.timeout
    cancellation = _cancellation_event()
    lock = (
        session_lock(
            ctx.journal.path,
            session_key,
            timeout=wait_timeout,
            cancellation=cancellation,
        )
        if session is not None
        else nullcontext()
    )
    lock.__enter__()
    if cancellation is not None and cancellation.is_set():
        lock.__exit__(None, None, None)
        raise CancellationRequested("Cancelled while waiting for the session")
    operation_key = f"{ctx.run_id}:{ctx.scope}:{ctx.ordinal}"
    binding_store = SessionBinding(ctx.journal, session_key) if session_key else None

    def finish_owner(operation_id: str, attempt_number: int, *, abort=False) -> None:
        release = getattr(ctx.client.provider, "release_operation", None)
        if not callable(release):
            return
        durable = ctx.journal.attempt(operation_id, attempt_number)
        if durable is None:
            release(operation_key, require_owner=False, abort=abort)
            return
        field = "cleanup" if abort else "disposal"
        state = durable.get(field) or {}
        cleanup = durable.get("cleanup") or {}
        disposal = durable.get("disposal") or {}
        resolved = (
            state.get("resolved_by") == "operator"
            or cleanup.get("resolved_by") == "operator"
        )
        confirmed = disposal.get("status") == "completed" and (
            not abort or cleanup.get("status") == "completed"
        )
        try:
            if not confirmed and not resolved:
                ctx.journal.attempt_checkpoint(
                    operation_id, attempt_number,
                    {field: {"status": "pending"}, "disposal": {"status": "pending"}},
                )
            # A durable exit proof permits replay without a live adapter. Any
            # locally retained owner still has to be released before settlement.
            release(
                operation_key,
                require_owner=(
                    not (confirmed or resolved)
                    and bool(disposal or durable.get("dispatch_authorized"))
                ),
                abort=abort,
            )
            if not resolved and not confirmed:
                ctx.journal.attempt_checkpoint(
                    operation_id, attempt_number,
                    {field: {"status": "completed"}, "disposal": {"status": "completed"}},
                )
        except Exception as exc:
            if resolved:
                # The recorded operator choice accepted this uncertainty. A
                # best-effort local release does not replace it with exit proof.
                return
            try:
                ctx.journal.attempt_checkpoint(
                    operation_id, attempt_number,
                    {
                        field: {"status": "incomplete", "error": str(exc)},
                        "disposal": {"status": "incomplete", "error": str(exc)},
                    },
                )
            except Exception as checkpoint_error:
                raise UncertainOperation(
                    f"Codex {field} failed and its state could not be recorded",
                    operation_id,
                ) from checkpoint_error
            raise UncertainOperation(
                f"Codex {field} is unverified: {exc}", operation_id,
            ) from exc
    def can_repair(safe: bool) -> bool:
        if safe:
            return True
        following = ctx.journal.get(f"{ctx.run_id}:{ctx.scope}:{ctx.ordinal}")
        return following is not None and not isinstance(
            ProviderCheckpoint.from_record(following.get("response")), EmptyCheckpoint,
        )

    try:
        feedback = None
        repair_usage = {}
        repair_thread_id = None
        retained_owner = None
        for attempt in range(output_retries + 1):
            inputs = {
                "operation_key": operation_key,
                "session": session_key,
                "prompt": rendered,
                "input": input,
                "reads": handles,
                "writes": [a.to_record() for a in writes],
                "schema": schema,
                "policy": effective.to_dict(),
                "workspace": str(target),
                "attempt": attempt,
                "operation": operation,
                "feedback": feedback,
                "instructions": instructions,
                "settings": dict(settings or {}),
                "tools": None if tools is None else list(tools),
                "timeout": timeout,
                "output_retries": output_retries,
                "retained_owner": retained_owner,
            }

            def execute(
                recover=False,
                feedback=feedback,
                attempt=attempt,
                repair_thread_id=repair_thread_id,
            ):
                operation_id = ctx.operation_id
                fresh_response = False
                row = ctx.journal.get(operation_id)
                recorded_inputs = codec.decode(row["inputs"])
                allow_retry = (
                    retry_safe
                    and isinstance(recorded_inputs, dict)
                    and recorded_inputs.get("retry_safe") is True
                )
                retained = (
                    recorded_inputs.get("retained_owner")
                    if isinstance(recorded_inputs, dict)
                    else None
                )
                checkpoint = ProviderCheckpoint.from_record(row.get("response"))
                generation = checkpoint.generation
                authorized = isinstance(checkpoint, RetryAuthorizedCheckpoint)
                prior_generation = checkpoint.attempt_generation
                artifact_operation = f"{operation_id}:generation:{prior_generation}"

                def record_not_dispatched(kind: str, error: Exception) -> None:
                    nonlocal checkpoint
                    checkpoint = NotDispatchedCheckpoint(
                        generation,
                        request_data,
                        kind,
                        str(error),
                    )
                    ctx.save_response(operation_id, checkpoint.to_record())

                def finish_retained_owner() -> None:
                    if not isinstance(retained, dict):
                        return
                    retained_operation = retained.get("operation_id")
                    retained_attempt = retained.get("attempt")
                    if (
                        not isinstance(retained_operation, str)
                        or not retained_operation
                        or type(retained_attempt) is not int
                        or retained_attempt < 1
                    ):
                        raise RuntimeError("Recorded repair owner is invalid")
                    finish_owner(retained_operation, retained_attempt, abort=True)
                    if binding_store is not None:
                        binding_store.finish(
                            ctx.run_id,
                            operation_key,
                            operation_id=retained_operation,
                            attempt=retained_attempt,
                            session_id=(
                                retained.get("session_id")
                                if isinstance(retained.get("session_id"), str)
                                else None
                            ),
                            outcome="preflight_failed",
                        )

                def retained_attempt():
                    if not isinstance(retained, dict):
                        return None
                    retained_operation = retained.get("operation_id")
                    retained_attempt_number = retained.get("attempt")
                    if (
                        not isinstance(retained_operation, str)
                        or type(retained_attempt_number) is not int
                    ):
                        return None
                    return ctx.journal.attempt(
                        retained_operation, retained_attempt_number
                    )

                def record_retained_preflight_failure(error: BaseException) -> None:
                    if not isinstance(retained, dict):
                        return
                    retained_operation = retained.get("operation_id")
                    retained_attempt_number = retained.get("attempt")
                    if (
                        not isinstance(retained_operation, str)
                        or type(retained_attempt_number) is not int
                    ):
                        return
                    kind = (
                        "provider_timeout"
                        if isinstance(error, ProviderTimeoutError)
                        else "artifact_error"
                        if isinstance(error, ArtifactError)
                        else "os_error"
                        if isinstance(error, OSError)
                        else "error"
                    )
                    ctx.journal.attempt_checkpoint(
                        retained_operation,
                        retained_attempt_number,
                        {
                            "repair_preflight_failure": {
                                "kind": kind,
                                "error": str(error),
                            }
                        },
                    )

                def raise_retained_preflight_failure(failure: dict[str, Any]) -> None:
                    message = str(failure.get("error") or "Repair preflight failed")
                    kind = failure.get("kind")
                    if kind == "provider_timeout":
                        raise ProviderTimeoutError(message)
                    if kind == "artifact_error":
                        raise ArtifactError(message)
                    if kind == "os_error":
                        raise OSError(message)
                    raise RuntimeError(message)

                retained_durable = retained_attempt()
                retained_failure = (
                    retained_durable.get("repair_preflight_failure")
                    if isinstance(retained_durable, dict)
                    else None
                )
                if isinstance(retained_failure, dict):
                    finish_retained_owner()
                    raise_retained_preflight_failure(retained_failure)

                if isinstance(checkpoint, NotDispatchedCheckpoint):
                    finish_retained_owner()
                    if checkpoint.error_kind == "policy_error":
                        raise ProviderPolicyError(checkpoint.error)
                    raise BudgetExceeded(checkpoint.error)

                if isinstance(checkpoint, ValidationFailedCheckpoint):
                    error = checkpoint.output_error
                    failure = (
                        OutputValidationError if error["retryable"] else TypeError
                    )
                    if not error["retryable"] or attempt == output_retries or not can_repair(allow_retry):
                        finish_owner(operation_id, checkpoint.attempt_generation + 1)
                    raise failure(error["message"])
                if isinstance(checkpoint, ValidatedCheckpoint):
                    try:
                        captured = store.captured(artifact_operation)
                    except (OSError, ArtifactError) as exc:
                        raise UncertainOperation(
                            f"Artifact capture needs recovery: {exc}", operation_id
                        ) from exc
                    if captured is not None:
                        finish_owner(operation_id, checkpoint.attempt_generation + 1)
                        if event_callback is not None:
                            event_callback(
                                StreamEvent(
                                    "replayed", {"operation_id": operation_id}
                                )
                            )
                        return Result(
                            codec.decode(checkpoint.validated_value),
                            captured,
                            checkpoint.response.usage,
                            operation_id,
                            ctx.run_id,
                            checkpoint.response.metadata,
                        )
                fresh_attempt = isinstance(checkpoint, EmptyCheckpoint)
                try:
                    destinations = store.destinations(writes)
                except (OSError, ArtifactError) as exc:
                    if fresh_attempt:
                        record_retained_preflight_failure(exc)
                        finish_retained_owner()
                        raise
                    raise UncertainOperation(
                        f"Artifact destinations need reconciliation: {exc}",
                        operation_id,
                    ) from exc
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
                                }
                                for h in handles
                            ]
                        )
                    )
                if writes:
                    complete_prompt += (
                        "\n\nWrite the declared artifacts to these exact paths. Required files must exist and satisfy their declared schemas when captured:\n"
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
                        "\n\nRepair the previous output contract failure using the current workspace:\n"
                        + feedback
                    )
                try:
                    binding = (
                        binding_store.check(operation_key) if binding_store else {}
                    )
                except Exception as exc:
                    if fresh_attempt:
                        record_retained_preflight_failure(exc)
                        finish_retained_owner()
                    raise
                request_data = checkpoint.request_data or {
                    "operation_key": operation_key,
                    "session_id": (
                        repair_thread_id
                        if session is None
                        else binding.get("session_id")
                    ),
                    "prompt": complete_prompt,
                    "artifacts": {
                        name: str(path) for name, path in destinations.items()
                    },
                    "reads": [str(handle.path) for handle in handles],
                }

                def save_provider_metadata(update):
                    ctx.journal.attempt_checkpoint(operation_id, request.attempt, update)
                    if binding_store is not None and update.get("session_id"):
                        binding_store.advance(operation_key, update["session_id"])

                request = ProviderRequest(
                    operation_id=operation_id,
                    prompt=complete_prompt,
                    workspace=target,
                    session_id=(
                        row.get("thread_id") or request_data.get("session_id")
                    ),
                    output_schema=schema,
                    policy=effective,
                    artifacts=destinations,
                    session_key=session_key,
                    operation_key=operation_key,
                    timeout=(
                        min(ctx.limits.timeout, timeout)
                        if timeout is not None
                        else ctx.limits.timeout
                    ),
                    attempt=prior_generation + 1,
                    reads=tuple(handle.path for handle in handles),
                    preset=operation,
                    tools=None if tools is None else tuple(tools),
                    instructions=instructions,
                    settings=dict(settings or {}),
                    cancel_event=_cancellation_event(),
                    on_event=event_callback,
                    on_checkpoint=save_provider_metadata,
                    checkpoint=ctx.journal.attempt(operation_id, prior_generation + 1),
                )

                def finish_policy_failure(error):
                    if not any(
                        event["event"] == "provider_call_stopped"
                        and event.get("operation_id") == operation_id
                        for event in ctx.journal.events(ctx.run_id)
                    ):
                        ctx.journal.event(ctx.run_id, "provider_call_stopped", {
                            "operation_key": operation_key,
                            "reason": str(error),
                        }, operation_id)
                    finish_owner(operation_id, request.attempt, abort=True)
                    if binding_store is not None:
                        binding_store.finish(
                            ctx.run_id, operation_key, operation_id=operation_id,
                            attempt=request.attempt, outcome="policy_failed",
                        )

                def recover_attempt():
                    # Checkpoints arrive on the transport's reader thread. Read
                    # the durable current attempt rather than the pre-dispatch
                    # snapshot carried by the original request.
                    attempt = ctx.journal.attempt(operation_id, request.attempt)
                    try:
                        return recover_outcome(ctx.client.provider, replace(
                            request, checkpoint=attempt,
                        ))
                    except ProviderPolicyError as error:
                        # Native reconciliation can discover and checkpoint a
                        # policy violation before raising it. Classify only the
                        # resulting durable state, not the recovery input.
                        attempt = ctx.journal.attempt(
                            operation_id, request.attempt
                        )
                        cleanup = (
                            attempt.get("cleanup")
                            if isinstance(attempt, dict)
                            else None
                        )
                        terminal_policy_failure = (
                            isinstance(attempt, dict)
                            and attempt.get("dispatch_authorized") is True
                            and attempt.get("status") == "failed"
                            and attempt.get("policy_error") is True
                            and isinstance(cleanup, dict)
                            and cleanup.get("status") == "completed"
                        )
                        if not terminal_policy_failure:
                            detail = (
                                cleanup.get("error")
                                if isinstance(cleanup, dict)
                                and isinstance(cleanup.get("error"), str)
                                else str(error)
                            )
                            raise UncertainOperation(
                                detail or "Provider policy failure is not confirmed stopped",
                                operation_id,
                            ) from error
                        finish_policy_failure(error)
                        raise

                recovery_outcome = None
                if (
                    recover
                    and not authorized
                    and not fresh_attempt
                    and not isinstance(checkpoint, RespondedCheckpoint)
                ):
                    recovery_outcome = recover_attempt()
                    action = ProviderLifecycle.recovery_action(
                        checkpoint, recovery_outcome
                    )
                    if action is RecoveryAction.USE_RESPONSE:
                        checkpoint = ProviderLifecycle.completed(
                            checkpoint, recovery_outcome.response
                        )
                        ctx.save_response(
                            operation_id,
                            checkpoint.to_record(),
                            session_key=session_key,
                        )
                    elif isinstance(recovery_outcome, Stopped) and allow_retry:
                        if cancellation is not None and cancellation.is_set():
                            raise CancellationRequested(
                                "Cancelled before provider retry"
                            )
                        checkpoint = ProviderLifecycle.authorize_retry(
                            checkpoint, origin="automatic"
                        )
                        ctx.save_response(operation_id, checkpoint.to_record())
                        generation = checkpoint.generation
                        authorized = True
                    else:
                        raise UncertainOperation(
                            recovery_outcome.detail
                            or "Provider intent has no durable response; reconcile before retrying",
                            operation_id,
                        )
                if authorized:
                    # Reconcile before another dispatch: the prior turn may
                    # still be acting or have a completed response to adopt.
                    outcome = recovery_outcome or recover_attempt()
                    action = ProviderLifecycle.recovery_action(checkpoint, outcome)
                    if action is RecoveryAction.USE_RESPONSE:
                        generation = prior_generation
                        checkpoint = ProviderLifecycle.completed(
                            checkpoint, outcome.response
                        )
                        ctx.save_response(
                            operation_id,
                            checkpoint.to_record(),
                            session_key=session_key,
                        )
                    elif action is RecoveryAction.START_RETRY:
                        if (
                            checkpoint.origin == "automatic"
                            and not allow_retry
                        ):
                            raise UncertainOperation(
                                "Automatic provider retry safety was tightened; "
                                "operator reconciliation is required",
                                operation_id,
                            )
                        if cancellation is not None and cancellation.is_set():
                            raise CancellationRequested(
                                "Cancelled before provider retry"
                            )
                        artifact_operation = f"{operation_id}:generation:{generation}"
                        request = replace(
                            request, artifacts=destinations, attempt=generation + 1,
                            checkpoint=ctx.journal.attempt(operation_id, generation + 1),
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
                    if authorized or fresh_attempt or not recover:
                        try:
                            from .budgets import dispatch_timeout_ceiling

                            configured_timeout = min(
                                request.timeout,
                                effective.timeout or request.timeout,
                            )
                            ceiling = dispatch_timeout_ceiling(
                                ctx.client.provider, configured_timeout
                            )
                            request = replace(
                                request, deadline=time.monotonic() + ceiling
                            )
                            _preflight_provider(ctx.client.provider, request)
                            store.destinations(writes, create_parents=True)
                        except ProviderPolicyError as exc:
                            record_not_dispatched("policy_error", exc)
                            finish_retained_owner()
                            raise
                        except BudgetExceeded as exc:
                            record_not_dispatched("budget_error", exc)
                            finish_retained_owner()
                            raise
                        except BaseException as exc:
                            # A repair still owns the server from its preceding
                            # response until every no-dispatch setup step has
                            # succeeded.  Settle that exact durable attempt before
                            # exposing timeouts, filesystem failures, or other
                            # preflight errors.
                            record_retained_preflight_failure(exc)
                            finish_retained_owner()
                            raise
                        checkpoint = IntentCheckpoint(generation, request_data)
                        ctx.save_response(
                            operation_id,
                            checkpoint.to_record(),
                        )
                        ctx.journal.prepare_attempt(operation_id, request.attempt, {
                            **request_data,
                            "prompt": complete_prompt,
                            "operation_key": operation_key,
                            "preset": operation,
                            "policy": effective.to_dict(),
                            "settings": dict(settings or {}),
                            "tools": None if tools is None else list(tools),
                            "output_schema": schema,
                            "workspace": str(target),
                            "instructions": instructions,
                            "timeout": request.timeout,
                        })
                        if binding_store is not None:
                            binding_store.claim(ctx.run_id, operation_key, operation_id, request.attempt)
                        request = replace(request, checkpoint=ctx.journal.attempt(operation_id, request.attempt))
                    dispatched = False
                    try:
                        if not getattr(
                            ctx.client.provider, "_reserves_dispatch", False
                        ):
                            from .dispatches import Dispatch

                            dispatch = Dispatch(ctx.client.provider, request)
                            reserved_deadline = time.monotonic() + dispatch.timeout
                            request = replace(
                                request,
                                timeout=dispatch.timeout,
                                deadline=min(
                                    request.deadline
                                    if request.deadline is not None
                                    else reserved_deadline,
                                    reserved_deadline,
                                ),
                            )
                            dispatched = True
                            dispatch.started()
                            try:
                                response = _start_turn(
                                    ctx.client.provider, request, event_callback
                                )
                                if not isinstance(response, ProviderResponse):
                                    raise TypeError(
                                        "Provider returned an invalid response object"
                                    )
                                response.to_record()
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
                                "completed"
                                if isinstance(response, ProviderResponse)
                                else "failed",
                                usage=getattr(response, "usage", None),
                            )
                        else:
                            try:
                                response = _start_turn(
                                    ctx.client.provider, request, event_callback
                                )
                            finally:
                                durable_attempt = ctx.journal.attempt(
                                    operation_id, request.attempt
                                )
                                dispatched = (
                                    isinstance(durable_attempt, dict)
                                    and durable_attempt.get("dispatch_authorized")
                                    is True
                                )
                        fresh_response = True
                    except BudgetExceeded as exc:
                        if not dispatched:
                            record_not_dispatched("budget_error", exc)
                        else:
                            raise UncertainOperation(
                                str(exc), operation_id
                            ) from exc
                        raise
                    except ProviderPolicyError as exc:
                        if dispatched:
                            policy_outcome = recover_attempt()
                            if isinstance(policy_outcome, Stopped):
                                finish_policy_failure(exc)
                                raise
                            raise UncertainOperation(
                                policy_outcome.detail or str(exc), operation_id
                            ) from exc
                        record_not_dispatched("policy_error", exc)
                        raise
                    except Exception as exc:
                        raise UncertainOperation(str(exc), operation_id) from exc
                    if not isinstance(response, ProviderResponse):
                        raise UncertainOperation(
                            "Provider returned an invalid response; reconcile its effects",
                            operation_id,
                        )
                    try:
                        response.to_record()
                    except (ValueError, TypeError, RecursionError) as exc:
                        raise UncertainOperation(
                            f"Provider returned an invalid response: {exc}",
                            operation_id,
                        ) from exc
                    ctx.journal.attempt_checkpoint(operation_id, request.attempt, {
                        "status": "completed", "response": response.to_record(),
                    })
                    checkpoint = RespondedCheckpoint(
                        generation, request_data, response
                    )
                    ctx.save_response(
                        operation_id,
                        checkpoint.to_record(),
                        session_key=session_key,
                    )
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
                                value, ArtifactMap(), response.usage, operation_id
                            )
                        )
                        checkpoint = ValidatedCheckpoint(
                            generation=checkpoint.generation,
                            request=checkpoint.request,
                            response=checkpoint.response,
                            artifact_resolution=checkpoint.artifact_resolution,
                            validated_value=value_record,
                        )
                        ctx.save_response(
                            operation_id,
                            checkpoint.to_record(),
                            session_key=session_key,
                        )
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
                    ctx.save_response(
                        operation_id,
                        checkpoint.to_record(),
                        session_key=session_key,
                    )
                    if not retryable or attempt == output_retries or not can_repair(allow_retry):
                        finish_owner(operation_id, request.attempt)
                    if retryable:
                        raise OutputValidationError(str(exc)) from exc
                    raise
                except OSError as exc:
                    raise UncertainOperation(
                        f"Artifact publication is incomplete; resume to finish it: {exc}",
                        operation_id,
                    ) from exc
                finish_owner(operation_id, request.attempt)
                return Result(
                    value,
                    artifacts,
                    response.usage,
                    operation_id,
                    ctx.run_id,
                    response.metadata,
                )

            replay_id = f"{ctx.run_id}:{ctx.scope}:{ctx.ordinal}"
            replay_record = ctx.journal.get(replay_id)
            replaying_completed = (
                replay_record is not None and replay_record.get("status") == "completed"
            )
            try:
                result = ctx.operation(
                    "provider",
                    inputs,
                    execute,
                    retry_safe=retry_safe,
                    recover=lambda: execute(True),
                    name=name,
                )
                if replaying_completed and event_callback is not None:
                    event_callback(
                        StreamEvent("replayed", {"operation_id": result.operation_id})
                    )
                usage = dict(repair_usage)
                for key, value in result.usage.items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        usage[key] = usage.get(key, 0) + value
                    else:
                        usage[key] = value
                if binding_store is not None:
                    final_checkpoint = ProviderCheckpoint.from_record(
                        ctx.journal.get(result.operation_id)["response"]
                    )
                    binding_store.finish(
                        ctx.run_id, operation_key,
                        operation_id=result.operation_id,
                        attempt=final_checkpoint.attempt_generation + 1,
                        session_id=final_checkpoint.response.session_id,
                    )
                return replace(result, usage=usage)
            except OutputValidationError as exc:
                operation_id = f"{ctx.run_id}:{ctx.scope}:{ctx.ordinal - 1}"
                operation_record = ctx.journal.get(operation_id)
                response = operation_record.get("response") or {}
                failed = ProviderCheckpoint.from_record(response)
                if session is None and isinstance(failed, ValidationFailedCheckpoint):
                    # Rebuild call-local continuity on both execution and replay.
                    repair_thread_id = failed.response.session_id
                if isinstance(failed, ValidationFailedCheckpoint):
                    retained_owner = {
                        "operation_id": operation_id,
                        "attempt": failed.attempt_generation + 1,
                        "session_id": failed.response.session_id,
                    }
                for key, value in response.get("usage", {}).items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        repair_usage[key] = repair_usage.get(key, 0) + value
                exc.usage = dict(repair_usage)
                if attempt == output_retries:
                    raise
                recorded_inputs = codec.decode(operation_record["inputs"])
                repair_safe = (
                    retry_safe
                    and isinstance(recorded_inputs, dict)
                    and recorded_inputs.get("retry_safe") is True
                )
                if not can_repair(repair_safe):
                    raise
                feedback = str(exc)
    except Exception as exc:
        # A known terminal response may fail its schema or exhaust repairs.
        # Uncertain effects keep ownership until resume/operator resolution.
        if not isinstance(exc, (UncertainOperation, CancellationRequested)):
            current = ctx.journal.get(f"{ctx.run_id}:{ctx.scope}:{ctx.ordinal - 1}")
            if current is not None and current.get("status") == "failed":
                state = ProviderCheckpoint.from_record(current.get("response"))
                if isinstance(state, (RespondedCheckpoint, NotDispatchedCheckpoint)):
                    finish_owner(
                        current["id"], state.attempt_generation + 1,
                        abort=isinstance(state, NotDispatchedCheckpoint),
                    )
                    if binding_store is not None:
                        binding_store.finish(
                            ctx.run_id, operation_key, outcome="failed",
                            operation_id=current["id"], attempt=state.attempt_generation + 1,
                            session_id=state.response.session_id if isinstance(state, RespondedCheckpoint) else None,
                        )
        raise
    finally:
        lock.__exit__(None, None, None)


def _start_turn(
    adapter: Any, request: ProviderRequest, on_event: Any = None
) -> ProviderResponse:
    start = getattr(adapter, "start_turn", None)
    response = (
        start(request, on_event=on_event) if callable(start) else adapter.run(request)
    )
    if not isinstance(response, ProviderResponse):
        raise TypeError("Provider returned an invalid response object")
    return response


def _preflight_provider(adapter: Any, request: ProviderRequest) -> None:
    """Reject unenforceable requests before reserving or dispatching a turn."""
    validate = getattr(adapter, "validate_request", None)
    capabilities = validate(request) if callable(validate) else None
    if capabilities is None:
        probe = getattr(adapter, "probe", None)
        if callable(probe):
            capabilities = probe()
    require = getattr(capabilities, "require", None)
    if callable(require):
        require(request.preset)
    policy = request.policy.effective()
    if (
        policy.sandbox_mode == SandboxMode.DANGER_FULL_ACCESS
        and str(policy.network) != "full"
    ):
        raise ProviderPolicyError("danger-full-access cannot enforce disabled network")


def _best_effort(callback: Any):
    if callback is None:
        return None
    if not callable(callback):
        raise TypeError("on_event must be callable or None")

    def emit(event):
        try:
            callback(event)
        except Exception:  # noqa: BLE001, S110 - callbacks are observational
            pass

    return emit
