"""Durable ordinary functions over recorded, typed operations."""

from __future__ import annotations

import asyncio
import contextvars
import functools
import hashlib
import inspect
import json
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from types import CodeType
from typing import get_type_hints

from pydantic import TypeAdapter

from . import codec
from .errors import (
    ActivityFailed,
    BotpipeError,
    BudgetExceeded,
    InputRequired,
    ReplayMismatch,
    RunBusy,
    Suspension,
    UncertainOperation,
    WorkflowChanged,
)
from .journal import Journal, now, workspace_lock
from .models import RunResult
from .policy import Policy
from .provenance import capture_workflow_provenance

_CURRENT = contextvars.ContextVar("botpipe_run", default=None)
_OPERATION = contextvars.ContextVar("botpipe_operation", default=None)
_ACTIVITY = contextvars.ContextVar("botpipe_activity", default=False)
_UNSET = object()


def current_run():
    ctx = _CURRENT.get()
    if ctx is None:
        raise BotpipeError("This operation requires an active Botpipe workflow")
    return ctx


def _hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _exception_record(exc):
    codec.type_name(type(exc))
    record = {
        "module": type(exc).__module__,
        "type": type(exc).__qualname__,
        "message": str(exc),
    }
    try:
        record["args"] = codec.encode(exc.args)
        record["attributes"] = codec.encode(vars(exc))
    except TypeError:
        pass
    return record


def _restore_exception(record):
    try:
        cls = codec.resolve_type(f"{record['module']}:{record['type']}")
        args = (
            codec.decode(record["args"]) if "args" in record else (record["message"],)
        )
        try:
            result = cls(*args)
        except Exception:
            result = BaseException.__new__(cls)
            BaseException.__init__(result, *args)
        if "attributes" in record:
            vars(result).update(codec.decode(record["attributes"]))
        return result
    except Exception:
        return ActivityFailed(f"{record['type']}: {record['message']}")


def _function_version(fn, seen=None):
    """Pin callable code and referenced Python helpers/constants, not edited work data."""
    fn = inspect.unwrap(getattr(fn, "fn", fn))
    seen = set() if seen is None else seen
    key = f"{fn.__module__}:{fn.__qualname__}"
    if key in seen:
        return key
    seen.add(key)
    try:
        source = inspect.getsource(fn)
    except (OSError, TypeError):
        source = fn.__code__.co_code.hex()
    try:
        defaults = codec.encode(fn.__defaults__)
    except TypeError:
        raise TypeError("Workflow defaults must be durable data") from None
    values = {
        "source": source,
        "defaults": defaults,
        "kwdefaults": codec.encode(fn.__kwdefaults__),
        "helpers": {},
    }

    def code_identity(code):
        def constant(value):
            if isinstance(value, CodeType):
                return code_identity(value)
            try:
                return codec.encode(value)
            except TypeError:
                return repr(value)

        return {
            "bytes": code.co_code.hex(),
            "names": code.co_names,
            "constants": [constant(value) for value in code.co_consts],
        }

    values["code"] = code_identity(fn.__code__)
    namespace = getattr(fn, "__globals__", {})

    def referenced_names(code):
        names = set(code.co_names)
        for value in code.co_consts:
            if isinstance(value, CodeType):
                names.update(referenced_names(value))
        return names

    def helper_version(value):
        try:
            return _function_version(value, seen)
        except TypeError:
            # Library helpers may use opaque default sentinels that never cross
            # a durable boundary. Pin their source without trying to serialize
            # library configuration as workflow arguments.
            target = inspect.unwrap(getattr(value, "fn", value))
            try:
                helper_source = inspect.getsource(target)
            except (OSError, TypeError):
                helper_source = code_identity(target.__code__)
            return _hash(
                {
                    "reference": f"{target.__module__}:{target.__qualname__}",
                    "source": helper_source,
                }
            )

    for name in sorted(referenced_names(fn.__code__)):
        value = namespace.get(name)
        if inspect.isfunction(value) or isinstance(value, Workflow):
            sdk_modules = {
                "botpipe.runtime",
                "botpipe.sessions",
                "botpipe.prompts",
                "botpipe.artifacts",
                "botpipe.worklists",
            }
            if getattr(value, "__module__", "") not in sdk_modules or isinstance(
                value, Workflow
            ):
                values["helpers"][name] = helper_version(value)
        elif isinstance(value, (str, int, float, bool, tuple)) or value is None:
            try:
                values["helpers"][name] = codec.encode(value)
            except TypeError:
                pass
        elif isinstance(value, type):
            codec.type_name(value)
            try:
                values["helpers"][name] = TypeAdapter(value).json_schema()
            except Exception:
                pass
    # Closures containing mutable test providers/counters are not orchestration
    # source. Immutable configuration is pinned; effects inside closures must be activities.
    if fn.__closure__:
        values["closure"] = []
        for cell in fn.__closure__:
            value = cell.cell_contents
            if isinstance(value, (str, int, float, bool, tuple)):
                values["closure"].append(codec.encode(value))
            elif inspect.isfunction(value) or isinstance(value, Workflow):
                values["closure"].append(helper_version(value))
            elif isinstance(value, type):
                values["closure"].append({"type": codec.type_name(value)})
    return _hash(values)


def _validate_args(fn, args, kwargs):
    signature = inspect.signature(fn)
    bound = signature.bind(*args, **kwargs)
    bound.apply_defaults()
    try:
        hints = get_type_hints(fn)
    except (NameError, TypeError):
        hints = {}
    for name, value in list(bound.arguments.items()):
        annotation = hints.get(name, signature.parameters[name].annotation)
        if annotation is inspect.Parameter.empty or isinstance(annotation, str):
            continue
        if signature.parameters[name].kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if isinstance(annotation, type):
            codec.type_name(annotation)
        bound.arguments[name] = TypeAdapter(annotation).validate_python(value)
    return bound.args, bound.kwargs


def _invoke(fn, args, kwargs):
    args, kwargs = _validate_args(fn, args, kwargs)
    value = fn(*args, **kwargs)
    if inspect.isawaitable(value):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(value)
        if inspect.iscoroutine(value):
            value.close()
        raise BotpipeError(
            "Use await for an async child workflow or client.arun from an event loop"
        )
    return value


async def _async_call(fn, *args, **kwargs):
    task = asyncio.create_task(asyncio.to_thread(fn, *args, **kwargs))
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True
            if task.done():
                result = task.result()
                break
    if cancelled:
        raise asyncio.CancelledError
    return result


class Workflow:
    """Callable definition. A workflow's public body remains ordinary Python."""

    def __init__(self, fn, *, name=None, version="1", policy=None):
        functools.update_wrapper(self, fn)
        self.fn, self.name, self.version = fn, name or fn.__name__, str(version)
        self.policy = Policy.resolve(policy)
        from .provenance import capture_definition_sources

        self._source_identity_at_definition = capture_definition_sources(self)

    def __call__(self, *args, **kwargs):
        ctx = current_run()
        if inspect.iscoroutinefunction(self.fn):
            return _async_call(ctx.invoke, self, *args, **kwargs)
        return ctx.invoke(self, *args, **kwargs)

    @property
    def fingerprint(self):
        return _hash(
            {
                "name": self.name,
                "version": self.version,
                "policy": self.policy.to_dict(),
                "source": _function_version(self.fn),
            }
        )


def workflow(fn=None, *, name=None, version="1", policy=None):
    frame = inspect.currentframe()
    local_types = (
        dict(frame.f_back.f_locals) if frame is not None and frame.f_back else {}
    )
    del frame

    def decorate(function):
        _resolve_annotations(function, local_types)
        return Workflow(function, name=name, version=version, policy=policy)

    return decorate(fn) if fn is not None else decorate


def activity(fn=None, *, retry_safe=False, retries=0, name=None):
    frame = inspect.currentframe()
    local_types = (
        dict(frame.f_back.f_locals) if frame is not None and frame.f_back else {}
    )
    del frame
    if not isinstance(retries, int) or retries < 0:
        raise ValueError("retries must be a nonnegative integer")
    if retries and not retry_safe:
        raise ValueError("Activity retries require retry_safe=True")

    def decorate(function):
        _resolve_annotations(function, local_types)

        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            ctx = current_run()
            if _ACTIVITY.get():
                raise BotpipeError(
                    "An activity cannot call another managed activity; use an ordinary helper"
                )
            inputs = {
                "function": _function_version(function),
                "args": args,
                "kwargs": kwargs,
            }
            last = None
            for attempt in range(retries + 1):

                def execute():
                    token = _ACTIVITY.set(True)
                    try:
                        return _invoke(function, args, kwargs)
                    finally:
                        _ACTIVITY.reset(token)

                try:
                    return ctx.operation(
                        "activity",
                        {**inputs, "attempt": attempt},
                        execute,
                        retry_safe=retry_safe,
                        name=name or function.__qualname__,
                    )
                except BotpipeError:
                    # Runtime/replay failures are not activity failures and may
                    # never advance execution to a new retry identity.
                    raise
                except Exception as exc:
                    last = exc
            raise last

        if inspect.iscoroutinefunction(function):

            @functools.wraps(function)
            async def async_wrapped(*args, **kwargs):
                return await _async_call(wrapped, *args, **kwargs)

            return async_wrapped
        return wrapped

    return decorate(fn) if fn is not None else decorate


def _resolve_annotations(function, local_types):
    # Resolve locally defined models while their declaration scope exists.
    # Only annotations are retained, never execution frames or local state.
    try:
        function.__annotations__ = get_type_hints(function, localns=local_types)
    except (NameError, TypeError):
        pass  # Module forward references can resolve at invocation time.


class RunContext:
    def __init__(
        self,
        client,
        metadata,
        definition,
        *,
        scope="root",
        parent=None,
        parallel_branch=False,
    ):
        self.client, self.journal, self.definition = client, client.journal, definition
        self.run_id, self.task_id = metadata["run_id"], metadata["task_id"]
        self.workspace = client.workspace
        self.task_folder = client.state_dir / "tasks" / self.task_id
        self.scope, self.ordinal = scope, 0
        self.folder = Path(metadata["folder"])
        if parent is not None:
            self.folder = (
                parent.folder
                / "children"
                / hashlib.sha256(scope.encode()).hexdigest()[:16]
            )
        self.folder.mkdir(parents=True, exist_ok=True)
        source = inspect.getsourcefile(definition.fn)
        self.source_dir = Path(source).resolve().parent if source else self.workspace
        self.policy = Policy.resolve(
            parent.policy if parent else client.policy, definition.policy
        )
        self.parallel_branch = parallel_branch or (
            parent.parallel_branch if parent else False
        )
        self._session_locks = parent._session_locks if parent else {}
        self._workspace_locks = parent._workspace_locks if parent else {}
        self._guard = parent._guard if parent else threading.RLock()
        self._execution_lock = threading.RLock()
        self._replay_state = parent._replay_state if parent else {"error": None}
        self.provider_budgets = parent.provider_budgets if parent else ()

    @property
    def operation_id(self):
        return _OPERATION.get()

    def operation(
        self,
        kind,
        inputs,
        execute,
        *,
        retry_safe=False,
        orchestrator=False,
        recover=None,
        name=None,
    ):
        if self._replay_state["error"] is not None:
            raise self._replay_state["error"]
        if not self._execution_lock.acquire(blocking=False):
            raise BotpipeError(
                "Concurrent operations require parallel() with independent branch scopes"
            )
        try:
            return self._operation(
                kind,
                inputs,
                execute,
                retry_safe=retry_safe,
                orchestrator=orchestrator,
                recover=recover,
                name=name,
            )
        except ReplayMismatch as exc:
            # A caught application exception cannot make divergent history
            # valid or authorize additional effects in another scope.
            self._replay_state["error"] = exc
            raise
        finally:
            self._execution_lock.release()

    def _operation(
        self,
        kind,
        inputs,
        execute,
        *,
        retry_safe=False,
        orchestrator=False,
        recover=None,
        name=None,
    ):
        if _ACTIVITY.get():
            raise BotpipeError("Managed operations cannot run inside an activity")
        ordinal = self.ordinal
        self.ordinal += 1
        operation_id = f"{self.run_id}:{self.scope}:{ordinal}"
        encoded_inputs = codec.encode(inputs)
        fingerprint = _hash({"kind": kind, "name": name, "inputs": encoded_inputs})
        record = self.journal.get(operation_id)
        if record is not None:
            if record["fingerprint"] != fingerprint or record["kind"] != kind:
                raise ReplayMismatch(
                    f"Operation {operation_id} changed ({record['kind']} -> {kind}); start a new run"
                )
            if record["status"] == "completed":
                return codec.decode(record["result"])
            if record["status"] == "failed":
                raise _restore_exception(record["error"])
            authorized = bool((record.get("response") or {}).get("retry_authorized"))
            if recover is None and not (retry_safe or orchestrator or authorized):
                raise UncertainOperation(
                    f"Operation {operation_id} was interrupted; reconcile it before retrying",
                    operation_id,
                )
            if authorized and recover is None:
                self.journal.response(
                    operation_id,
                    {"generation": record["response"].get("generation", 1)},
                )
        else:
            self.journal.begin(
                operation_id=operation_id,
                run_id=self.run_id,
                scope=self.scope,
                ordinal=ordinal,
                kind=kind,
                name=name,
                fingerprint=fingerprint,
                inputs=encoded_inputs,
                limit=self.client.max_operations,
            )
        token = _OPERATION.set(operation_id)
        try:
            result = (
                recover() if record is not None and recover is not None else execute()
            )
            self.journal.finish(operation_id, codec.encode(result))
            return result
        except (Suspension, ReplayMismatch):
            raise
        except Exception as exc:
            self.journal.fail(operation_id, _exception_record(exc))
            raise
        finally:
            _OPERATION.reset(token)

    def _child(self, definition, args, kwargs, scope, *, parallel_branch=False):
        child = RunContext(
            self.client,
            self.journal.run(self.run_id),
            definition,
            scope=scope,
            parent=self,
            parallel_branch=parallel_branch,
        )
        token = _CURRENT.set(child)
        try:
            value = _invoke(definition.fn, args, kwargs)
            child.assert_consumed()
            return value
        finally:
            _CURRENT.reset(token)

    def invoke(self, definition, *args, **kwargs):
        if not isinstance(definition, Workflow):
            raise TypeError("Child workflows must use @workflow")
        inputs = {
            "workflow": definition.name,
            "version": definition.fingerprint,
            "args": args,
            "kwargs": kwargs,
        }

        def execute():
            return self._child(
                definition, args, kwargs, f"{self.scope}/child-{self.ordinal - 1}"
            )

        return self.operation(
            "child", inputs, execute, orchestrator=True, name=definition.name
        )

    def scope_call(self, scope, fn):
        definition = Workflow(fn, name=getattr(fn, "__name__", "branch"))
        return self._child(
            definition, (), {}, f"{self.scope}/{scope}", parallel_branch=True
        )

    def assert_consumed(self):
        if self._replay_state["error"] is not None:
            raise self._replay_state["error"]
        extra = [
            r
            for r in self.journal.operations(self.run_id)
            if r["scope"] == self.scope and r["ordinal"] >= self.ordinal
        ]
        if extra:
            error = ReplayMismatch(
                f"Workflow returned before consuming recorded operation {extra[0]['id']}"
            )
            self._replay_state["error"] = error
            raise error


def ask(question, *, returns=str):
    ctx = current_run()
    schema = codec.schema_for(returns)

    def execute():
        record = ctx.journal.get(ctx.operation_id)
        if record["status"] == "response":
            return TypeAdapter(returns).validate_python(
                codec.decode(record["response"]["answer"])
            )
        ctx.journal.wait_input(
            ctx.operation_id, {"question": str(question), "schema": schema}
        )
        raise InputRequired(str(question), ctx.operation_id)

    return ctx.operation(
        "input",
        {"question": str(question), "schema": schema},
        execute,
        orchestrator=True,
    )


def parallel(*calls, max_workers=None, settle="all"):
    if settle not in ("all", "collect"):
        raise ValueError("settle must be all or collect")
    if not all(callable(fn) for fn in calls):
        raise TypeError("parallel expects callables, e.g. lambda: reviewer.run(...)")
    ctx = current_run()
    inputs = {"calls": [_function_version(fn) for fn in calls], "settle": settle}

    def execute():
        group = ctx.ordinal - 1
        if not calls:
            return []
        with ThreadPoolExecutor(max_workers=max_workers or len(calls)) as pool:
            futures = [
                pool.submit(ctx.scope_call, f"parallel-{group}/{index}", fn)
                for index, fn in enumerate(calls)
            ]
            values = []
            errors = []
            for future in futures:
                try:
                    values.append(future.result())
                except BaseException as exc:
                    errors.append(exc)
                    values.append({"error": str(exc), "type": type(exc).__name__})
            suspended = next((e for e in errors if not isinstance(e, Exception)), None)
            if suspended is not None:
                raise suspended
            if errors and settle == "all":
                raise errors[0]
            return values

    return ctx.operation(
        "parallel", inputs, execute, orchestrator=True, name="parallel"
    )


class Botpipe:
    def __init__(
        self,
        workspace=".",
        provider="codex",
        *,
        state_dir=None,
        policy=None,
        max_operations=1000,
        timeout=3600,
        provider_config=None,
    ):
        from .providers import get_provider

        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ValueError(f"Workspace is not a directory: {self.workspace}")
        self.state_dir = (
            Path(state_dir).resolve() if state_dir else self.workspace / ".botpipe"
        )
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.provider_config = dict(provider_config or {})
        self.provider = (
            get_provider(provider, config=self.provider_config)
            if isinstance(provider, str)
            else provider
        )
        if not callable(getattr(self.provider, "run", None)):
            raise TypeError("Provider must implement run(request)")
        self.provider_name = getattr(
            self.provider, "name", type(self.provider).__name__
        )
        self.policy = Policy.resolve(policy)
        if (
            not isinstance(max_operations, int)
            or isinstance(max_operations, bool)
            or max_operations < 1
        ):
            raise ValueError("max_operations must be a positive integer")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.max_operations, self.timeout = max_operations, float(timeout)
        self.journal = Journal(self.state_dir / "state.sqlite3")

    def _definition(self, value):
        if isinstance(value, str):
            from .discovery import resolve_workflow

            value = resolve_workflow(value, workspace=self.workspace)
        if not isinstance(value, Workflow):
            raise TypeError("Expected a @workflow function or workflow reference")
        return value

    @contextmanager
    def _ownership(self, run_id, *, workspace=None):
        # The workspace fence survives process death and is shared even when
        # clients use different state directories. A released OS lock does not
        # prove that an external provider process has stopped editing files.
        target = self.workspace if workspace is None else Path(workspace).resolve()
        with workspace_lock(target / ".botpipe-workspace.lock") as handle:
            handle.seek(0)
            raw = handle.read().strip()
            if raw:
                try:
                    owner = json.loads(raw)
                except (ValueError, UnicodeError) as exc:
                    raise RunBusy(
                        "Workspace ownership record is unreadable; restore it before continuing"
                    ) from exc
                if owner == {"journal": str(self.journal.path), "run_id": run_id}:
                    # Do not rewrite the only fence while resuming uncertain
                    # effects. A crash during truncation could erase ownership.
                    yield
                    return
                if owner != {"journal": str(self.journal.path), "run_id": run_id}:
                    path = Path(owner["journal"])
                    if not path.is_file():
                        raise RunBusy(
                            "Previous run journal is missing; restore it to reconcile workspace ownership"
                        )
                    import sqlite3

                    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                    try:
                        rows = db.execute(
                            "SELECT kind,status,response,inputs FROM operations WHERE run_id=? "
                            "AND kind IN ('provider','activity') AND status IN ('started','response')",
                            (owner["run_id"],),
                        ).fetchall()
                    finally:
                        db.close()
                    unfinished = any(
                        not json.loads(response or "{}").get("not_dispatched")
                        and (
                            kind == "activity"
                            or "text" not in json.loads(response or "{}")
                            or bool(json.loads(inputs).get("value", {}).get("writes"))
                        )
                        for kind, status, response, inputs in rows
                    )
                    if unfinished:
                        raise RunBusy(
                            f"Run {owner['run_id']} has unresolved effects; resume or reconcile it first"
                        )
            record = json.dumps(
                {"journal": str(self.journal.path), "run_id": run_id}
            ).encode()
            handle.seek(0)
            handle.truncate()
            handle.write(record)
            handle.flush()
            os.fsync(handle.fileno())
            yield

    def run(self, definition, *args, task_id=None, run_id=None, **kwargs):
        definition = self._definition(definition)
        args, kwargs = _validate_args(definition.fn, args, kwargs)
        task_id = task_id or uuid.uuid4().hex[:12]
        run_id = run_id or uuid.uuid4().hex
        for label, value in (("task_id", task_id), ("run_id", run_id)):
            if not isinstance(value, str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value
            ):
                raise ValueError(f"{label} must be a safe identifier")
        folder = self.state_dir / "tasks" / task_id / "runs" / run_id
        data = {
            "run_id": run_id,
            "task_id": task_id,
            "workflow": definition.name,
            "module": definition.fn.__module__,
            "function": definition.fn.__qualname__,
            "source_file": inspect.getsourcefile(definition.fn),
            "version": definition.fingerprint,
            "args": codec.encode(args),
            "kwargs": codec.encode(kwargs),
            "status": "created",
            "folder": str(folder),
            "provider": self.provider_name,
            "provider_config": self.provider_config,
            "policy": self.policy.to_dict(),
            "max_operations": self.max_operations,
            "timeout": self.timeout,
            "created_at": now(),
            "error": None,
        }
        with self._ownership(run_id):
            data["provenance_start"] = capture_workflow_provenance(
                definition, self.workspace
            )
            self.journal.create_run(data)
            return self._execute(definition, data, args, kwargs)

    async def arun(self, definition, *args, **kwargs):
        # One runtime and one provider boundary. Cancellation joins the worker;
        # it never reports a stopped workflow while the worker still edits files.
        return await _async_call(self.run, definition, *args, **kwargs)

    def resume(
        self, run_id, *, answer=_UNSET, workflow=None, max_operations=None, timeout=None
    ):
        with self._ownership(run_id):
            data = self.journal.run(run_id)
            if workflow is None:
                reference = f"{data['module']}:{data['function']}"
                try:
                    definition = self._definition(reference)
                except (
                    ImportError,
                    AttributeError,
                    LookupError,
                    ValueError,
                    BotpipeError,
                ):
                    if not data.get("source_file") or "<locals>" in data["function"]:
                        raise BotpipeError(
                            "Pass workflow= when resuming a local workflow function"
                        )
                    definition = self._definition(
                        f"{data['source_file']}:{data['function']}"
                    )
            else:
                definition = self._definition(workflow)
            if definition.fingerprint != data["version"]:
                raise WorkflowChanged(
                    "Workflow code or referenced contracts changed; resume with original code or start a new run"
                )
            if (
                data["provider"] != self.provider_name
                or data.get("provider_config", {}) != self.provider_config
            ):
                raise ReplayMismatch(
                    "Provider configuration changed; resume with the recorded provider configuration"
                )
            if self.policy.to_dict() != data["policy"]:
                raise ReplayMismatch(
                    "Run policy changed; resume with the recorded policy"
                )
            changes = {}
            if max_operations is not None:
                if (
                    isinstance(max_operations, bool)
                    or not isinstance(max_operations, int)
                    or max_operations < data["max_operations"]
                ):
                    raise ValueError(
                        "Resume operation budget must be at least the recorded budget"
                    )
                changes["max_operations"] = max_operations
            if timeout is not None:
                if isinstance(timeout, bool) or timeout <= 0:
                    raise ValueError("timeout must be positive")
                changes["timeout"] = float(timeout)
            if changes:
                data.update(changes)
                self.journal.update_run(run_id, **changes)
                self.journal.event(run_id, "run_limits_updated", changes)
            if answer is not _UNSET:
                pending = data.get("pending_input")
                if not pending:
                    raise ValueError("Run is not waiting for an answer")
                import jsonschema

                json_value = (
                    answer.model_dump(mode="json")
                    if hasattr(answer, "model_dump")
                    else answer
                )
                jsonschema.validate(json_value, pending["schema"])
                self.journal.response(
                    pending["operation_id"], {"answer": codec.encode(answer)}
                )
            self.max_operations = data["max_operations"]
            self.timeout = data["timeout"]
            return self._execute(
                definition,
                data,
                codec.decode(data["args"]),
                codec.decode(data["kwargs"]),
            )

    async def aresume(self, run_id, **kwargs):
        return await _async_call(self.resume, run_id, **kwargs)

    def _execute(self, definition, data, args, kwargs):
        ctx = RunContext(self, data, definition)
        token = _CURRENT.set(ctx)
        status = "completed"
        value = None
        error = None
        pending = None
        self.journal.update_run(
            ctx.run_id, status="running", pending_input=None, error=None
        )
        try:
            value = _invoke(definition.fn, args, kwargs)
            ctx.assert_consumed()
            encoded = codec.encode(value)
        except InputRequired as exc:
            status = "awaiting_input"
            error = None
            record = self.journal.get(exc.operation_id)
            pending = {"operation_id": exc.operation_id, **record["response"]}
            encoded = None
        except BudgetExceeded as exc:
            status = "budget_exceeded"
            error = str(exc)
            encoded = None
        except UncertainOperation as exc:
            status = "interrupted"
            error = str(exc)
            encoded = None
        except KeyboardInterrupt:
            status = "interrupted"
            error = "Execution interrupted"
            encoded = None
        except Exception as exc:
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
            encoded = None
        finally:
            _CURRENT.reset(token)
        artifacts, usage = self._outputs(ctx.run_id)
        self.journal.update_run(
            ctx.run_id,
            status=status,
            value=encoded,
            error=error,
            pending_input=pending,
            usage=usage,
            updated_at=now(),
            provenance_end=capture_workflow_provenance(definition, self.workspace),
        )
        return RunResult(
            ctx.run_id,
            ctx.task_id,
            status,
            value,
            artifacts,
            error,
            pending,
            ctx.folder,
            usage,
        )

    def _outputs(self, run_id):
        from .artifacts import ArtifactHandle, ArtifactMap
        from .dispatches import aggregate_usage, dispatch_records

        artifacts = {}
        usage = {}
        dispatches = dispatch_records(self.journal.events(run_id))
        for row in self.journal.operations(run_id):
            response = row.get("response") or {}
            observed_usage = (
                aggregate_usage(dispatches[row["id"]])
                if row["id"] in dispatches
                else response.get("usage", {})
            )
            for key, value in observed_usage.items():
                if isinstance(value, (int, float)):
                    usage[key] = usage.get(key, 0) + value
            if row["status"] == "completed" and row["kind"] == "provider":
                # Inspection needs artifact records, not executable imports of
                # the workflow's possibly local or no-longer-installed model.
                handles = codec.decode(row["result"]["value"]["artifacts"])
                for name, handle in handles.items():
                    artifacts[f"{row['scope']}/{row['ordinal']}/{name}"] = handle
            elif row["status"] == "completed" and row["kind"] in (
                "worklist.complete",
                "worklist_complete",
                "read",
            ):
                result = codec.decode(row["result"])
                if (
                    isinstance(result, dict)
                    and {"name", "path", "source_path", "kind", "digest"}
                    <= result.keys()
                ):
                    result = ArtifactHandle.from_record(result)
                if isinstance(result, ArtifactHandle):
                    artifacts[f"{row['scope']}/{row['ordinal']}/{result.name}"] = result
        return ArtifactMap(artifacts), usage

    def runs(self):
        return self.journal.runs()

    def inspect(self, run_id):
        from .dispatches import aggregate_usage, dispatch_records

        records = self.journal.operations(run_id)
        events = self.journal.events(run_id)
        dispatches = dispatch_records(events)
        for record in records:
            response = record.get("response") or {}
            if record["id"] in dispatches:
                record["dispatches"] = dispatches[record["id"]]
                record["usage"] = aggregate_usage(record["dispatches"])
                record["usage_availability"] = (
                    "known_total"
                    if all(
                        d["usage_availability"] == "known_total"
                        for d in record["dispatches"]
                    )
                    else "partial"
                    if record["usage"]
                    else "unknown"
                )
            else:
                record["usage"] = response.get("usage", {})
        artifacts, usage = self._outputs(run_id)
        return {
            "run": self.journal.run(run_id),
            "operations": records,
            "events": events,
            "artifacts": artifacts.to_record(),
            "usage": usage,
        }

    def resolve(self, run_id, operation_id, *, retry=False, response=_UNSET):
        if bool(retry) == (response is not _UNSET):
            raise ValueError("Choose either retry=True or a response")
        with workspace_lock(self.workspace / ".botpipe-workspace.lock"):
            record = self.journal.get(operation_id)
            if record is None or record["run_id"] != run_id:
                raise KeyError(operation_id)
            if record["status"] not in ("started", "response"):
                raise ValueError("Only unfinished operations can be reconciled")
            if record["kind"] not in ("provider", "activity"):
                raise ValueError(
                    "Only provider turns and activities require effect reconciliation"
                )
            if (record.get("response") or {}).get("not_dispatched"):
                raise ValueError(
                    "Budget exhausted before dispatch; no effects need reconciliation. "
                    "Start a new run to use different provider budget limits"
                )
            if response is not _UNSET:
                from .providers import (
                    ProviderError,
                    ProviderInterruptedError,
                    ProviderRequest,
                    ProviderResponse,
                )

                if record["kind"] == "provider":
                    if isinstance(response, dict):
                        response = ProviderResponse(**response)
                    if not isinstance(response, ProviderResponse):
                        raise TypeError(
                            "Provider reconciliation needs ProviderResponse or its field mapping"
                        )
                    inputs = codec.decode(record["inputs"])
                    old = record.get("response") or {}
                    request_data = old.get("request") or {}
                    recover = getattr(self.provider, "recover", None)
                    if recover and request_data.get("receipt_dir"):
                        request = ProviderRequest(
                            operation_id=operation_id,
                            prompt="",
                            workspace=Path(inputs["workspace"]),
                            session_id=request_data.get("session_id"),
                            output_schema=inputs.get("schema"),
                            policy=Policy.from_dict(inputs["policy"]),
                            artifacts={},
                            receipt_dir=Path(request_data["receipt_dir"]),
                            timeout=self.timeout,
                            attempt=old.get("generation", 0) + 1,
                        )
                        try:
                            recover(request)
                        except ProviderInterruptedError as exc:
                            if exc.process_alive is True:
                                raise BotpipeError(
                                    "The provider is still running; stop it before recording a resolution"
                                ) from exc
                        except ProviderError:
                            pass
                    old.pop("retry_authorized", None)
                    self.journal.response(
                        operation_id,
                        {**old, **asdict(response)},
                        session_key=inputs.get("session"),
                    )
                else:
                    self.journal.finish(operation_id, codec.encode(response))
            else:
                # Explicit retry is represented by an authorization marker; the
                # original intent/identity remains, and adapters keep old receipts.
                old = record.get("response") or {}
                self.journal.response(
                    operation_id,
                    {
                        "retry_authorized": True,
                        "generation": old.get("generation", 0)
                        + (0 if old.get("retry_authorized") else 1),
                        **({"request": old["request"]} if "request" in old else {}),
                    },
                )
            self.journal.event(
                run_id, "operation_reconciled", {"retry": retry}, operation_id
            )

    def close(self):
        self.journal.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
