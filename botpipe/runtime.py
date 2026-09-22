"""Durable ordinary functions over recorded, typed operations."""

from __future__ import annotations

import asyncio
import contextvars
import dataclasses
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
from enum import Enum
from pathlib import Path
from types import MemberDescriptorType
from typing import TYPE_CHECKING, Self, get_type_hints

from pydantic import BaseModel, TypeAdapter, ValidationError

from . import codec
from ._callables import describe_callable
from ._code_identity import code_identity
from .errors import (
    ActivityFailed,
    BotpipeError,
    BudgetExceeded,
    InputRequired,
    ReplayMismatch,
    RunBusy,
    Suspension,
    UncertainOperation,
)
from .journal import Journal, now
from .limits import RunLimits
from .workspace_ownership import WorkspaceCoordinator
from .models import RunResult
from .policy import Policy, SandboxMode
from .provenance import SourceContext, capture_workflow_provenance, source_context
from .provider_checkpoints import (
    NotDispatchedCheckpoint,
    ProviderCheckpoint,
    ProviderLifecycle,
    RecoveryAction,
    RespondedCheckpoint,
    RetryAuthorizedCheckpoint,
    canonical_provider_response,
    provider_attempt_identity,
    provider_recovery_outcome,
)
from .recovery import (
    Completed,
    Running,
    Stopped,
    Unknown,
    cancellation_evidence,
    recover_outcome,
)

if TYPE_CHECKING:
    from .provider import Provider

_CURRENT = contextvars.ContextVar("botpipe_run", default=None)
_OPERATION = contextvars.ContextVar("botpipe_operation", default=None)
_ACTIVITY = contextvars.ContextVar("botpipe_activity", default=False)
_ASYNC_CANCELLATION = contextvars.ContextVar(
    "botpipe_async_cancellation", default=None
)
_UNSET = object()


def current_run() -> RunContext:
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


def _commit_or_confirm(journal, operation_id, write, projection, message):
    """Accept an acknowledgement failure only for the exact committed write."""
    try:
        write()
    except Exception as exc:
        try:
            observed = journal.confirmed(operation_id)
        except Exception:
            observed = None
        if not observed or any(
            observed.get(field) != value for field, value in projection.items()
        ):
            raise UncertainOperation(message, operation_id) from exc


def _persist_response(journal, operation_id, response, *, session_update=None):
    projection = {"status": "response", "response": response}
    if session_update is not None:
        projection.update(
            session_id=session_update["session_id"],
            session_revision=session_update["expected_revision"] + 1,
        )
    _commit_or_confirm(
        journal,
        operation_id,
        lambda: journal.response(
            operation_id,
            response,
            session_update=session_update,
        ),
        projection,
        "Operation checkpoint could not be confirmed; resume to reconcile it",
    )


def _operation_encoded_values(record):
    for field in ("inputs", "result"):
        if record.get(field) is not None:
            yield record[field]
    error = record.get("error") or {}
    for field in ("exception_type", "args", "native_args", "attributes"):
        if error.get(field) is not None:
            yield error[field]
    for slot in error.get("slots", ()):
        if type(slot) is dict:
            for field in ("owner_type", "value"):
                if slot.get(field) is not None:
                    yield slot[field]
    response = record.get("response") or {}
    for field in ("answer", "validated_answer", "validated_value"):
        if response.get(field) is not None:
            yield response[field]


def _preflight_recorded_contracts(data, operations):
    """Validate every durable value before accepting input or running effects."""

    try:
        for field in ("workflow_call", "args", "kwargs", "value"):
            value = data.get(field)
            if value is not None:
                codec.verify_contracts(value, path=f"$.run.{field}")
        for index, record in enumerate(operations):
            for value_index, value in enumerate(_operation_encoded_values(record)):
                if value is not None:
                    codec.verify_contracts(
                        value,
                        path=f"$.operations[{index}].values[{value_index}]",
                    )
            error = record.get("error")
            if error is not None:
                _preflight_exception_record(error)
        for record in operations:
            recorded_inputs = codec.decode(record["inputs"])
            if record["kind"] == "activity":
                if not isinstance(recorded_inputs, dict):
                    raise ReplayMismatch("Recorded activity inputs are malformed")
                retry_safe = recorded_inputs.pop("retry_safe", None)
                if type(retry_safe) is not bool:
                    raise ReplayMismatch("Recorded activity retry safety is malformed")
            expected = _hash(
                {
                    "kind": record["kind"],
                    "name": record["name"],
                    "inputs": codec.encode(recorded_inputs),
                }
            )
            if record["fingerprint"] != expected:
                raise ReplayMismatch(
                    f"Recorded operation {record['id']} inputs do not match "
                    "its replay fingerprint"
                )
    except ReplayMismatch:
        raise
    except (
        ImportError,
        AttributeError,
        LookupError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ReplayMismatch(
            f"Recorded durable value contracts cannot be verified: {exc}"
        ) from exc


def _cancellation_was_not_dispatched(operations):
    """Prove every unfinished provider cancellation stopped before dispatch."""

    found = False
    for record in operations:
        if record["status"] in {"completed", "failed"}:
            continue
        if record["kind"] not in {"provider", "decision"}:
            continue
        if record["kind"] != "provider":
            return False
        try:
            checkpoint = ProviderCheckpoint.from_record(record.get("response"))
        except (TypeError, ValueError, ReplayMismatch):
            return False
        if not (
            isinstance(checkpoint, NotDispatchedCheckpoint)
            and checkpoint.error_kind == "cancellation_error"
            and checkpoint.restoration_pending is False
        ):
            return False
        found = True
    return found


def _exception_record(exc):
    codec.type_name(type(exc))
    record = {
        "module": type(exc).__module__,
        "type": type(exc).__qualname__,
        "message": str(exc),
        "exception_type": codec.encode(type(exc)),
    }
    slot_owner_types = {
        owner: codec.encode(owner)
        for owner in type(exc).__mro__
        if owner is not BaseException
        and any(
            isinstance(descriptor, MemberDescriptorType)
            for descriptor in vars(owner).values()
        )
    }
    state_errors = []
    try:
        record["args"] = codec.encode(BaseException.args.__get__(exc, type(exc)))
        if isinstance(exc, OSError):
            reduced = OSError.__reduce__(exc)
            if not isinstance(reduced, tuple) or len(reduced) < 2:
                raise TypeError("OSError did not expose native reconstruction state")
            record["native_family"] = "OSError"
            record["native_args"] = codec.encode(reduced[1])
        record["attributes"] = codec.encode(object.__getattribute__(exc, "__dict__"))
    except (TypeError, AttributeError) as error:
        state_errors.append(str(error))

    slots = []
    for owner in type(exc).__mro__:
        if owner is BaseException:
            continue
        for name, descriptor in vars(owner).items():
            if not isinstance(descriptor, MemberDescriptorType):
                continue
            slot = {
                "owner": codec.type_name(owner),
                "owner_type": slot_owner_types[owner],
                "name": name,
            }
            try:
                value = descriptor.__get__(exc, type(exc))
            except AttributeError:
                slot["present"] = False
            else:
                slot["present"] = True
                try:
                    slot["value"] = codec.encode(value)
                except (TypeError, AttributeError) as error:
                    # The placeholder is never restored when restorable is false,
                    # but keeps the durable slot layout structurally complete.
                    slot["value"] = codec.encode(None)
                    state_errors.append(str(error))
            slots.append(slot)
    record["slots"] = slots
    if not state_errors:
        record["restorable"] = True
    else:
        record["restorable"] = False
        record["state_error"] = "; ".join(state_errors)
    return record


def _recorded_exception_type(record, *, slot=False):
    encoded_field = "owner_type" if slot else "exception_type"
    label = "exception slot owner" if slot else "exception type"
    if encoded_field not in record:
        raise ReplayMismatch(f"Recorded {label} is malformed")
    try:
        cls = codec.decode(record[encoded_field])
    except ReplayMismatch:
        raise
    except (
        ImportError,
        AttributeError,
        LookupError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ReplayMismatch(
            f"Recorded {label} storage contract cannot be verified: {exc}"
        ) from exc
    if not isinstance(cls, type):
        raise ReplayMismatch(f"Recorded {label} did not resolve to a type")
    return cls


def _preflight_exception_record(record):
    if type(record) is not dict:
        raise ReplayMismatch("Recorded exception is malformed")
    cls = _recorded_exception_type(record)
    if not issubclass(cls, BaseException):
        raise ReplayMismatch("Recorded exception type is not an exception")
    slots = record.get("slots", ())
    if type(slots) is not list:
        raise ReplayMismatch("Recorded exception slots are malformed")
    expected = [
        (owner, name)
        for owner in cls.__mro__
        if owner is not BaseException
        for name, descriptor in vars(owner).items()
        if isinstance(descriptor, MemberDescriptorType)
    ]
    if len(slots) != len(expected):
        raise ReplayMismatch("Recorded exception slots no longer match its type")
    for slot, (expected_owner, expected_name) in zip(slots, expected):
        if type(slot) is not dict:
            raise ReplayMismatch("Recorded exception slot is malformed")
        present = slot.get("present")
        required = {"owner", "owner_type", "name", "present"}
        if present is True:
            required.add("value")
        if type(present) is not bool or set(slot) != required:
            raise ReplayMismatch("Recorded exception slot is malformed")
        owner = _recorded_exception_type(slot, slot=True)
        if (
            owner is not expected_owner
            or slot["owner"] != codec.type_name(expected_owner)
            or slot["name"] != expected_name
        ):
            raise ReplayMismatch("Recorded exception slot owner no longer matches")


def _allocate_exception(cls, args, record):
    """Allocate exceptions through native bases without application hooks."""
    if issubclass(cls, OSError):
        # OSError has native state beyond BaseException.args. Passing application
        # subclasses through cls(...) would run their __new__/__init__ hooks.
        if record.get("native_family") != "OSError":
            raise TypeError("OSError record lacks native reconstruction state")
        native_args = _decode_exception_value(
            record["native_args"], "native exception state"
        )
        result = OSError.__new__(cls, *native_args)
        OSError.__init__(result, *native_args)
        return result
    if cls.__module__ == "builtins":
        return cls(*args)
    native = next(
        base
        for base in cls.__mro__[1:]
        if base.__module__ == "builtins" and issubclass(base, BaseException)
    )
    result = native.__new__(cls, *args)
    BaseException.__init__(result, *args)
    return result


def _decode_exception_value(value, label):
    """Keep contract-verification failures out of state-restoration fallback."""

    try:
        codec.verify_contracts(value, path="$exception")
    except (
        ImportError,
        AttributeError,
        LookupError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ReplayMismatch(
            f"Recorded {label} contract cannot be verified: {exc}"
        ) from exc
    return codec.decode(value)


def _restore_exception_state(record):
    cls = _recorded_exception_type(record)
    slots = record.get("slots", ())
    if type(slots) not in (list, tuple):
        raise ReplayMismatch("Recorded exception slots are malformed")
    slot_owners = []
    for slot in slots:
        if type(slot) is not dict:
            raise ReplayMismatch("Recorded exception slot is malformed")
        slot_owners.append(_recorded_exception_type(slot, slot=True))
    if not record.get("restorable", True):
        raise TypeError(record.get("state_error", "unsupported exception state"))
    args = (
        _decode_exception_value(record["args"], "exception arguments")
        if "args" in record
        else (record["message"],)
    )
    if not isinstance(cls, type) or not issubclass(cls, BaseException):
        raise TypeError("Recorded exception type is not an exception")
    result = _allocate_exception(cls, args, record)
    if "attributes" in record:
        object.__getattribute__(result, "__dict__").update(
            _decode_exception_value(record["attributes"], "exception attributes")
        )
    for slot, owner in zip(slots, slot_owners):
        if not slot["present"]:
            continue
        if issubclass(cls, OSError) and owner is OSError:
            continue
        descriptor = vars(owner)[slot["name"]]
        if not issubclass(cls, owner) or not isinstance(
            descriptor, MemberDescriptorType
        ):
            raise TypeError("Recorded exception slot no longer matches its type")
        descriptor.__set__(
            result, _decode_exception_value(slot["value"], "exception slot state")
        )
    return result


def _restore_exception(record):
    try:
        return _restore_exception_state(record)
    except ReplayMismatch:
        raise
    except Exception:
        return ActivityFailed(f"{record['type']}: {record['message']}")


def _finalize_exception_record(record):
    """Make initial and replay behavior agree when restoration is unsupported."""
    try:
        _restore_exception_state(record)
    except ReplayMismatch:
        raise
    except Exception:
        record["restorable"] = False
        record["state_error"] = "exception state cannot be restored safely"
    return record


def _function_version(fn):
    """Hash one canonical, identity-preserving graph of callable code."""
    graph = describe_callable(fn)
    skipped = object()

    def encoded_binding(node, binding):
        if binding.kind == "type":
            name = codec.type_name(binding.value)
            try:
                schema = TypeAdapter(binding.value).json_schema()
            except Exception:  # noqa: BLE001 - schema generation is third-party code
                schema = None
            return {"type": name, "schema": schema}
        try:
            return codec.encode(binding.value)
        except TypeError as exc:
            if callable(binding.value):
                # The matching graph edge pins executable identity.  Explicit
                # defaults and partial bindings retain durable callable-instance state
                # here when the codec supports it.
                return skipped
            if not binding.required:
                return skipped
            if node.kind == "partial":
                location = binding.label.replace("argument:", "argument ").replace(
                    "keyword:", "keyword "
                )
                if binding.label.startswith("keyword:"):
                    location = f"keyword {binding.label.removeprefix('keyword:')!r}"
                raise TypeError(
                    f"Unsupported explicit partial {location}: {exc}"
                ) from None
            raise TypeError("Callable defaults must be durable data") from None

    def function_metadata(target):
        try:
            # The graph already represents wrappers. Inspect this node's code
            # directly instead of repeatedly unwrapping shared decorator suffixes.
            source = inspect.getsource(target.__code__)
        except (OSError, TypeError, ValueError):
            source = code_identity(target.__code__)
        return {
            "reference": f"{target.__module__}:{target.__qualname__}",
            "source": source,
            "code": code_identity(target.__code__),
        }

    def class_metadata(node):
        sources = []
        for target in node.source_targets:
            reference = f"{target.__module__}:{target.__qualname__}"
            try:
                source = inspect.getsource(target)
            except (OSError, TypeError, ValueError):
                source = reference
            sources.append({"reference": reference, "source": source})
        return sources

    records = []
    for node in graph.nodes:
        record = {
            "kind": node.kind,
            "edges": [[edge.label, edge.target] for edge in node.edges],
            "bindings": [],
        }
        for binding in node.bindings:
            encoded = encoded_binding(node, binding)
            if encoded is not skipped:
                record["bindings"].append([binding.label, encoded])
        if node.kind == "workflow":
            definition = node.value
            record["metadata"] = {
                "name": definition.name,
                "version": definition.version,
                "policy": definition.policy.to_dict(),
            }
        elif node.kind in {"function", "decorated"}:
            record["metadata"] = function_metadata(node.value)
        elif node.kind == "class":
            record["metadata"] = {"sources": class_metadata(node)}
        elif node.kind in {"builtin", "builtin_type", "method_descriptor"}:
            record["reference"] = node.reference
        elif node.kind not in {"partial", "method", "instance"}:
            raise TypeError(f"Unsupported callable graph node {node.kind!r}")
        records.append(record)

    return _hash(
        {
            "schema": "botpipe.callable-graph.v2",
            "root": graph.root,
            "nodes": records,
        }
    )


def _observed_workflow_fingerprint(definition):
    try:
        return definition.fingerprint
    except Exception:  # noqa: BLE001 - fingerprints are observational evidence
        return None


def _validate_args(fn, args, kwargs):
    from .discovery import WorkflowInputError

    signature = inspect.signature(fn)
    try:
        bound = signature.bind(*args, **kwargs)
    except TypeError as exc:
        raise WorkflowInputError(str(exc)) from exc
    bound.apply_defaults()
    try:
        hints = get_type_hints(fn)
    except (NameError, TypeError) as exc:
        raise WorkflowInputError(f"Cannot resolve workflow annotations: {exc}") from exc
    for name, value in list(bound.arguments.items()):
        annotation = hints.get(name, signature.parameters[name].annotation)
        if annotation is inspect.Parameter.empty:
            continue
        if signature.parameters[name].kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if isinstance(annotation, type):
            codec.type_name(annotation)
        codec.preflight(annotation, path=f"$.{name}")
        try:
            bound.arguments[name] = TypeAdapter(annotation).validate_python(value)
        except (ValueError, TypeError) as exc:
            raise WorkflowInputError(f"Invalid workflow input {name!r}: {exc}") from exc
    return bound.args, bound.kwargs


def _invoke(fn, args, kwargs):
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


class _AsyncCancellationScope:
    """Join asyncio cancellation to the durable run it created in a worker."""

    def __init__(self):
        self._condition = threading.Condition()
        self._runtime = None
        self._run_id = None
        self._requested = False

    def bind(self, runtime, run_id):
        with self._condition:
            self._runtime = runtime
            self._run_id = run_id
            self._condition.notify_all()

    def request(self):
        with self._condition:
            self._requested = True
            self._condition.notify_all()

    def cancel_once(self, timeout=0.05):
        with self._condition:
            if self._runtime is None:
                self._condition.wait(timeout)
            runtime, run_id = self._runtime, self._run_id
        if runtime is None:
            return False
        runtime.cancel(run_id)
        return True


def _bind_async_cancellation(runtime, run_id):
    scope = _ASYNC_CANCELLATION.get()
    if scope is not None:
        scope.bind(runtime, run_id)


async def _async_call(fn, *args, **kwargs):
    scope = _AsyncCancellationScope()
    token = _ASYNC_CANCELLATION.set(scope)
    try:
        task = asyncio.create_task(asyncio.to_thread(fn, *args, **kwargs))
    finally:
        _ASYNC_CANCELLATION.reset(token)
    cancelled = False
    cancellation_settled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            if not cancelled:
                scope.request()
            cancelled = True
            # Retry briefly after an Unknown result. This closes the narrow
            # race where durable intent exists but the native adapter has not
            # yet registered ownership of its just-starting process.
            for _ in range(10):
                if cancellation_settled or task.done():
                    break
                attempt = asyncio.create_task(asyncio.to_thread(scope.cancel_once))
                while True:
                    try:
                        cancellation_settled = await asyncio.shield(attempt)
                        break
                    except asyncio.CancelledError:
                        cancelled = True
                        if attempt.done():
                            try:
                                cancellation_settled = attempt.result()
                            except (BotpipeError, KeyError):
                                pass
                            break
                    except (BotpipeError, KeyError):
                        # The durable request remains the authority. Retry while
                        # the worker is alive so a process that wins a start race
                        # is still asked to stop once the adapter owns it.
                        break
                if not cancellation_settled and not task.done():
                    try:
                        await asyncio.sleep(0.02)
                    except asyncio.CancelledError:
                        cancelled = True
            if task.done():
                if not cancelled:
                    result = task.result()
                break
        except BaseException:
            if cancelled:
                break
            raise
    if cancelled:
        raise asyncio.CancelledError
    return result


def _callable_reference(value):
    module = getattr(value, "__module__", None)
    qualname = getattr(value, "__qualname__", None)
    if type(module) is not str or type(qualname) is not str:
        raise TypeError(
            "Callable replay identity requires a module and qualified name; "
            "provide an explicit activity or workflow name"
        )
    return f"{module}:{qualname}"


def _logical_binding(value, *, seen, depth):
    """Describe data explicitly bound into a partial."""

    if callable(value):
        surface = _logical_callable_surface(value, _seen=seen, _depth=depth)
        declared_data = isinstance(value, (BaseModel, Enum)) or (
            dataclasses.is_dataclass(value) and not isinstance(value, type)
        )
        if declared_data:
            try:
                codec.encode(value)
            except TypeError:
                # Some declared data objects have deliberately non-durable state.
                # Preserve their existing opaque callable-reference behavior.
                pass
            else:
                # A callable instance used as an explicit partial argument is data as
                # well as code. Preserve its supported durable state while keeping
                # implementation identity source-free. Callable receivers otherwise
                # remain opaque logical references.
                return {
                    "binding": "callable_data",
                    "callable": surface,
                    "value": value,
                }
        return {
            "binding": "callable",
            "value": surface,
        }
    return {"binding": "value", "value": value}


def _logical_callable_surface(value, *, explicit_name=None, _seen=None, _depth=0):
    """Return the source-free callable surface used for replay matching."""

    if _depth > 100:
        raise TypeError("Callable replay identity exceeds maximum nesting depth")
    seen = set() if _seen is None else _seen
    marker = id(value)
    if marker in seen:
        raise TypeError("Callable replay identity contains a cycle")
    seen.add(marker)
    try:
        try:
            namespace = object.__getattribute__(value, "__dict__")
        except (AttributeError, TypeError):
            namespace = {}
        declared_name = namespace.get("_botpipe_explicit_name")
        if explicit_name is None and declared_name is not None:
            explicit_name = declared_name
        if (
            type(value).__module__ == __name__
            and type(value).__name__ == "Workflow"
            and "fn" in vars(value)
        ):
            return _logical_callable_surface(
                value.fn,
                explicit_name=value._explicit_name,
                _seen=seen,
                _depth=_depth + 1,
            )
        if isinstance(value, functools.partial):
            return {
                "kind": "partial",
                "callable": _logical_callable_surface(
                    value.func,
                    explicit_name=explicit_name,
                    _seen=seen,
                    _depth=_depth + 1,
                ),
                "args": [
                    _logical_binding(item, seen=seen, depth=_depth + 1)
                    for item in value.args
                ],
                "kwargs": [
                    [
                        key,
                        _logical_binding(item, seen=seen, depth=_depth + 1),
                    ]
                    for key, item in (value.keywords or {}).items()
                ],
            }
        if explicit_name is not None:
            return {"kind": "named", "name": str(explicit_name)}
        if inspect.ismethod(value):
            owner = (
                value.__self__
                if isinstance(value.__self__, type)
                else type(value.__self__)
            )
            return {
                "kind": "method",
                "callable": _callable_reference(value.__func__),
                "owner": _callable_reference(owner),
            }
        if inspect.isfunction(value) or inspect.isbuiltin(value):
            return {"kind": "function", "reference": _callable_reference(value)}
        if inspect.ismethoddescriptor(value) and hasattr(value, "__objclass__"):
            return {
                "kind": "method_descriptor",
                "reference": (
                    f"{_callable_reference(value.__objclass__)}.{value.__name__}"
                ),
            }
        if inspect.isclass(value):
            return {"kind": "type", "reference": _callable_reference(value)}
        if callable(value):
            return {"kind": "instance", "type": _callable_reference(type(value))}
        raise TypeError(f"Expected a callable, got {type(value).__name__}")
    finally:
        seen.remove(marker)


class Workflow:
    """Callable definition. A workflow's public body remains ordinary Python."""

    def __init__(self, fn, *, name=None, version="1", policy=None):
        functools.update_wrapper(self, fn)
        self.fn = fn
        self.name = name or getattr(fn, "__name__", type(fn).__name__)
        self._explicit_name = name
        self.version = str(version)
        self.policy = Policy.resolve(policy)
        from .provenance import (
            capture_definition_sources,
            capture_orchestration_sources,
        )

        descriptor = describe_callable(self)
        try:
            self._source_context = source_context(self, graph=descriptor)
        except Exception:  # noqa: BLE001 - source evidence is observational
            self._source_context = SourceContext(None, None, None, ())
        try:
            self._source_identity_at_definition = capture_definition_sources(
                self, graph=descriptor, context=self._source_context
            )
            self._orchestration_sources_at_definition = (
                capture_orchestration_sources(
                    self, graph=descriptor, context=self._source_context
                )
                if self._source_boundaries
                else None
            )
        except Exception:  # noqa: BLE001 - source evidence is observational
            self._source_identity_at_definition = None
            self._orchestration_sources_at_definition = None

    @property
    def _source_boundaries(self):
        return self._source_context.owned_boundaries

    def __call__(self, *args, **kwargs):
        ctx = current_run()
        if inspect.iscoroutinefunction(self.fn):
            return _async_call(ctx.invoke, self, *args, **kwargs)
        return ctx.invoke(self, *args, **kwargs)

    @property
    def logical_identity(self):
        return _logical_callable_surface(self.fn, explicit_name=self._explicit_name)

    @property
    def fingerprint(self):
        return _hash(
            {
                "name": self.name,
                "version": self.version,
                "policy": self.policy.to_dict(),
                "source": _function_version(self.fn),
                "source_modules": self._orchestration_sources_at_definition,
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


def activity(fn=None, *, retry_safe=True, retries=0, name=None):
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
        operation_name = (
            str(name)
            if name is not None
            else getattr(
                function,
                "__qualname__",
                f"{type(function).__module__}.{type(function).__qualname__}",
            )
        )

        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            ctx = current_run()
            if _ACTIVITY.get():
                raise BotpipeError(
                    "An activity cannot call another managed activity; use an ordinary helper"
                )
            inputs = {
                "activity": _logical_callable_surface(function, explicit_name=name),
                "args": args,
                "kwargs": list(kwargs.items()),
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
                        name=operation_name,
                    )
                except BotpipeError:
                    # Runtime/replay failures are not activity failures and may
                    # never advance execution to a new retry identity.
                    raise
                except Exception as exc:
                    last = exc
            raise last

        wrapped._botpipe_explicit_name = name

        if inspect.iscoroutinefunction(function):

            @functools.wraps(function)
            async def async_wrapped(*args, **kwargs):
                return await _async_call(wrapped, *args, **kwargs)

            async_wrapped._botpipe_explicit_name = name
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
    for annotation in function.__annotations__.values():
        codec.register_annotation(annotation)


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
        input_candidate=None,
        workspace_leases=(),
    ):
        self.client, self.journal, self.definition = client, client.journal, definition
        self.run_id, self.task_id = metadata["run_id"], metadata["task_id"]
        self.limits = (
            parent.limits if parent is not None else RunLimits.from_record(metadata)
        )
        self.workspace = client.workspace
        self.workspace_leases = (
            parent.workspace_leases if parent else workspace_leases
        )
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
        boundary = definition._source_context.origin_boundary
        self.source_dir = (
            (boundary if boundary and boundary.is_dir() else boundary.parent)
            if boundary
            else parent.source_dir
            if parent is not None
            else self.workspace
        )
        base_policy = parent.policy if parent else Policy.from_dict(
            metadata.get("policy", {})
        )
        self.policy = Policy.resolve(base_policy, definition.policy)
        # Applied lazily only when a new physical attempt may dispatch. Keeping
        # it separate preserves historical operation fingerprints and permits
        # committed replay/conservative recovery under changed deployment rules.
        self.current_policy_ceiling = (
            parent.current_policy_ceiling if parent else client.policy
        )
        self.parallel_branch = parallel_branch or (
            parent.parallel_branch if parent else False
        )
        self._session_locks = parent._session_locks if parent else {}
        # Each durable scope records its own first-use family aliases. Strong
        # object keys below keep ephemeral families alive for the execution.
        self._provider_family_bindings = {}
        self._workspace_locks = parent._workspace_locks if parent else {}
        self._guard = parent._guard if parent else threading.RLock()
        self._input_state = parent._input_state if parent else {
            "candidates": dict(input_candidate or {})
        }
        self._execution_lock = threading.RLock()
        self._replay_state = parent._replay_state if parent else {"error": None}
        self.provider_budgets = parent.provider_budgets if parent else ()
        self.execution_id = parent.execution_id if parent else uuid.uuid4().hex
        self.provider_name = metadata.get("provider")
        self.provider_config = dict(metadata.get("provider_config", {}))
        self.provider_defaults = dict(metadata.get("provider_defaults", {}))
        self._default_provider = None

    @property
    def provider(self) -> Provider:
        """One memoized configured provider for this workflow scope."""

        if self._default_provider is None:
            from .provider import Provider

            self._default_provider = Provider(runtime=self.client)
        return self._default_provider

    def take_input_candidate(self, operation_id):
        """Consume a submitted answer only from the input operation it targets."""
        with self._guard:
            candidates = self._input_state["candidates"]
            if operation_id not in candidates:
                return _UNSET
            return candidates.pop(operation_id)

    @property
    def operation_id(self):
        return _OPERATION.get()

    def check_cancelled(self):
        """Fence a new physical dispatch after a durable cancellation request."""

        requested = self.journal.run(self.run_id).get("cancel_requested_at")
        if requested is not None:
            raise UncertainOperation(
                "Execution cancellation was requested; no new attempt may dispatch",
                self.operation_id,
            )

    def check_replay_fence(self):
        if self._replay_state["error"] is not None:
            raise self._replay_state["error"]

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
        self.check_replay_fence()
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
        except (ReplayMismatch, UncertainOperation) as exc:
            # A caught application exception cannot make divergent history
            # valid or authorize additional effects/observations in this run.
            # Child contexts share this fence with their root context.
            self._replay_state["error"] = exc
            raise
        finally:
            self._execution_lock.release()

    def save_response(
        self,
        operation_id,
        response,
        *,
        session_update=None,
    ):
        _persist_response(
            self.journal,
            operation_id,
            response,
            session_update=session_update,
        )

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
        fingerprint_inputs = codec.encode(inputs)
        fingerprint = _hash({"kind": kind, "name": name, "inputs": fingerprint_inputs})
        durable_inputs = (
            {**inputs, "retry_safe": retry_safe} if kind == "activity" else inputs
        )
        encoded_inputs = (
            codec.encode(durable_inputs) if kind == "activity" else fingerprint_inputs
        )
        record = self.journal.get(operation_id)
        if record is not None:
            if record["fingerprint"] != fingerprint or record["kind"] != kind:
                raise ReplayMismatch(
                    f"Operation {operation_id} changed ({record['kind']} -> {kind}); start a new run"
                )
            if record["status"] == "completed":
                if kind in {"provider", "decision"}:
                    try:
                        from .streaming import mark_stream_replay
                    except ImportError:
                        pass
                    else:
                        mark_stream_replay(self.run_id, operation_id)
                return codec.decode(record["result"])
            if record["status"] == "failed":
                _preflight_exception_record(record["error"])
                raise _restore_exception(record["error"])
            if kind == "provider":
                provider_checkpoint = ProviderCheckpoint.from_record(
                    record.get("response")
                )
                authorized = isinstance(provider_checkpoint, RetryAuthorizedCheckpoint)
            else:
                authorized = bool(
                    (record.get("response") or {}).get("retry_authorized")
                )
            automatic_retry = retry_safe
            if kind == "activity":
                recorded_inputs = codec.decode(record["inputs"])
                automatic_retry = (
                    retry_safe
                    and isinstance(recorded_inputs, dict)
                    and recorded_inputs.get("retry_safe") is True
                )
            if recover is None and not (automatic_retry or orchestrator or authorized):
                raise UncertainOperation(
                    f"Operation {operation_id} was interrupted; reconcile it before retrying",
                    operation_id,
                )
            if authorized and recover is None and kind != "provider":
                self.save_response(
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
                limit=self.limits.max_operations,
            )
        token = _OPERATION.set(operation_id)
        try:
            result = (
                recover() if record is not None and recover is not None else execute()
            )
            encoded_result = codec.encode(result)
            _commit_or_confirm(
                self.journal,
                operation_id,
                lambda: self.journal.finish(operation_id, encoded_result),
                {"status": "completed", "result": encoded_result},
                "Operation result could not be confirmed committed; resume to reconcile it",
            )
            return result
        except (Suspension, ReplayMismatch):
            raise
        except Exception as exc:
            # A submitted input is still tentative while its operation is
            # waiting. Unexpected validator/runtime bugs must propagate to the
            # run boundary without turning that request into a durable failure.
            current = self.journal.get(operation_id)
            if (
                kind == "input"
                and current is not None
                and current["status"] == "waiting"
            ):
                raise
            recorded_error = _finalize_exception_record(_exception_record(exc))
            _commit_or_confirm(
                self.journal,
                operation_id,
                lambda: self.journal.fail(operation_id, recorded_error),
                {"status": "failed", "error": recorded_error},
                "Operation failure could not be confirmed committed; resume to reconcile it",
            )
            if not recorded_error.get("restorable", True):
                raise _restore_exception(recorded_error) from exc
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
            try:
                value = _invoke(definition.fn, args, kwargs)
            except Exception:
                child.assert_consumed()
                raise
            child.assert_consumed()
            return value
        finally:
            _CURRENT.reset(token)

    def invoke(self, definition, *args, **kwargs):
        if not isinstance(definition, Workflow):
            raise TypeError("Child workflows must use @workflow")
        inputs = {
            "workflow": definition.logical_identity,
            "args": args,
            "kwargs": list(kwargs.items()),
        }

        def execute():
            return self._child(
                definition, args, kwargs, f"{self.scope}/child-{self.ordinal - 1}"
            )

        return self.operation(
            "child",
            inputs,
            execute,
            orchestrator=True,
            name=definition.name,
        )

    def scope_call(self, scope, definition):
        # ThreadPoolExecutor does not propagate context variables. Re-enter the
        # owning runtime's restoration registry in each parallel branch.
        with codec.use_contract_registry(self.client.contract_registry):
            return self._child(
                definition, (), {}, f"{self.scope}/{scope}", parallel_branch=True
            )

    def assert_consumed(self):
        self.check_replay_fence()
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


def ask_human(question, *, returns=str):
    ctx = current_run()
    codec.preflight(returns, path="$.answer")
    schema = codec.schema_for(returns)

    def execute():
        record = ctx.journal.get(ctx.operation_id)
        if record["status"] == "response":
            response = record["response"]
            if "validated_answer" in response:
                return codec.decode(response["validated_answer"])
            raise ReplayMismatch("Recorded input is missing its validated answer")
        candidate = ctx.take_input_candidate(ctx.operation_id)
        if record["status"] == "waiting" and candidate is not _UNSET:
            try:
                value = TypeAdapter(returns).validate_python(candidate)
            except ValidationError as exc:
                raise InputRequired(
                    str(question),
                    ctx.operation_id,
                    {
                        "type": "validation_error",
                        "message": "Answer does not match the requested type",
                        "details": json.loads(
                            exc.json(include_input=False, include_url=False)
                        ),
                    },
                ) from None
            try:
                encoded = codec.encode(value)
            except TypeError as exc:
                raise InputRequired(
                    str(question),
                    ctx.operation_id,
                    {"type": "encoding_error", "message": str(exc)},
                ) from None
            ctx.save_response(ctx.operation_id, {"validated_answer": encoded})
            return value
        waiting = {"question": str(question), "schema": schema}
        _commit_or_confirm(
            ctx.journal,
            ctx.operation_id,
            lambda: ctx.journal.wait_input(ctx.operation_id, waiting),
            {"status": "waiting", "response": waiting},
            "Input checkpoint could not be confirmed committed; resume to reconcile it",
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
    definitions = tuple(
        Workflow(fn, name=getattr(fn, "__name__", f"branch-{index}"))
        for index, fn in enumerate(calls)
    )
    inputs = {
        "identity": "botpipe.parallel-branches.v3",
        "calls": [_logical_callable_surface(fn) for fn in calls],
        "settle": settle,
    }

    def execute():
        group = ctx.ordinal - 1
        if not calls:
            return []
        with ThreadPoolExecutor(max_workers=max_workers or len(calls)) as pool:
            futures = [
                pool.submit(
                    ctx.scope_call,
                    f"parallel-{group}/{index}",
                    definition,
                )
                for index, definition in enumerate(definitions)
            ]
            values = []
            errors = []
            for future in futures:
                try:
                    values.append(future.result())
                except BaseException as exc:
                    errors.append(exc)
                    values.append({"error": str(exc), "type": type(exc).__name__})
            if ctx._replay_state["error"] is not None:
                raise ctx._replay_state["error"]
            suspended = next((e for e in errors if not isinstance(e, Exception)), None)
            if suspended is not None:
                raise suspended
            if errors and settle == "all":
                raise errors[0]
            return values

    return ctx.operation(
        "parallel",
        inputs,
        execute,
        orchestrator=True,
        name="parallel",
    )


async def aparallel(*calls, max_workers=None, settle="all"):
    """Async parallel composition with the same durable branch identities."""

    return await _async_call(
        parallel, *calls, max_workers=max_workers, settle=settle
    )


class Botpipe:
    def __init__(
        self,
        workspace=".",
        provider=_UNSET,
        *,
        state_dir=None,
        policy=None,
        max_operations=_UNSET,
        timeout=_UNSET,
        provider_config=None,
        provider_defaults=None,
        contract_registry=None,
    ):
        from .providers import get_provider

        if provider is _UNSET:
            from .config import load_config

            configured = load_config(workspace).client_kwargs()
            workspace = configured["workspace"]
            provider = configured["provider"]
            if state_dir is None:
                state_dir = configured["state_dir"]
            if policy is None:
                policy = configured["policy"]
            if provider_config is None:
                provider_config = configured["provider_config"]
            if provider_defaults is None:
                provider_defaults = configured["provider_defaults"]
            if max_operations is _UNSET:
                max_operations = configured["max_operations"]
            if timeout is _UNSET:
                timeout = configured["timeout"]

        if max_operations is _UNSET:
            max_operations = 1000
        if timeout is _UNSET:
            timeout = 3600

        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ValueError(f"Workspace is not a directory: {self.workspace}")
        self.state_dir = (
            Path(state_dir).resolve()
            if state_dir
            else self.workspace / ".botpipe-v2"
        )
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.provider_config = dict(provider_config or {})
        self.provider_defaults = dict(provider_defaults or {})
        # Runtime restoration resources are deliberately not journaled. The
        # recorded structural contract remains the authority for each entry.
        self.contract_registry = codec.normalize_contract_registry(contract_registry)
        from .config import validate_non_secret_settings

        validate_non_secret_settings(
            self.provider_config, path="provider configuration"
        )
        validate_non_secret_settings(
            self.provider_defaults, path="provider defaults"
        )
        self.policy = Policy.resolve(policy)
        validate_non_secret_settings(
            self.policy.to_dict(), path="runtime policy"
        )
        constructed_adapter = isinstance(provider, str)
        self.provider = (
            get_provider(provider, config=self.provider_config)
            if isinstance(provider, str)
            else provider
        )
        if provider is not None and not any(
            callable(getattr(self.provider, method, None))
            for method in ("run", "decide")
        ):
            raise TypeError("Provider must implement a supported capability")
        self.provider_name = (
            getattr(self.provider, "name", type(self.provider).__name__)
            if self.provider is not None
            else None
        )
        self._adapter_lock = threading.RLock()
        self._adapter_cache = {}
        self._owned_adapters = set()
        if self.provider is not None:
            key = self._adapter_key(self.provider_name, self.provider_config)
            self._adapter_cache[key] = self.provider
            if constructed_adapter:
                self._owned_adapters.add(id(self.provider))
        self.limits = RunLimits(max_operations, timeout)
        self.journal = Journal(self.state_dir / "state.sqlite3")
        self._workspace_coordinator = WorkspaceCoordinator()

    @property
    def max_operations(self):
        return self.limits.max_operations

    @max_operations.setter
    def max_operations(self, value):
        self.limits = RunLimits(value, self.limits.timeout)

    @property
    def timeout(self):
        return self.limits.timeout

    @timeout.setter
    def timeout(self, value):
        self.limits = RunLimits(self.limits.max_operations, value)

    @staticmethod
    def _adapter_key(name, config):
        return (
            name,
            json.dumps(
                config, sort_keys=True, separators=(",", ":"), allow_nan=False
            ),
        )

    def resolve_adapter(self, name, config=None):
        """Resolve and memoize a runtime-owned adapter resource."""

        from .config import validate_non_secret_settings
        from .providers import get_provider

        config = dict(config or {})
        validate_non_secret_settings(config, path=f"provider {name} configuration")
        key = self._adapter_key(name, config)
        with self._adapter_lock:
            adapter = self._adapter_cache.get(key)
            if adapter is None:
                adapter = get_provider(name, config=config)
                self._adapter_cache[key] = adapter
                self._owned_adapters.add(id(adapter))
            return adapter

    def _definition(self, value):
        if isinstance(value, str):
            from .discovery import resolve_workflow

            value = resolve_workflow(value, workspace=self.workspace)
        if not isinstance(value, Workflow):
            raise TypeError("Expected a @workflow function or workflow reference")
        # Register reconstructed local/generic input types before resume decodes
        # their snapshots. Registration resolves types but never validates values.
        _resolve_annotations(value.fn, {})
        return value

    def _check_run_configuration(self, data):
        # Provider selection is a run snapshot. A changed project default must
        # not retarget recorded families during recovery. Current policy is
        # applied separately when a future dispatch is prepared.
        for field in ("provider_config", "provider_defaults", "policy"):
            if not isinstance(data.get(field, {}), dict):
                raise ReplayMismatch(f"Recorded run {field} is malformed")
        self._recorded_workspace_mode(data)

    @staticmethod
    def _recorded_workspace_mode(data):
        # Runs created before root modes were recorded held the conservative
        # write claim. Preserve that safe journal meaning without accepting an
        # explicitly malformed value.
        if "workspace_mode" not in data:
            return "write"
        mode = data.get("workspace_mode")
        if mode not in {"read", "write"}:
            raise ReplayMismatch("Recorded run workspace mode is malformed")
        if mode == "read" and not Botpipe._is_recorded_standalone_reader(data):
            raise ReplayMismatch(
                "Recorded read workspace mode is inconsistent with the workflow"
            )
        return mode

    @staticmethod
    def _is_recorded_standalone_reader(data):
        """Recognize only the durable private standalone query/generate shape."""

        from .provider import _standalone_operation

        if (
            data.get("workflow") != _standalone_operation.name
            or data.get("module") != _standalone_operation.fn.__module__
            or data.get("function") != _standalone_operation.fn.__qualname__
            or data.get("workflow_call")
            != codec.encode(_standalone_operation.logical_identity)
            or data.get("kwargs") != codec.encode({})
        ):
            return False
        args = data.get("args")
        if (
            type(args) is not dict
            or set(args) != {"$botpipe", "value"}
            or args.get("$botpipe") != "tuple"
            or type(args.get("value")) is not list
            or len(args["value"]) != 1
        ):
            return False
        encoded_spec = args["value"][0]
        if (
            type(encoded_spec) is not dict
            or set(encoded_spec) != {"$botpipe", "value"}
            or encoded_spec.get("$botpipe") != "dict"
            or type(encoded_spec.get("value")) is not dict
        ):
            return False
        spec = encoded_spec["value"]
        return (
            set(spec) == {"selection", "session", "operation", "prompt", "options"}
            and spec.get("operation") in {"query", "generate"}
        )

    @staticmethod
    def _new_workspace_mode(definition, args):
        # Only the exact private standalone wrapper can narrow root ownership.
        # User workflows remain writers even when their current body only reads.
        from .provider import _standalone_operation

        if definition is _standalone_operation and len(args) == 1:
            spec = args[0]
            if type(spec) is dict and spec.get("operation") in {"query", "generate"}:
                return "read"
        return "write"

    @contextmanager
    def _ownership(
        self, run_id, *, workspace=None, parent=(), recovery=False, operation_id=None
    ):
        target = self.workspace if workspace is None else workspace
        with self._workspace_coordinator.claim(
            target, self.journal, run_id, "write", parent=parent, recovery=recovery,
            operation_id=operation_id
        ) as lease:
            yield lease

    @contextmanager
    def _read_ownership(
        self, run_id, *, workspace=None, parent=(), recovery=False,
        operation_id=None
    ):
        target = self.workspace if workspace is None else workspace
        with self._workspace_coordinator.claim(
            target, self.journal, run_id, "read", parent=parent,
            recovery=recovery,
            operation_id=operation_id
        ) as lease:
            yield lease

    def run(self, definition, *args, task_id=None, run_id=None, **kwargs):
        with codec.use_contract_registry(self.contract_registry):
            return self._run(
                definition, *args, task_id=task_id, run_id=run_id, **kwargs
            )

    def _run(self, definition, *args, task_id=None, run_id=None, **kwargs):
        definition = self._definition(definition)
        args, kwargs = _validate_args(definition.fn, args, kwargs)
        context = definition._source_context
        limits = self.limits
        task_id = task_id or uuid.uuid4().hex[:12]
        run_id = run_id or uuid.uuid4().hex
        for label, value in (("task_id", task_id), ("run_id", run_id)):
            if not isinstance(value, str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value
            ):
                raise ValueError(f"{label} must be a safe identifier")
        folder = self.state_dir / "tasks" / task_id / "runs" / run_id
        encoded_args = codec.encode(args)
        encoded_kwargs = codec.encode(kwargs)
        data = {
            "run_id": run_id,
            "task_id": task_id,
            "workflow": definition.name,
            "workflow_call": codec.encode(definition.logical_identity),
            "module": getattr(
                definition.fn, "__module__", type(definition.fn).__module__
            ),
            "function": getattr(
                definition.fn, "__qualname__", type(definition.fn).__qualname__
            ),
            "source_file": str(context.origin_source)
            if context.origin_source
            else None,
            "version": _observed_workflow_fingerprint(definition),
            "args": encoded_args,
            "kwargs": encoded_kwargs,
            "status": "created",
            "folder": str(folder),
            "provider": self.provider_name,
            "provider_config": self.provider_config,
            "provider_defaults": self.provider_defaults,
            "policy": self.policy.to_dict(),
            "workspace_mode": self._new_workspace_mode(definition, args),
            "max_operations": limits.max_operations,
            "timeout": limits.timeout,
            "created_at": now(),
            "error": None,
        }
        # A claim left by a crash must always refer to an existing run, even
        # when the crash precedes the first operation. Failed admission removes
        # only the untouched placeholder created by this call.
        self.journal.create_run(data)
        try:
            ownership = (
                self._read_ownership
                if data["workspace_mode"] == "read"
                else self._ownership
            )
            with ownership(run_id) as lease:
                data["provenance_start"] = capture_workflow_provenance(
                    definition, self.workspace
                )
                self.journal.update_run(
                    run_id, provenance_start=data["provenance_start"]
                )
                return self._execute(
                    definition,
                    data,
                    args,
                    kwargs,
                    provenance_start=data["provenance_start"],
                    workspace_leases=(lease,),
                )
        except RunBusy:
            self.journal.discard_created_run(run_id)
            raise

    async def arun(self, definition, *args, **kwargs):
        # One runtime and one provider boundary. Cancellation joins the worker;
        # it never reports a stopped workflow while the worker still edits files.
        return await _async_call(self.run, definition, *args, **kwargs)

    def resume(
        self,
        run_id,
        *,
        answers=None,
        workflow=None,
        max_operations=None,
        timeout=None,
    ):
        with codec.use_contract_registry(self.contract_registry):
            return self._resume(
                run_id,
                answers=answers,
                workflow=workflow,
                max_operations=max_operations,
                timeout=timeout,
            )

    def _resume(
        self,
        run_id,
        *,
        answers=None,
        workflow=None,
        max_operations=None,
        timeout=None,
    ):
        # An invalid identifier must not create an orphan claim that can never
        # be reconciled. Re-read after admission for the current committed state.
        initial = self.journal.run(run_id)
        mode = self._recorded_workspace_mode(initial)
        ownership = self._read_ownership if mode == "read" else self._ownership
        with ownership(run_id, recovery=True) as lease:
            data = self.journal.run(run_id)
            self._check_run_configuration(data)
            operations = self.journal.operations(run_id)

            def recorded_definition():
                reference = f"{data['module']}:{data['function']}"
                try:
                    return self._definition(reference)
                except (
                    ImportError,
                    AttributeError,
                    LookupError,
                    TypeError,
                    ValueError,
                    BotpipeError,
                ):
                    if not data.get("source_file") or "<locals>" in data["function"]:
                        raise BotpipeError(
                            "Pass workflow= when resuming a local workflow function"
                        )
                    return self._definition(f"{data['source_file']}:{data['function']}")

            definition = self._definition(workflow) if workflow is not None else None
            if data["status"] == "completed":
                try:
                    _preflight_recorded_contracts(data, operations)
                except ReplayMismatch as contract_error:
                    if definition is not None:
                        raise
                    try:
                        definition = recorded_definition()
                    except Exception:  # noqa: BLE001 - preserve contract diagnosis
                        raise contract_error
                    _preflight_recorded_contracts(data, operations)
                value = codec.decode(data["value"])
                artifacts, usage = self._outputs(run_id)
                return RunResult(
                    run_id,
                    data["task_id"],
                    "completed",
                    value,
                    artifacts,
                    None,
                    None,
                    Path(data["folder"]),
                    usage,
                )
            if definition is None:
                definition = recorded_definition()
            _preflight_recorded_contracts(data, operations)
            if codec.encode(definition.logical_identity) != data["workflow_call"]:
                raise ReplayMismatch(
                    "Workflow identity changed; resume with the recorded workflow name "
                    "or callable"
                )
            changes = {}
            limits = RunLimits(
                data["max_operations"] if max_operations is None else max_operations,
                data["timeout"] if timeout is None else timeout,
            )
            if max_operations is not None:
                if limits.max_operations < data["max_operations"]:
                    raise ValueError(
                        "Resume operation budget must be at least the recorded budget"
                    )
                changes["max_operations"] = limits.max_operations
            if timeout is not None:
                changes["timeout"] = limits.timeout
            if changes:
                data.update(changes)
                self.journal.update_run(run_id, **changes)
                self.journal.event(run_id, "run_limits_updated", changes)
            cancellation_inferred = (
                data.get("cancel_requested_at") is not None
                and data.get("cancellation_confirmed_at") is None
                and _cancellation_was_not_dispatched(operations)
            )
            if data.get("cancel_requested_at") is not None and (
                data.get("cancellation_confirmed_at") is not None
                or cancellation_inferred
            ):
                # A confirmed stop (or an authoritative completion that won
                # the race) permits replay/recovery. A cancellation checkpoint
                # with completed restoration is equally authoritative: no
                # native attempt existed to stop. The event history remains;
                # only the active dispatch fence is acknowledged here.
                data["cancel_requested_at"] = None
                data["cancellation_confirmed_at"] = None
                self.journal.update_run(
                    run_id,
                    cancel_requested_at=None,
                    cancellation_confirmed_at=None,
                    updated_at=now(),
                )
                self.journal.event(
                    run_id,
                    "cancellation_acknowledged",
                    {"not_dispatched": cancellation_inferred},
                )
            if answers is None:
                answers = {}
            if not isinstance(answers, dict):
                raise TypeError("answers must map operation ids to answers")
            input_candidate = {}
            for operation_id, answer in answers.items():
                if not isinstance(operation_id, str):
                    raise TypeError("answer operation ids must be strings")
                record = self.journal.get(operation_id)
                if (
                    record is None
                    or record["run_id"] != run_id
                    or record["kind"] != "input"
                    or record["status"] != "waiting"
                ):
                    raise ValueError(
                        f"Run is not waiting for answer operation {operation_id}"
                    )
                input_candidate[operation_id] = answer
            decoded_args = codec.decode(data["args"])
            decoded_kwargs = codec.decode(data["kwargs"])
            return self._execute(
                definition,
                data,
                decoded_args,
                decoded_kwargs,
                input_candidate=input_candidate,
                workspace_leases=(lease,),
            )

    async def aresume(self, run_id, **kwargs):
        return await _async_call(self.resume, run_id, **kwargs)

    def _execute(
        self,
        definition,
        data,
        args,
        kwargs,
        *,
        input_candidate=None,
        provenance_start=None,
        workspace_leases=(),
    ):
        _bind_async_cancellation(self, data["run_id"])
        ctx = RunContext(
            self, data, definition, input_candidate=input_candidate,
            workspace_leases=workspace_leases,
        )
        status = "completed"
        value = None
        error = None
        failure = None
        pending = data.get("pending_input")
        if provenance_start is None:
            provenance_start = capture_workflow_provenance(definition, self.workspace)
        self.journal.event(
            ctx.run_id,
            "execution_revision",
            {"phase": "start", "provenance": provenance_start},
        )
        self.journal.update_run(ctx.run_id, status="running", error=None)
        token = _CURRENT.set(ctx)
        try:
            value = _invoke(definition.fn, args, kwargs)
            if self.journal.run(ctx.run_id).get("cancel_requested_at") is not None:
                raise UncertainOperation(
                    "Execution was cancelled before its result was accepted",
                    ctx.operation_id,
                )
            ctx.assert_consumed()
            encoded = codec.encode(value)
            pending = None
        except InputRequired as exc:
            status = "awaiting_input"
            error = None
            record = self.journal.get(exc.operation_id)
            pending = {"operation_id": exc.operation_id, **record["response"]}
            if exc.diagnostic is not None:
                pending["diagnostic"] = exc.diagnostic
            encoded = None
        except BudgetExceeded as exc:
            exc.run_id = ctx.run_id
            if not getattr(exc, "operation_id", None):
                exc.operation_id = ctx.operation_id
            failure = exc
            status = "budget_exceeded"
            error = str(exc)
            pending = None
            encoded = None
        except UncertainOperation as exc:
            exc.run_id = ctx.run_id
            if not getattr(exc, "operation_id", None):
                exc.operation_id = ctx.operation_id
            failure = exc
            status = "interrupted"
            error = str(exc)
            if pending is not None:
                waiting = self.journal.get(pending.get("operation_id"))
                if waiting is None or waiting["status"] != "waiting":
                    pending = None
            encoded = None
        except KeyboardInterrupt:
            status = "interrupted"
            error = "Execution interrupted"
            if pending is not None:
                waiting = self.journal.get(pending.get("operation_id"))
                if waiting is None or waiting["status"] != "waiting":
                    pending = None
            encoded = None
        except Exception as exc:
            failure = exc
            try:
                ctx.assert_consumed()
            except ReplayMismatch as mismatch:
                failure = mismatch
            status = "failed"
            error = f"{type(failure).__name__}: {failure}"
            pending = None
            encoded = None
        finally:
            _CURRENT.reset(token)
        artifacts, usage = self._outputs(ctx.run_id)
        provenance_end = capture_workflow_provenance(definition, self.workspace)
        self.journal.update_run(
            ctx.run_id,
            status=status,
            value=encoded,
            error=error,
            pending_input=pending,
            usage=usage,
            updated_at=now(),
            provenance_end=provenance_end,
        )
        self.journal.event(
            ctx.run_id,
            "execution_revision",
            {"phase": "end", "provenance": provenance_end},
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
            failure,
        )

    def _outputs(self, run_id):
        from .read_projection import project_run

        projection = project_run(self.journal.snapshot(run_id))
        return projection.artifacts, projection.usage

    def runs(self):
        return self.journal.runs()

    def pending(self, run_id):
        """Return every independently answerable human-input request."""

        run = self.journal.run(run_id)
        diagnostic = run.get("pending_input") or {}
        return tuple(
            {
                "operation_id": record["id"],
                **record["response"],
                **(
                    {"diagnostic": diagnostic["diagnostic"]}
                    if diagnostic.get("operation_id") == record["id"]
                    and "diagnostic" in diagnostic
                    else {}
                ),
            }
            for record in self.journal.operations(run_id)
            if record["kind"] == "input" and record["status"] == "waiting"
        )

    def answer(
        self,
        run_id,
        operation_id,
        value,
        *,
        workflow=None,
        max_operations=None,
        timeout=None,
    ):
        """Submit one answer to the exact pending human-input operation."""

        return self.resume(
            run_id,
            answers={operation_id: value},
            workflow=workflow,
            max_operations=max_operations,
            timeout=timeout,
        )

    def inspect(self, run_id):
        from .read_projection import project_run

        return project_run(self.journal.snapshot(run_id)).inspection()

    def cancel(self, run_id, operation_id=None):
        """Request cancellation without claiming that unknown effects stopped."""

        data = self.journal.run(run_id)
        if data["status"] in {"completed", "failed", "budget_exceeded"}:
            return self.inspect(run_id)
        unfinished = [
            record
            for record in self.journal.operations(run_id)
            if record["status"] not in {"completed", "failed"}
            and record["kind"] in {"provider", "decision"}
            and (operation_id is None or record["id"] == operation_id)
        ]
        # A targeted typo must not leave an otherwise healthy run fenced.  A
        # run-wide request is still journaled when no operation exists yet so
        # a worker racing toward its first dispatch observes the cancellation.
        if operation_id is not None and not unfinished:
            raise KeyError(operation_id)
        requested_at = now()
        self.journal.update_run(
            run_id,
            cancel_requested_at=requested_at,
            updated_at=requested_at,
        )
        self.journal.event(
            run_id,
            "cancellation_requested",
            {"operation_id": operation_id},
            operation_id=operation_id,
        )
        unresolved = []
        for record in unfinished:
            # The cancellation flag was committed before this read. Workers
            # cannot begin a later dispatch after observing that fence, so this
            # checkpoint identifies the attempt targeted by cancel().
            current = self.journal.get(record["id"])
            if current is None or current["status"] in {"completed", "failed"}:
                continue
            record = current
            inputs = codec.decode(record["inputs"])
            name = inputs.get("provider")
            config = inputs.get("provider_config", {})
            adapter = self.resolve_adapter(name, config)
            attempt_identity = None
            provider_checkpoint = None
            if record["kind"] == "provider":
                provider_checkpoint = ProviderCheckpoint.from_record(
                    record.get("response")
                )
                attempt_identity = provider_attempt_identity(provider_checkpoint)
            if isinstance(provider_checkpoint, RespondedCheckpoint):
                outcome = Completed(provider_checkpoint.response)
            else:
                cancel = getattr(adapter, "cancel", None)
                if not callable(cancel):
                    outcome = Unknown(
                        f"{name} does not implement synchronous cancellation"
                    )
                else:
                    try:
                        outcome = cancel(record["id"])
                    except BaseException as exc:
                        outcome = Unknown(f"provider cancellation failed: {exc}")
            if not isinstance(outcome, (Completed, Stopped, Running, Unknown)):
                outcome = Unknown(
                    "provider returned an invalid cancellation outcome"
                )
            if record["kind"] == "provider":
                settled = self.journal.get(record["id"])
                settled_checkpoint = ProviderCheckpoint.from_record(
                    settled.get("response") if settled is not None else None
                )
                settled_identity = provider_attempt_identity(settled_checkpoint)
                if attempt_identity is None:
                    # The worker may have crossed its intent checkpoint while
                    # cancel() was entering the adapter. The post-call intent
                    # is then the only possible dispatched attempt.
                    attempt_identity = settled_identity
                elif (
                    settled_identity is not None
                    and settled_identity != attempt_identity
                ):
                    outcome = Unknown(
                        "Provider attempt changed while cancellation was in progress"
                    )
                if (
                    isinstance(settled_checkpoint, RespondedCheckpoint)
                    and settled_identity == attempt_identity
                    and not isinstance(outcome, Completed)
                ):
                    outcome = Completed(settled_checkpoint.response)
                outcome = provider_recovery_outcome(outcome)
            response_record = None
            if isinstance(outcome, Completed):
                try:
                    response_record = outcome.response.to_record()
                    if type(response_record) is not dict:
                        raise TypeError("terminal response record is not an object")
                    # Prove the record is durable before it reaches Journal.event.
                    json.dumps(response_record, allow_nan=False)
                except (
                    AttributeError,
                    TypeError,
                    ValueError,
                    OverflowError,
                    RecursionError,
                ) as exc:
                    outcome = Unknown(
                        f"provider returned an invalid completed cancellation response: {exc}"
                    )
            outcome_data = {
                "outcome": type(outcome).__name__.lower(),
                "detail": getattr(outcome, "detail", None),
                **(
                    {"attempt": attempt_identity}
                    if attempt_identity is not None
                    else {}
                ),
            }
            if isinstance(outcome, Completed):
                # Keep the authoritative terminal record in durable evidence.
                # The owning worker or subsequent recovery performs the normal
                # checkpoint/session commit rather than duplicating that logic.
                outcome_data["response"] = response_record
            self.journal.event(
                run_id,
                "cancellation_outcome",
                outcome_data,
                operation_id=record["id"],
            )
            if isinstance(outcome, (Running, Unknown)):
                unresolved.append((record["id"], outcome))

        settled_at = now()
        if unresolved:
            operation, outcome = unresolved[0]
            detail = getattr(outcome, "detail", None) or (
                "Provider cancellation was not confirmed stopped"
            )
            self.journal.update_run(
                run_id,
                status="interrupted",
                error=detail,
                cancellation_confirmed_at=None,
                updated_at=settled_at,
            )
            self.journal.event(
                run_id,
                "cancellation_unconfirmed",
                {"operation_ids": [item[0] for item in unresolved]},
            )
            raise UncertainOperation(detail, operation)

        self.journal.event(run_id, "cancellation_confirmed", {})
        self.journal.update_run(
            run_id,
            status="interrupted",
            error="Execution cancelled",
            cancellation_confirmed_at=settled_at,
            updated_at=settled_at,
        )
        return self.inspect(run_id)

    def resolve(
        self,
        run_id,
        operation_id,
        *,
        retry=False,
        response=_UNSET,
        artifact_digests=None,
    ):
        with codec.use_contract_registry(self.contract_registry):
            return self._resolve(
                run_id,
                operation_id,
                retry=retry,
                response=response,
                artifact_digests=artifact_digests,
            )

    def _resolve(
        self,
        run_id,
        operation_id,
        *,
        retry=False,
        response=_UNSET,
        artifact_digests=None,
    ):
        if retry and (response is not _UNSET or artifact_digests is not None):
            raise ValueError("Choose retry=True or a response/artifact reconciliation")
        if not retry and response is _UNSET and artifact_digests is None:
            raise ValueError("Choose retry=True, a response, or artifact_digests")
        # Validate identifiers and manually supplied provider values before any
        # ownership or journal mutation. Re-read after admission for freshness.
        initial = self.journal.run(run_id)
        initial_record = self.journal.get(operation_id)
        if initial_record is None or initial_record["run_id"] != run_id:
            raise KeyError(operation_id)
        if response is not _UNSET and initial_record["kind"] == "provider":
            try:
                response = canonical_provider_response(
                    response, allow_mapping=True
                )
            except ReplayMismatch as exc:
                raise TypeError(str(exc)) from exc
        mode = self._recorded_workspace_mode(initial)
        ownership = self._read_ownership if mode == "read" else self._ownership
        with ownership(run_id, recovery=True) as lease:
            data = self.journal.run(run_id)
            self._check_run_configuration(data)
            operations = self.journal.operations(run_id)
            _preflight_recorded_contracts(data, operations)
            record = self.journal.get(operation_id)
            if record is None or record["run_id"] != run_id:
                raise KeyError(operation_id)
            if record["status"] not in ("started", "response"):
                raise ValueError("Only unfinished operations can be reconciled")
            if record["kind"] not in ("provider", "decision", "activity"):
                raise ValueError(
                    "Only provider turns, decisions, and activities require effect reconciliation"
                )
            if artifact_digests is not None and record["kind"] != "provider":
                raise ValueError("Only provider outputs accept artifact reconciliation")
            old = dict(record.get("response") or {})
            source = "operator"
            if record["kind"] == "provider":
                from .providers import provider_request_from_snapshot

                checkpoint = ProviderCheckpoint.from_record(old)
                if isinstance(checkpoint, NotDispatchedCheckpoint):
                    raise ValueError(
                        "Budget exhausted before dispatch; no effects need reconciliation. "
                        "Start a new run to use different provider budget limits"
                    )
                inputs = codec.decode(record["inputs"])
                adapter = self.resolve_adapter(
                    inputs["provider"],
                    inputs.get("provider_config", {}),
                )
                request_data = checkpoint.request_data or {}
                # A retry marker names the *next* generation; reconcile the
                # attempt whose effects are still awaiting resolution.
                previous = checkpoint.attempt_generation
                request = provider_request_from_snapshot(
                    request_data,
                    operation_id=operation_id,
                    workspace=Path(inputs["workspace"]),
                    output_schema=inputs.get("schema"),
                    timeout=RunLimits.from_record(data).timeout,
                    attempt=previous + 1,
                    provider=adapter.name,
                )

                def reconcile_provider():
                    nonlocal response, retry, source, checkpoint
                    if isinstance(checkpoint, RespondedCheckpoint):
                        # This journaled response already passed the provider
                        # boundary; it is as authoritative as a recovered receipt.
                        outcome = Completed(checkpoint.response)
                    else:
                        outcome = cancellation_evidence(
                            self.journal.events(run_id),
                            operation_id=operation_id,
                            identity=provider_attempt_identity(checkpoint),
                        )
                        if outcome is None:
                            outcome = recover_outcome(adapter, request)
                    outcome = provider_recovery_outcome(outcome)
                    evidence = cancellation_evidence(
                        self.journal.events(run_id),
                        operation_id=operation_id,
                        identity=provider_attempt_identity(checkpoint),
                    )
                    if (
                        isinstance(evidence, Completed)
                        and isinstance(checkpoint, RespondedCheckpoint)
                        and evidence.response.to_record()
                        != checkpoint.response.to_record()
                    ):
                        raise BotpipeError(
                            "Cancellation evidence conflicts with the provider checkpoint"
                        )
                    action = ProviderLifecycle.reconciliation_action(outcome)
                    if action is RecoveryAction.USE_RESPONSE:
                        checkpoint = ProviderLifecycle.completed(
                            checkpoint, outcome.response
                        )
                        response = checkpoint.response
                        retry = False
                        source = "recovered"
                    elif action is RecoveryAction.BLOCK:
                        raise BotpipeError(ProviderLifecycle.blocked_message(outcome))
                    if artifact_digests is not None:
                        from .artifacts import Artifact, ArtifactStore

                        if response is _UNSET:
                            raise ValueError(
                                "Artifact reconciliation also needs the completed or manually supplied response"
                            )
                        declarations = tuple(
                            Artifact.from_record(a) for a in inputs.get("writes", ())
                        )
                        if not declarations:
                            raise ValueError(
                                "This provider operation has no declared artifacts"
                            )
                        store = ArtifactStore(
                            request.receipt_dir.parent,
                            workspace=request.workspace,
                            forbidden_paths=(
                                self.journal.path,
                                self.workspace / ".botpipe-workspace.lock",
                                request.workspace / ".botpipe-workspace.lock",
                            ),
                        )
                        artifact_operation = f"{operation_id}:generation:{previous}"
                        if store.has_capture_evidence(artifact_operation):
                            resolution = (
                                checkpoint.artifact_resolution
                                if isinstance(checkpoint, RespondedCheckpoint)
                                else None
                            )
                            if (resolution or {}).get("digests") != artifact_digests:
                                raise ValueError(
                                    "Artifact capture already has durable evidence; resume it instead"
                                )
                        else:
                            approved = store.check_capture_digests(
                                declarations, artifact_digests
                            )
                            if response is _UNSET:
                                raise ValueError(
                                    "Artifact reconciliation also needs a provider response"
                                )
                            checkpoint = ProviderLifecycle.completed(
                                checkpoint, response
                            )
                            checkpoint = ProviderLifecycle.with_artifact_resolution(
                                checkpoint, approved
                            )

                target = request.workspace.resolve()
                request_policy = request.policy.effective()
                target_ownership = (
                    self._read_ownership
                    if request.operation in {"query", "generate"}
                    or request_policy.sandbox_mode == SandboxMode.READ_ONLY
                    else self._ownership
                )
                with target_ownership(
                    run_id, workspace=target, parent=(lease,), recovery=True,
                    operation_id=operation_id,
                ):
                    reconcile_provider()

                if response is not _UNSET:
                    response = canonical_provider_response(response)
                    checkpoint = ProviderLifecycle.completed(checkpoint, response)
                    session_update = None
                    session_id = inputs.get("session")
                    if session_id is not None and record.get("session_revision") is None:
                        saved_session = self.journal.session(session_id)
                        if saved_session is None:
                            raise ValueError("Recorded provider session is missing")
                        session_update = {
                            "session_id": session_id,
                            "expected_revision": saved_session["revision"],
                            "native_session_id": response.session_id,
                        }
                    _persist_response(
                        self.journal,
                        operation_id,
                        checkpoint.to_record(),
                        session_update=session_update,
                    )
            elif record["kind"] == "decision":
                from .artifacts import ArtifactMap
                from .jev import (
                    DecisionRequest,
                    DecisionResponse,
                    decision_response_from_record,
                )
                from .models import Result
                from .recovery import Stopped

                inputs = codec.decode(record["inputs"])
                adapter = self.resolve_adapter(
                    inputs["provider"],
                    inputs.get("provider_config", {}),
                )
                request = DecisionRequest(
                    operation_id=operation_id,
                    state=inputs["state"],
                    questions=inputs["questions"],
                    receipt_dir=Path(data["folder"]) / "receipts",
                    timeout=RunLimits.from_record(data).timeout,
                    settings=inputs.get("settings", {}),
                )
                outcome = recover_outcome(adapter, request)
                if isinstance(outcome, Completed):
                    resolved_response = outcome.response
                    retry = False
                    source = "recovered"
                elif isinstance(outcome, Stopped):
                    resolved_response = None if response is _UNSET else response
                    if resolved_response is None and not retry:
                        raise ValueError(
                            "A stopped decision needs retry=True or a typed response"
                        )
                else:
                    raise BotpipeError(
                        getattr(outcome, "detail", None)
                        or "Decision outcome is uncertain; reconciliation is blocked"
                    )
                if resolved_response is not None:
                    if not isinstance(resolved_response, DecisionResponse):
                        if not isinstance(resolved_response, dict):
                            raise TypeError(
                                "Decision reconciliation needs DecisionResponse or its record"
                            )
                        resolved_response = decision_response_from_record(
                            resolved_response, inputs["questions"]
                        )
                    result = Result(
                        dict(resolved_response.answers),
                        ArtifactMap(),
                        dict(resolved_response.usage),
                        operation_id,
                        run_id=run_id,
                        metadata={
                            **resolved_response.metadata,
                            "model": resolved_response.model,
                        },
                    )
                    _persist_response(
                        self.journal,
                        operation_id,
                        {
                            "phase": "validated",
                            "validated_value": codec.encode(result),
                            "usage": dict(resolved_response.usage),
                        },
                    )
            elif response is not _UNSET:
                result = codec.encode(response)
                _commit_or_confirm(
                    self.journal,
                    operation_id,
                    lambda: self.journal.finish(operation_id, result),
                    {"status": "completed", "result": result},
                    "Resolved activity checkpoint could not be confirmed; inspect it before retrying",
                )
            if retry:
                # Explicit retry is represented by an authorization marker; the
                # original intent/identity remains, and adapters keep old receipts.
                if record["kind"] == "provider":
                    checkpoint = ProviderLifecycle.authorize_retry(checkpoint)
                    retry_record = checkpoint.to_record()
                else:
                    retry_record = {
                        "retry_authorized": True,
                        "generation": old.get("generation", 0)
                        + (0 if old.get("retry_authorized") else 1),
                        **({"request": old["request"]} if "request" in old else {}),
                    }
                _persist_response(self.journal, operation_id, retry_record)
            self.journal.event(
                run_id,
                "operation_reconciled",
                {
                    "retry": retry,
                    "source": source,
                    **(
                        {"artifacts": checkpoint.artifact_resolution}
                        if artifact_digests is not None and record["kind"] == "provider"
                        else {}
                    ),
                },
                operation_id,
            )
            if data.get("cancel_requested_at") is not None:
                self.journal.update_run(
                    run_id,
                    cancel_requested_at=None,
                    cancellation_confirmed_at=None,
                    updated_at=now(),
                )
                self.journal.event(
                    run_id,
                    "cancellation_reconciled",
                    {"operation_id": operation_id},
                    operation_id=operation_id,
                )

    def close(self):
        with self._adapter_lock:
            adapters = [
                adapter
                for adapter in self._adapter_cache.values()
                if id(adapter) in self._owned_adapters
            ]
            self._adapter_cache.clear()
            self._owned_adapters.clear()
        try:
            for adapter in adapters:
                close = getattr(adapter, "close", None)
                if callable(close):
                    close()
        finally:
            self.journal.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args):
        self.close()
