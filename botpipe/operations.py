"""Durable provider operation coordinator shared by workflows and direct SDK calls."""

from __future__ import annotations

import json
import os
import re
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
    BotpipeError,
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
    PreparingCheckpoint,
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
from .recovery import Stopped, Unknown, recover_outcome
from .runtime import _cancellation_event, current_run


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
        allowed_roots=(ctx.task_folder,),
        forbidden_paths=(
            ctx.client.journal.path,
            ctx.workspace / ".botpipe-workspace.lock",
            target / ".botpipe-workspace.lock",
        ),
    )
    read_store = ArtifactStore(
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
                    forbidden_paths=(ctx.client.journal.path,),
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
    try:
        feedback = None
        repair_usage = {}
        for attempt in range(output_retries + 1):
            inputs = {
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
            }

            def execute(recover=False, feedback=feedback):
                operation_id = ctx.operation_id
                fresh_response = False
                row = ctx.journal.get(operation_id)
                checkpoint = ProviderCheckpoint.from_record(row.get("response"))
                generation = checkpoint.generation
                authorized = isinstance(checkpoint, RetryAuthorizedCheckpoint)
                prepared_generation = checkpoint.attempt_generation
                artifact_operation = f"{operation_id}:generation:{prepared_generation}"

                if isinstance(checkpoint, EmptyCheckpoint):
                    store.destinations(writes)
                writable_turn = operation == "run"
                turn_context = (
                    ctx.client.workspace_turn(
                        target,
                        run_id=ctx.run_id,
                        operation_id=operation_id,
                        writable=True,
                        timeout=timeout,
                    )
                    if writable_turn
                    else nullcontext(None)
                )
                with turn_context as turn:
                    if turn is not None:
                        turn.mark_unresolved(operation_id)

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
                        restore()
                        if turn is not None:
                            turn.clear(operation_id)
                        if checkpoint.error_kind == "policy_error":
                            raise ProviderPolicyError(checkpoint.error)
                        raise BudgetExceeded(checkpoint.error)

                    if isinstance(checkpoint, ValidationFailedCheckpoint):
                        if turn is not None:
                            turn.clear(operation_id)
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
                            if turn is not None:
                                turn.clear(operation_id)
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
                    preparing = isinstance(
                        checkpoint, (EmptyCheckpoint, PreparingCheckpoint)
                    )
                    if isinstance(checkpoint, EmptyCheckpoint):
                        # Validate paths before any destination can move. This
                        # marker proves a resumed preparation has not dispatched.
                        store.destinations(writes)
                        checkpoint = PreparingCheckpoint(generation)
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
                    request_data = checkpoint.request_data or {
                        "session_id": binding.get("session_id"),
                        "receipt_dir": str(ctx.folder / "receipts"),
                        "prompt": complete_prompt,
                        "artifacts": {
                            name: str(path) for name, path in destinations.items()
                        },
                        "reads": [str(handle.path) for handle in handles],
                    }

                    def save_provider_metadata(update):
                        ctx.journal.provider_metadata(
                            operation_id,
                            thread_id=update.get("session_id"),
                            turn_id=update.get("turn_id"),
                            preset=update.get("preset"),
                            enforcement=update.get("enforcement"),
                            probe_hash=update.get("probe_hash"),
                        )

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
                        receipt_dir=ctx.folder / "receipts",
                        timeout=(
                            min(ctx.limits.timeout, timeout)
                            if timeout is not None
                            else ctx.limits.timeout
                        ),
                        attempt=prepared_generation + 1,
                        reads=tuple(handle.path for handle in handles),
                        preset=operation,
                        tools=None if tools is None else tuple(tools),
                        instructions=instructions,
                        settings=dict(settings or {}),
                        cancel_event=_cancellation_event(),
                        on_event=event_callback,
                        on_checkpoint=save_provider_metadata,
                    )
                    if authorized:
                        # Reconcile before touching destinations: the previous
                        # process may still be writing them, or its completed
                        # response may already be recoverable from a receipt.
                        outcome = recover_outcome(ctx.client.provider, request)
                        action = ProviderLifecycle.recovery_action(checkpoint, outcome)
                        if action is RecoveryAction.USE_RESPONSE:
                            generation = prepared_generation
                            checkpoint = ProviderLifecycle.completed(
                                checkpoint, outcome.response
                            )
                            ctx.save_response(
                                operation_id,
                                checkpoint.to_record(),
                                session_key=session_key,
                            )
                        elif action is RecoveryAction.START_RETRY:
                            rollback()
                            artifact_operation = (
                                f"{operation_id}:generation:{generation}"
                            )
                            try:
                                destinations = store.prepare(writes, artifact_operation)
                            except (OSError, ArtifactError) as exc:
                                raise UncertainOperation(
                                    f"Artifact preparation is incomplete; resume after resolving the conflict: {exc}",
                                    operation_id,
                                ) from exc
                            request = replace(
                                request, artifacts=destinations, attempt=generation + 1
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
                            try:
                                _preflight_provider(ctx.client.provider, request)
                            except Exception:
                                restore()
                                if turn is not None:
                                    turn.clear(operation_id)
                                raise
                            checkpoint = IntentCheckpoint(generation, request_data)
                            ctx.save_response(
                                operation_id,
                                checkpoint.to_record(),
                            )
                        dispatched = False
                        try:
                            if recover and not authorized and not preparing:
                                outcome = recover_outcome(ctx.client.provider, request)
                                action = ProviderLifecycle.recovery_action(
                                    checkpoint, outcome
                                )
                                if isinstance(
                                    outcome, (Stopped, Unknown)
                                ) and operation in {
                                    "query",
                                    "generate",
                                }:
                                    checkpoint = ProviderLifecycle.authorize_retry(
                                        checkpoint
                                    )
                                    ctx.save_response(
                                        operation_id, checkpoint.to_record()
                                    )
                                    return execute(False)
                                if action is not RecoveryAction.USE_RESPONSE:
                                    raise UncertainOperation(
                                        outcome.detail
                                        or "Provider intent has no durable response; reconcile before retrying",
                                        operation_id,
                                    )
                                response = outcome.response
                            else:
                                if not getattr(
                                    ctx.client.provider, "_reserves_dispatch", False
                                ):
                                    from .dispatches import Dispatch

                                    dispatch = Dispatch(ctx.client.provider, request)
                                    request = replace(request, timeout=dispatch.timeout)
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
                                    response = _start_turn(
                                        ctx.client.provider, request, event_callback
                                    )
                                fresh_response = True
                        except BudgetExceeded as exc:
                            if not dispatched:
                                checkpoint = NotDispatchedCheckpoint(
                                    generation,
                                    request_data,
                                    True,
                                    "budget_error",
                                    str(exc),
                                )
                                ctx.save_response(operation_id, checkpoint.to_record())
                                restore()
                                if turn is not None:
                                    turn.clear(operation_id)
                            else:
                                raise UncertainOperation(
                                    str(exc), operation_id
                                ) from exc
                            raise
                        except ProviderPolicyError as exc:
                            if dispatched:
                                policy_outcome = recover_outcome(
                                    ctx.client.provider, request
                                )
                                if isinstance(policy_outcome, Stopped):
                                    if turn is not None:
                                        turn.clear(operation_id)
                                    raise
                                raise UncertainOperation(
                                    policy_outcome.detail or str(exc), operation_id
                                ) from exc
                            checkpoint = NotDispatchedCheckpoint(
                                generation,
                                request_data,
                                True,
                                "policy_error",
                                str(exc),
                            )
                            ctx.save_response(operation_id, checkpoint.to_record())
                            restore()
                            if turn is not None:
                                turn.clear(operation_id)
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
                        if turn is not None:
                            turn.clear(operation_id)
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
                        if turn is not None:
                            turn.clear(operation_id)
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
                return replace(result, usage=usage)
            except OutputValidationError as exc:
                operation_id = f"{ctx.run_id}:{ctx.scope}:{ctx.ordinal - 1}"
                response = ctx.journal.get(operation_id).get("response") or {}
                for key, value in response.get("usage", {}).items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        repair_usage[key] = repair_usage.get(key, 0) + value
                exc.usage = dict(repair_usage)
                if attempt == output_retries:
                    raise
                feedback = str(exc)
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
    if callable(validate):
        validate(request)
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
