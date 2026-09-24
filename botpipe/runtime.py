"""Durable ordinary functions over recorded, typed operations."""

from __future__ import annotations

import asyncio
import contextvars
import dataclasses
import functools
import hashlib
import inspect
import json
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from enum import Enum
from pathlib import Path
from types import MemberDescriptorType
from typing import get_type_hints

from pydantic import BaseModel, TypeAdapter, ValidationError

from . import codec
from ._callables import describe_callable
from ._code_identity import code_identity
from .errors import (
    ActivityFailed,
    BotpipeError,
    BudgetExceeded,
    CancellationRequested,
    InputRequired,
    ReplayMismatch,
    Suspension,
    UncertainOperation,
)
from .journal import Journal, now
from .limits import RunLimits
from .locks import default_state_dir
from .locks import run_lock as acquire_run_lock
from .locks import session_lock as acquire_session_lock
from .models import RunResult
from .policy import Policy
from .provenance import SourceContext, capture_workflow_provenance, source_context
from .provider_checkpoints import (
    NotDispatchedCheckpoint,
    ProviderCheckpoint,
    ProviderLifecycle,
    RecoveryAction,
    RespondedCheckpoint,
    RetryAuthorizedCheckpoint,
)
from .recovery import Completed, Running, Unknown, recover_outcome

_CURRENT = contextvars.ContextVar("botpipe_run", default=None)
_OPERATION = contextvars.ContextVar("botpipe_operation", default=None)
_ACTIVITY = contextvars.ContextVar("botpipe_activity", default=False)
_CANCELLATION = contextvars.ContextVar("botpipe_cancellation", default=None)
_UNSET = object()
_OPERATOR_FAILURE = "Operation failed by operator resolution"


class _CancellationSignal:
    def __init__(self, parent=None):
        self._event = threading.Event()
        self._parent = parent

    def set(self):
        self._event.set()

    def is_set(self):
        return self._event.is_set() or (
            self._parent is not None and self._parent.is_set()
        )


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


def _persist_response(journal, operation_id, response, session_key=None):
    _commit_or_confirm(
        journal,
        operation_id,
        lambda: journal.response(operation_id, response, session_key=session_key),
        {"status": "response", "response": response},
        "Operation checkpoint could not be confirmed; resume to reconcile it",
    )
    if session_key and response.get("session_id"):
        from .session_bindings import SessionBinding

        request = response.get("request") or {}
        SessionBinding(journal, session_key).advance(
            request.get("operation_key", operation_id), response["session_id"]
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
            if record["kind"] in {"activity", "provider"}:
                if not isinstance(recorded_inputs, dict):
                    raise ReplayMismatch(
                        f"Recorded {record['kind']} inputs are malformed"
                    )
                retry_safe = recorded_inputs.pop("retry_safe", None)
                if type(retry_safe) is not bool and not (
                    record["kind"] == "provider" and retry_safe is None
                ):
                    raise ReplayMismatch(
                        f"Recorded {record['kind']} retry safety is malformed"
                    )
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


def _cancellation_event():
    return _CANCELLATION.get()


async def _async_call(fn, *args, **kwargs):
    cancellation = _CancellationSignal(_CANCELLATION.get())
    token = _CANCELLATION.set(cancellation)
    try:
        task = asyncio.create_task(asyncio.to_thread(fn, *args, **kwargs))
    finally:
        _CANCELLATION.reset(token)
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True
            cancellation.set()
            if task.done():
                try:
                    result = task.result()
                except BaseException as exc:
                    raise asyncio.CancelledError from exc
                break
        except BaseException as exc:
            if cancelled:
                raise asyncio.CancelledError from exc
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
        input_candidate=None,
    ):
        self.client, self.journal, self.definition = client, client.journal, definition
        self.run_id, self.task_id = metadata["run_id"], metadata["task_id"]
        self.limits = (
            parent.limits if parent is not None else RunLimits.from_record(metadata)
        )
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
        boundary = definition._source_context.origin_boundary
        self.source_dir = (
            (boundary if boundary and boundary.is_dir() else boundary.parent)
            if boundary
            else parent.source_dir
            if parent is not None
            else self.workspace
        )
        self.policy = Policy.resolve(
            parent.policy if parent else client.policy, definition.policy
        )
        self._guard = parent._guard if parent else threading.RLock()
        self._input_state = (
            parent._input_state if parent else {"candidate": input_candidate}
        )
        self._execution_lock = threading.RLock()
        self._replay_state = parent._replay_state if parent else {"error": None}
        self.provider_budgets = parent.provider_budgets if parent else ()

    def take_input_candidate(self, operation_id):
        """Consume a submitted answer only from the input operation it targets."""
        with self._guard:
            candidate = self._input_state["candidate"]
            if candidate is None or candidate["operation_id"] != operation_id:
                return _UNSET
            self._input_state["candidate"] = None
            return candidate["raw"]

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

    def save_response(self, operation_id, response, session_key=None):
        _persist_response(self.journal, operation_id, response, session_key)

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
            {**inputs, "retry_safe": retry_safe}
            if kind in {"activity", "provider"}
            else inputs
        )
        encoded_inputs = (
            codec.encode(durable_inputs)
            if kind in {"activity", "provider"}
            else fingerprint_inputs
        )
        record = self.journal.get(operation_id)
        if record is not None:
            if record["fingerprint"] != fingerprint or record["kind"] != kind:
                raise ReplayMismatch(
                    f"Operation {operation_id} changed ({record['kind']} -> {kind}); start a new run"
                )
            if record["status"] == "completed":
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
            if kind in {"activity", "provider"}:
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

    def _child(self, definition, args, kwargs, scope):
        child = RunContext(
            self.client,
            self.journal.run(self.run_id),
            definition,
            scope=scope,
            parent=self,
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
        return self._child(definition, (), {}, f"{self.scope}/{scope}")

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
    return await _async_call(
        parallel, *calls, max_workers=max_workers, settle=settle
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
        self.provider_config = dict(provider_config or {})
        if isinstance(provider, str):
            from .config import (
                ConfigError,
                validate_codex_config,
                validate_non_secret_settings,
            )

            if provider != "codex":
                raise ConfigError("Botpipe 2.0 supports only the codex provider")
            validate_non_secret_settings(self.provider_config, "codex")
            validate_codex_config(self.provider_config)
        self.state_dir = (
            Path(state_dir).resolve()
            if state_dir is not None
            else default_state_dir(self.workspace)
        )
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._provider_name_arg = provider if isinstance(provider, str) else None
        self._configured_provider_config = dict(self.provider_config)
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
        self._configured_policy = self.policy
        self.limits = RunLimits(max_operations, timeout)
        self.journal = Journal(self.state_dir)

    def protected_paths(self, folder):
        folder = Path(folder)
        return (
            folder / "ledger.jsonl", folder / "input.json", folder / "request.md",
            folder / "operations", self.state_dir / "sessions",
        )

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
        if data["provider"] != self.provider_name:
            raise ReplayMismatch(
                "Provider configuration changed; resume with the recorded provider configuration"
            )
        if self._provider_name_arg is not None:
            self._activate_provider_config(data.get("provider_config", {}))
            self.policy = Policy.from_dict(data["policy"])
        elif (
            data.get("provider_config", {}) != self.provider_config
            or self.policy.to_dict() != data["policy"]
        ):
            raise ReplayMismatch("Run policy changed; resume with the recorded policy")

    def _activate_provider_config(self, config):
        config = dict(config)
        if config == self.provider_config:
            return
        from .config import validate_codex_config, validate_non_secret_settings
        from .providers import get_provider

        validate_non_secret_settings(config, "codex")
        validate_codex_config(config)
        close = getattr(self.provider, "close", None)
        if callable(close):
            close()
        self.provider = get_provider(self._provider_name_arg, config=config)
        self.provider_config = config
        self.provider_name = getattr(
            self.provider, "name", type(self.provider).__name__
        )

    def _prepare_new_run(self):
        if self._provider_name_arg is not None:
            self._activate_provider_config(self._configured_provider_config)
            self.policy = self._configured_policy

    def run_lock(self, run_id):
        """Hold the fail-fast execution lock for one journal/run identity."""

        return acquire_run_lock(self.journal.path, run_id)

    def run(self, definition, *args, task_id=None, run_id=None, **kwargs):
        self._prepare_new_run()
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
        request_text = args[0] if args and isinstance(args[0], str) else kwargs.get("request")
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
            **({"request_text": request_text} if isinstance(request_text, str) else {}),
            "status": "created",
            "folder": str(folder),
            "provider": self.provider_name,
            "provider_config": self.provider_config,
            "policy": self.policy.to_dict(),
            "max_operations": limits.max_operations,
            "timeout": limits.timeout,
            "created_at": now(),
            "error": None,
        }
        with self.run_lock(run_id):
            provenance_start = capture_workflow_provenance(
                definition, self.workspace
            )
            self.journal.create_run(data)
            return self._execute(
                definition,
                data,
                args,
                kwargs,
                provenance_start=provenance_start,
            )

    async def arun(self, definition, *args, **kwargs):
        # One runtime and one provider boundary. Cancellation joins the worker;
        # it never reports a stopped workflow while the worker still edits files.
        return await _async_call(self.run, definition, *args, **kwargs)

    def resume(
        self, run_id, *, answer=_UNSET, workflow=None, max_operations=None, timeout=None
    ):
        with self.run_lock(run_id):
            for operation_id, selection in self._pending_resolutions(run_id).items():
                arguments = codec.decode(selection["arguments"])
                self._resolve(run_id, operation_id, **arguments, _locked=True)
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
            input_candidate = None
            if answer is not _UNSET:
                pending = data.get("pending_input")
                if not pending:
                    raise ValueError("Run is not waiting for an answer")
                operation_id = pending.get("operation_id")
                record = self.journal.get(operation_id)
                recorded_request = None if record is None else record.get("response")
                expected_request = {
                    key: pending[key]
                    for key in ("question", "schema")
                    if key in pending
                }
                if (
                    record is None
                    or record["run_id"] != run_id
                    or record["kind"] != "input"
                    or record["status"] != "waiting"
                    or recorded_request != expected_request
                ):
                    raise ValueError("Run is no longer waiting for that answer")
                input_candidate = {"operation_id": operation_id, "raw": answer}
            decoded_args = codec.decode(data["args"])
            decoded_kwargs = codec.decode(data["kwargs"])
            return self._execute(
                definition,
                data,
                decoded_args,
                decoded_kwargs,
                input_candidate=input_candidate,
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
    ):
        ctx = RunContext(self, data, definition, input_candidate=input_candidate)
        status = "completed"
        value = None
        error = None
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
            status = "budget_exceeded"
            error = str(exc)
            pending = None
            encoded = None
        except CancellationRequested as exc:
            status = "interrupted"
            error = str(exc)
            pending = None
            encoded = None
        except UncertainOperation as exc:
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
        )
        self.journal.event(
            ctx.run_id,
            "execution_revision",
            {"phase": "end", "provenance": provenance_end},
        )
        result = RunResult(
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
        return result

    def _outputs(self, run_id):
        from .read_projection import project_run

        projection = project_run(self.journal.snapshot(run_id))
        return projection.artifacts, projection.usage

    def runs(self):
        return self.journal.runs()

    def inspect(self, run_id):
        from .read_projection import project_run

        return project_run(self.journal.snapshot(run_id)).inspection()

    def resolve(
        self,
        run_id,
        operation_id,
        *,
        retry=False,
        accept=False,
        fail=False,
        response=_UNSET,
        artifact_digests=None,
    ):
        return self._resolve(
            run_id, operation_id, retry=retry, accept=accept, fail=fail,
            response=response, artifact_digests=artifact_digests,
        )

    def _pending_resolutions(self, run_id):
        pending = {}
        for event in self.journal.events(run_id):
            if event["event"] == "resolution_selected":
                pending[event["operation_id"]] = event["data"]
            elif event["event"] == "operation_reconciled":
                pending.pop(event["operation_id"], None)
        return pending

    def _resolve(
        self, run_id, operation_id, *, retry=False, accept=False, fail=False,
        response=_UNSET, artifact_digests=None, _locked=False,
    ):
        choices = int(bool(retry)) + int(bool(accept)) + int(bool(fail))
        if choices > 1 or (retry and (response is not _UNSET or artifact_digests is not None)):
            raise ValueError("Choose exactly one of retry, accept, or fail")
        if choices == 0 and response is _UNSET and artifact_digests is None:
            raise ValueError("Choose retry, accept, fail, a response, or artifact_digests")
        with nullcontext() if _locked else self.run_lock(run_id):
            requested = codec.encode({
                "retry": retry, "accept": accept, "fail": fail,
                **({"response": response} if response is not _UNSET else {}),
                "artifact_digests": artifact_digests,
            })
            selected = self._pending_resolutions(run_id).get(operation_id)
            if selected is not None:
                if not _locked and requested != selected["requested"]:
                    raise ValueError("A recorded resolution is unfinished; resume it before choosing another")
                arguments = codec.decode(selected["arguments"])
                retry, accept, fail = (arguments[key] for key in ("retry", "accept", "fail"))
                response = arguments.get("response", _UNSET)
                artifact_digests = arguments.get("artifact_digests")

            def select_resolution(outcome=None):
                nonlocal selected
                if selected is not None:
                    return
                selected = {
                    "requested": requested,
                    "arguments": codec.encode({
                        "retry": retry, "accept": accept, "fail": fail,
                        **({"response": response} if response is not _UNSET else {}),
                        "artifact_digests": artifact_digests,
                    }),
                    "prior_outcome": None if outcome is None else type(outcome).__name__,
                    "detail": None if outcome is None else getattr(outcome, "detail", None),
                }
                self.journal.event(run_id, "resolution_selected", selected, operation_id)

            data = self.journal.run(run_id)
            self._check_run_configuration(data)
            operations = self.journal.operations(run_id)
            _preflight_recorded_contracts(data, operations)
            record = self.journal.get(operation_id)
            if record is None or record["run_id"] != run_id:
                raise KeyError(operation_id)
            if selected is not None and record["kind"] == "activity" and record["status"] == "completed":
                self.journal.event(run_id, "operation_reconciled", {"retry": False, "source": "operator"}, operation_id)
                return
            replaying_failure = (
                fail
                and record["status"] == "failed"
                and self._is_operator_failure(record)
            )
            if record["status"] not in ("started", "response") and not replaying_failure:
                raise ValueError("Only unfinished operations can be reconciled")
            if record["kind"] not in ("provider", "activity"):
                raise ValueError(
                    "Only provider turns and activities require effect reconciliation"
                )
            if artifact_digests is not None and record["kind"] != "provider":
                raise ValueError("Only provider outputs accept artifact reconciliation")
            old = dict(record.get("response") or {})
            source = "operator"
            if fail and record["kind"] == "activity":
                select_resolution()
                self._fail_resolution(
                    run_id,
                    operation_id,
                    record,
                    source,
                    already_failed=replaying_failure,
                )
                self._finish_failed_resolution(run_id, operation_id, source)
                return
            if record["kind"] == "provider":
                from .artifacts import Artifact, ArtifactError, ArtifactStore
                from .providers import ProviderRequest, ProviderResponse

                checkpoint = ProviderCheckpoint.from_record(old)
                if isinstance(checkpoint, NotDispatchedCheckpoint):
                    raise ValueError(
                        "Budget exhausted before dispatch; no effects need reconciliation. "
                        "Start a new run to use different provider budget limits"
                    )
                inputs = codec.decode(record["inputs"])
                request_data = checkpoint.request_data or {}
                operation_key = request_data.get("operation_key", inputs.get("operation_key", operation_id))
                # A retry marker names the *next* generation; reconcile the
                # attempt whose effects are still awaiting resolution.
                previous = checkpoint.attempt_generation
                request = ProviderRequest(
                    operation_id=operation_id,
                    prompt=request_data.get("prompt", inputs["prompt"]),
                    workspace=Path(inputs["workspace"]),
                    session_id=request_data.get("session_id"),
                    output_schema=inputs.get("schema"),
                    policy=Policy.from_dict(inputs["policy"]),
                    artifacts={
                        name: Path(path)
                        for name, path in request_data.get("artifacts", {}).items()
                    },
                    operation_key=operation_key,
                    session_key=inputs.get("session"),
                    timeout=RunLimits.from_record(data).timeout,
                    attempt=previous + 1,
                    reads=tuple(Path(path) for path in request_data.get("reads", ())),
                    preset=inputs.get("operation", "run"),
                    tools=(
                        None
                        if inputs.get("tools") is None
                        else tuple(inputs.get("tools", ()))
                    ),
                    instructions=inputs.get("instructions"),
                    settings=inputs.get("settings", {}),
                    checkpoint=self.journal.attempt(operation_id, previous + 1),
                    on_checkpoint=lambda update: self.journal.attempt_checkpoint(
                        operation_id, previous + 1, update
                    ),
                )
                store = ArtifactStore(
                    Path(data["folder"]),
                    state_dir=self.state_dir,
                    workspace=request.workspace,
                    allowed_roots=(self.state_dir / "tasks" / data["task_id"],),
                    forbidden_paths=self.protected_paths(data["folder"]),
                )
                artifact_operation = f"{operation_id}:generation:{previous}"

                def settle_independent_cleanup():
                    release = getattr(self.provider, "release_operation", None)
                    if inputs.get("session") is not None or not callable(release):
                        return
                    attempt = self.journal.attempt(operation_id, previous + 1)
                    if not attempt:
                        return
                    cleanup = attempt.get("cleanup") or {}
                    if cleanup.get("status") == "completed" or cleanup.get("resolved_by") == "operator":
                        return
                    try:
                        release(operation_key, require_owner=bool(attempt.get("dispatch_authorized")))
                    except Exception as exc:
                        # Explicit resolution may accept uncertainty, but it is
                        # not evidence that an old process was stopped.
                        cleanup = {
                            "status": "incomplete", "error": str(exc),
                            "resolved_by": "operator",
                            "resolution": "fail" if fail else "retry" if retry else "accept",
                        }
                    else:
                        cleanup = {"status": "completed"}
                    self.journal.attempt_checkpoint(operation_id, previous + 1, {"cleanup": cleanup})

                def reconcile_provider():
                    nonlocal artifact_digests, response, retry, source, checkpoint
                    if isinstance(checkpoint, RespondedCheckpoint):
                        # The durable terminal response needs no native recovery.
                        outcome = Completed(checkpoint.response)
                    else:
                        outcome = recover_outcome(self.provider, request)
                    if isinstance(outcome, Running):
                        raise BotpipeError(ProviderLifecycle.blocked_message(outcome))
                    if fail:
                        # Explicit failure may resolve a stopped or unknowable old
                        # attempt, but never a turn known to still be active.
                        if isinstance(outcome, Completed):
                            response = outcome.response
                            checkpoint = ProviderLifecycle.completed(checkpoint, response)
                        select_resolution(outcome)
                        if isinstance(outcome, Completed):
                            _persist_response(self.journal, operation_id, checkpoint.to_record(), session_key=inputs.get("session"))
                        return
                    action = ProviderLifecycle.reconciliation_action(outcome)
                    if action is RecoveryAction.USE_RESPONSE:
                        checkpoint = ProviderLifecycle.completed(
                            checkpoint, outcome.response
                        )
                        response = checkpoint.response
                        retry = False
                        source = "recovered"
                    elif (
                        isinstance(outcome, Unknown)
                        and not retry
                        and not accept
                        and response is _UNSET
                    ):
                        raise BotpipeError(ProviderLifecycle.blocked_message(outcome))
                    if accept and response is _UNSET:
                        if inputs.get("schema") is not None:
                            raise ValueError(
                                "Accepting a typed result without a completed turn "
                                "requires a response matching its output schema"
                            )
                        response = ProviderResponse(
                            "",
                            session_id=record.get("thread_id") or request.session_id,
                            metadata={"operator_accepted": True},
                        )
                    if response is not _UNSET:
                        if isinstance(response, dict):
                            response = ProviderResponse(**response)
                        if not isinstance(response, ProviderResponse):
                            raise TypeError(
                                "Provider reconciliation needs ProviderResponse or its field mapping"
                            )
                        if accept and source == "operator":
                            response = dataclasses.replace(
                                response,
                                session_id=(
                                    response.session_id
                                    or record.get("thread_id")
                                    or request.session_id
                                ),
                                metadata={**response.metadata, "operator_accepted": True},
                            )
                        response.to_record()
                        if accept and inputs.get("schema") is not None:
                            from jsonschema import ValidationError as SchemaError
                            from jsonschema import validate

                            text = response.text.strip()
                            fenced = re.fullmatch(
                                r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL
                            )
                            try:
                                validate(
                                    json.loads(fenced.group(1) if fenced else text),
                                    inputs["schema"],
                                )
                            except (ValueError, SchemaError) as exc:
                                raise ValueError(
                                    "Accepted response does not match the output schema: "
                                    f"{exc}"
                                ) from exc
                        checkpoint = ProviderLifecycle.completed(checkpoint, response)
                    declarations = tuple(
                        Artifact.from_record(a) for a in inputs.get("writes", ())
                    ) if artifact_digests is not None or accept else ()
                    if artifact_digests is not None or (accept and declarations):
                        if response is _UNSET:
                            raise ValueError(
                                "Artifact reconciliation also needs the completed or manually supplied response"
                            )
                        if not declarations:
                            raise ValueError(
                                "This provider operation has no declared artifacts"
                            )
                        if accept and artifact_digests is None:
                            resolution = checkpoint.artifact_resolution
                            if resolution is not None:
                                artifact_digests = resolution["digests"]
                            else:
                                paths = store.destinations(declarations)
                                accepted = {}
                                for declaration in declarations:
                                    path = paths[declaration.name]
                                    if not path.exists():
                                        accepted[declaration.name] = None
                                        continue
                                    digest = hashlib.sha256()
                                    try:
                                        with path.open("rb") as handle:
                                            for chunk in iter(
                                                lambda: handle.read(1024 * 1024), b""
                                            ):
                                                digest.update(chunk)
                                    except OSError as exc:
                                        raise ArtifactError(
                                            "Could not inventory accepted artifact: "
                                            f"{declaration.name}"
                                        ) from exc
                                    accepted[declaration.name] = digest.hexdigest()
                                artifact_digests = accepted
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
                            checkpoint = ProviderLifecycle.with_artifact_resolution(
                                checkpoint, approved
                            )
                    select_resolution(outcome)
                    if response is not _UNSET:
                        # Record the operator's selection before capture so a
                        # restart can resume from the chosen response.
                        _persist_response(
                            self.journal,
                            operation_id,
                            checkpoint.to_record(),
                            session_key=inputs.get("session"),
                        )
                    if accept and declarations:
                        store.capture(
                            declarations,
                            artifact_operation,
                            recover=True,
                            expected_digests=artifact_digests,
                        )

                session_key = inputs.get("session")
                recorded_timeout = inputs.get("timeout")
                session_timeout = (
                    RunLimits.from_record(data).timeout
                    if recorded_timeout is None
                    else recorded_timeout
                )
                session_guard = (
                    acquire_session_lock(
                        self.journal.path,
                        session_key,
                        timeout=session_timeout,
                        cancellation=_cancellation_event(),
                    )
                    if session_key is not None
                    else nullcontext()
                )
                with session_guard:
                    from .session_bindings import SessionBinding

                    binding = SessionBinding(self.journal, session_key) if session_key else None
                    owner_attempt = previous + 1
                    if binding is not None:
                        pending = binding.check(operation_key).get("pending")
                        if pending is not None and pending["operation_key"] == operation_key:
                            owner_attempt = pending["attempt"]
                    reconcile_provider()
                    settle_independent_cleanup()
                    if fail:
                        self._fail_resolution(
                            run_id, operation_id, record, source,
                            already_failed=replaying_failure,
                        )
                        if binding is not None:
                            binding.finish(
                                run_id, operation_key,
                                operation_id=operation_id, attempt=owner_attempt,
                                session_id=None if response is _UNSET else response.session_id,
                                outcome="operator_failed",
                            )
                        self._finish_failed_resolution(run_id, operation_id, source)
                        return
                    if retry:
                        checkpoint = ProviderLifecycle.authorize_retry(checkpoint)
                        _persist_response(self.journal, operation_id, checkpoint.to_record())
                        if binding is not None:
                            binding.claim(run_id, operation_key, operation_id, checkpoint.generation + 1)
                    if binding is not None and not retry:
                        binding.finish(
                            run_id, operation_key,
                            operation_id=operation_id, attempt=owner_attempt,
                            session_id=None if response is _UNSET else response.session_id,
                            outcome="operator_accepted",
                        )
                    self.journal.event(run_id, "operation_reconciled", {
                        "retry": retry, "source": source,
                        **({"artifacts": checkpoint.artifact_resolution} if artifact_digests is not None else {}),
                    }, operation_id)
                    return

            elif response is not _UNSET:
                result = codec.encode(response)
                select_resolution()
                _commit_or_confirm(
                    self.journal,
                    operation_id,
                    lambda: self.journal.finish(operation_id, result),
                    {"status": "completed", "result": result},
                    "Resolved activity checkpoint could not be confirmed; inspect it before retrying",
                )
            elif accept:
                raise ValueError("Activity resolution with accept needs a response")
            if retry:
                select_resolution()
                # Explicit retry is represented by an authorization marker; the
                # original intent and every attempt remain in the ledger.
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
    def _fail_resolution(
        self,
        run_id,
        operation_id,
        record,
        source,
        *,
        already_failed=False,
    ):
        if not already_failed:
            failure = _finalize_exception_record(
                _exception_record(BotpipeError(_OPERATOR_FAILURE))
            )
            self.journal.fail(operation_id, failure)
        self.journal.update_run(
            run_id,
            status="failed",
            error=f"BotpipeError: {_OPERATOR_FAILURE}",
            pending_input=None,
            updated_at=now(),
        )

    def _finish_failed_resolution(self, run_id, operation_id, source):
        if not any(
            event["event"] == "operation_reconciled"
            and event["operation_id"] == operation_id
            and event["data"].get("failed") is True
            for event in self.journal.events(run_id)
        ):
            self.journal.event(
                run_id,
                "operation_reconciled",
                {
                    "retry": False,
                    "accepted": False,
                    "failed": True,
                    "source": source,
                },
                operation_id,
            )

    @staticmethod
    def _is_operator_failure(record):
        error = record.get("error")
        return (
            type(error) is dict
            and error.get("module") == BotpipeError.__module__
            and error.get("type") == BotpipeError.__qualname__
            and error.get("message") == _OPERATOR_FAILURE
        )

    def close(self):
        close = getattr(self.provider, "close", None)
        try:
            if callable(close):
                close()
        finally:
            self.journal.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
