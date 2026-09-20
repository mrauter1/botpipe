"""Durable, typed provider turns using runtime-owned session objects."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from contextlib import ExitStack
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, TypeVar, overload

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
    ProviderError,
    ProviderInterruptedError,
    ProviderPolicyError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
)
from .runtime import _async_call, current_run

T = TypeVar("T")


class OutputValidationError(ValueError):
    """The completed provider turn did not satisfy its output contract."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class Session:
    """An opaque conversation handle; each call is a separate durable operation."""

    def __init__(self, *, key="default", _scope="run", _item=None):
        ctx = current_run()
        if not isinstance(key, str) or not key:
            raise ValueError("Session key must be a nonempty string")
        identity = {
            "scope": _scope,
            "key": key,
            "workflow": ctx.definition.name,
            "task": ctx.task_id,
            "provider": ctx.client.provider_name,
        }
        if _scope == "run":
            identity.update(run=ctx.run_id, scope_path=ctx.scope, ordinal=ctx.ordinal)
        elif _scope == "fresh":
            identity.update(run=ctx.run_id, scope_path=ctx.scope, ordinal=ctx.ordinal)
        elif _scope == "item":
            identity.update(worklist=_item.worklist, item=_item.id)
        self.key = ctx.operation(
            "session",
            identity,
            lambda: hashlib.sha256(codec.dumps(identity).encode()).hexdigest(),
            retry_safe=True,
        )
        self.task_id = ctx.task_id
        self.client = ctx.client

    @classmethod
    def task(cls, key="default"):
        return cls(key=key, _scope="task")

    @classmethod
    def work_item(cls, item, key="default"):
        return cls(key=key, _scope="item", _item=item)

    @classmethod
    def fresh(cls):
        return cls(_scope="fresh")

    @overload
    def run(
        self, prompt: str | Prompt, *, returns: type[T], **kwargs: Any
    ) -> Result[T]: ...

    @overload
    def run(self, prompt: str | Prompt, **kwargs: Any) -> Result[str]: ...

    def run(
        self,
        prompt,
        *,
        input=None,
        reads=(),
        writes=(),
        returns=str,
        policy=None,
        name=None,
        retries=2,
        workspace=None,
    ):
        ctx = current_run()
        if ctx.client is not self.client or ctx.task_id != self.task_id:
            raise BotpipeError(
                "A Session belongs to the task and client that created it"
            )
        if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
            raise ValueError("retries must be a nonnegative integer")
        effective = Policy.resolve(ctx.policy, policy).effective()
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
                    if (
                        not observed.is_relative_to(ctx.workspace)
                        or not observed.is_file()
                    ):
                        raise ArtifactError(
                            f"Read path must be a file in the workspace: {path}"
                        )
                    return read_store.publish(
                        Artifact.raw(observed, name=path.stem),
                        observed.read_bytes(),
                        ctx.operation_id,
                    )

                handles.append(
                    ctx.operation(
                        "read", {"path": str(path)}, snapshot, retry_safe=True
                    )
                )
        rendered = (
            prompt if isinstance(prompt, Prompt) else Prompt.inline(str(prompt))
        ).render(input)
        schema = None if returns is str else codec.schema_for(returns)
        with ctx._guard:
            lock = ctx._session_locks.setdefault(self.key, threading.Lock())
            workspace_lock = ctx._workspace_locks.setdefault(
                str(target), threading.Lock()
            )
        if not lock.acquire(blocking=False):
            raise BotpipeError(
                "Concurrent calls cannot share one mutable Session; use separate sessions"
            )
        acquired_workspace = False
        target_ownership = ExitStack()
        owns_target = False
        try:
            if ctx.parallel_branch and effective.sandbox_mode != SandboxMode.READ_ONLY:
                acquired_workspace = workspace_lock.acquire(blocking=False)
                if not acquired_workspace:
                    raise BotpipeError(
                        "Concurrent editing branches cannot share a workspace"
                    )
            feedback = None
            repair_usage = {}
            for attempt in range(retries + 1):
                inputs = {
                    "session": self.key,
                    "prompt": rendered,
                    "input": input,
                    "reads": handles,
                    "writes": [a.to_record() for a in writes],
                    "schema": schema,
                    "policy": effective.to_dict(),
                    "workspace": str(target),
                    "attempt": attempt,
                    "feedback": feedback,
                }

                def execute(recover=False):
                    operation_id = ctx.operation_id
                    row = ctx.journal.get(operation_id)
                    saved = row.get("response") or {}
                    if saved.get("not_dispatched"):
                        raise BudgetExceeded(
                            saved.get("budget_error", "Provider budget exhausted")
                        )
                    generation = saved.get("generation", 0)
                    authorized = saved.get("retry_authorized", False)
                    prepared_generation = generation - 1 if authorized else generation
                    artifact_operation = (
                        f"{operation_id}:generation:{prepared_generation}"
                    )
                    destinations = store.prepare(writes, artifact_operation)
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
                    binding = ctx.journal.session(self.key) or {}
                    request_data = saved.get("request") or {
                        "session_id": binding.get("session_id"),
                        "receipt_dir": str(ctx.folder / "receipts"),
                    }
                    request = ProviderRequest(
                        operation_id=operation_id,
                        prompt=complete_prompt,
                        workspace=target,
                        session_id=request_data.get("session_id"),
                        output_schema=schema,
                        policy=effective,
                        artifacts=destinations,
                        receipt_dir=ctx.folder / "receipts",
                        timeout=ctx.client.timeout,
                        attempt=prepared_generation + 1,
                        reads=tuple(handle.path for handle in handles),
                    )
                    if authorized:
                        # Reconcile before touching destinations: the previous
                        # process may still be writing them, or its completed
                        # response may already be recoverable from a receipt.
                        recover_fn = getattr(ctx.client.provider, "recover", None)
                        try:
                            recovered = recover_fn(request) if recover_fn else None
                        except ProviderInterruptedError as exc:
                            if exc.process_alive is not False:
                                raise UncertainOperation(
                                    str(exc), operation_id
                                ) from exc
                            recovered = None
                        except ProviderError:
                            recovered = None
                        if recovered is not None:
                            generation = prepared_generation
                            saved = {
                                **asdict(recovered),
                                "request": request_data,
                                "generation": generation,
                            }
                            ctx.journal.response(
                                operation_id, saved, session_key=self.key
                            )
                        else:
                            artifact_operation = (
                                f"{operation_id}:generation:{generation}"
                            )
                            destinations = store.prepare(writes, artifact_operation)
                            request = replace(
                                request, artifacts=destinations, attempt=generation + 1
                            )
                    if "text" in saved:
                        response = ProviderResponse(
                            **{
                                k: saved[k]
                                for k in ("text", "session_id", "usage", "metadata")
                                if k in saved
                            }
                        )
                    else:
                        if authorized or not recover:
                            ctx.journal.response(
                                operation_id,
                                {"request": request_data, "generation": generation},
                            )
                        dispatched = False
                        try:
                            if (
                                recover
                                and not authorized
                                and not saved.get("not_dispatched")
                            ):
                                recover_fn = getattr(
                                    ctx.client.provider, "recover", None
                                )
                                response = recover_fn(request) if recover_fn else None
                                if response is None:
                                    raise UncertainOperation(
                                        "Provider intent has no durable response; reconcile before retrying",
                                        operation_id,
                                    )
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
                                        response = ctx.client.provider.run(request)
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
                                    response = ctx.client.provider.run(request)
                        except BudgetExceeded as exc:
                            if not dispatched:
                                ctx.journal.response(
                                    operation_id,
                                    {
                                        "request": request_data,
                                        "generation": generation,
                                        "not_dispatched": True,
                                        "budget_error": str(exc),
                                    },
                                )
                                store.restore(artifact_operation)
                            raise
                        except ProviderPolicyError:
                            store.restore(artifact_operation)
                            raise
                        except ProviderError as exc:
                            raise UncertainOperation(str(exc), operation_id) from exc
                        if not isinstance(response, ProviderResponse):
                            raise UncertainOperation(
                                "Provider returned an invalid response; reconcile its effects",
                                operation_id,
                            )
                        ctx.journal.response(
                            operation_id,
                            {
                                **asdict(response),
                                "request": request_data,
                                "generation": generation,
                            },
                            session_key=self.key,
                        )
                    try:
                        if returns is str:
                            value = response.text
                        else:
                            text = response.text.strip()
                            fenced = re.fullmatch(
                                r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL
                            )
                            value = TypeAdapter(returns).validate_json(
                                fenced.group(1) if fenced else text
                            )
                        artifacts = store.capture(writes, artifact_operation)
                    except (ValueError, ArtifactError) as exc:
                        raise OutputValidationError(str(exc)) from exc
                    return Result(value, artifacts, response.usage, operation_id)

                # Alternate writable workspaces need the same cross-process
                # ownership fence as the client's primary workspace. Completed
                # replay consumes only the journal and does not claim a target.
                if (
                    target != ctx.workspace
                    and effective.sandbox_mode != SandboxMode.READ_ONLY
                    and not owns_target
                ):
                    pending = ctx.journal.get(f"{ctx.run_id}:{ctx.scope}:{ctx.ordinal}")
                    if pending is None or pending["status"] not in (
                        "completed",
                        "failed",
                    ):
                        target_ownership.enter_context(
                            ctx.client._ownership(ctx.run_id, workspace=target)
                        )
                        owns_target = True
                try:
                    result = ctx.operation(
                        "provider",
                        inputs,
                        execute,
                        recover=lambda: execute(True),
                        name=name,
                    )
                    usage = dict(repair_usage)
                    for key, value in result.usage.items():
                        if isinstance(value, (int, float)) and not isinstance(
                            value, bool
                        ):
                            usage[key] = usage.get(key, 0) + value
                        else:
                            usage[key] = value
                    return replace(result, usage=usage)
                except OutputValidationError as exc:
                    operation_id = f"{ctx.run_id}:{ctx.scope}:{ctx.ordinal - 1}"
                    response = ctx.journal.get(operation_id).get("response") or {}
                    for key, value in response.get("usage", {}).items():
                        if isinstance(value, (int, float)) and not isinstance(
                            value, bool
                        ):
                            repair_usage[key] = repair_usage.get(key, 0) + value
                    exc.usage = dict(repair_usage)
                    if attempt == retries:
                        raise
                    feedback = str(exc)
        finally:
            target_ownership.close()
            if acquired_workspace:
                workspace_lock.release()
            lock.release()

    @overload
    async def arun(
        self, prompt: str | Prompt, *, returns: type[T], **kwargs: Any
    ) -> Result[T]: ...

    @overload
    async def arun(self, prompt: str | Prompt, **kwargs: Any) -> Result[str]: ...

    async def arun(self, prompt, **kwargs):
        return await _async_call(self.run, prompt, **kwargs)
