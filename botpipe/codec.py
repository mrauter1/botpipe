"""Explicit, bounded JSON state for durable execution; never pickle state."""

from __future__ import annotations

import base64
import contextvars
import dataclasses
import importlib
import json
import math
import os
import re
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from inspect import get_annotations, getattr_static
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType, MemberDescriptorType, SimpleNamespace
from typing import ForwardRef, get_args, get_origin, get_type_hints

from pydantic import BaseModel, Secret, SecretBytes, SecretStr, TypeAdapter

_TYPES: dict[str, type] = {}
_STATE_VERSION = 1
_MAX_DEPTH = 100
_MAX_VALUES = 100_000
_TYPE_NAME = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[^:\x00\r\n]{1,1000}$")
_SOURCE_BOUNDARY = contextvars.ContextVar("botpipe_source_boundary", default=None)
_SOURCE_ANCHOR = contextvars.ContextVar("botpipe_source_anchor", default=None)
_SOURCE_CAPTURE = contextvars.ContextVar("botpipe_source_capture", default=None)
_DECODE_SOURCES = contextvars.ContextVar("botpipe_decode_sources", default=None)
_OWNER_SCHEMA = "botpipe.source-owners.v2"
_INFER_SOURCE_ANCHOR = object()


@contextmanager
def source_identity(boundary, *, anchor=_INFER_SOURCE_ANCHOR):
    """Record and verify owned source for durable values in this boundary."""

    raw = boundary if isinstance(boundary, (tuple, list, set)) else (boundary,)
    boundaries = tuple(
        dict.fromkeys(str(Path(item).resolve(strict=True)) for item in raw)
    )
    if anchor is _INFER_SOURCE_ANCHOR:
        resolved_anchor = boundaries[0] if boundaries else None
    else:
        resolved_anchor = str(Path(anchor).resolve(strict=True))
    boundary_token = _SOURCE_BOUNDARY.set(boundaries)
    anchor_token = _SOURCE_ANCHOR.set(resolved_anchor)
    try:
        yield
    finally:
        _SOURCE_ANCHOR.reset(anchor_token)
        _SOURCE_BOUNDARY.reset(boundary_token)


def _boundary_kind(path):
    if path.is_file():
        return "file"
    if path.is_dir():
        return "directory"
    raise TypeError(
        f"Source ownership boundary is neither a file nor directory: {path}"
    )


def _source_owner_record(boundaries, anchor):
    """Describe operation ownership relative to an independent source anchor."""

    paths = tuple(Path(item).resolve(strict=True) for item in boundaries)
    if not paths:
        return None
    if anchor is None:
        raise TypeError("Source ownership boundaries require a source anchor")
    anchor = Path(anchor).resolve(strict=True)
    base = anchor if anchor.is_dir() else anchor.parent
    items = []
    for path in paths:
        relative = Path(os.path.relpath(path, base)).as_posix()
        _portable_owner_relative(relative, "source owner")
        items.append({"kind": _boundary_kind(path), "relative": relative})
    return {
        "schema": _OWNER_SCHEMA,
        "anchor_kind": _boundary_kind(anchor),
        "boundaries": items,
    }


def _portable_owner_relative(relative, path):
    if type(relative) is not str or not relative or "\x00" in relative:
        raise TypeError(f"{path}: invalid source owner locator")
    posix = PurePosixPath(relative)
    windows = PureWindowsPath(relative)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or "\\" in relative
        or posix.as_posix() != relative
    ):
        raise TypeError(f"{path}: invalid portable source ownership path {relative!r}")
    seen_name = False
    for part in posix.parts:
        if part == "..":
            if seen_name:
                raise TypeError(
                    f"{path}: invalid portable source ownership path {relative!r}"
                )
        elif part != ".":
            seen_name = True
    return posix


def _resolve_owner_relative(base, relative, path):
    parts = _portable_owner_relative(relative, path).parts
    candidate = base
    for part in parts:
        if part == "..":
            candidate = candidate.parent
        elif part != ".":
            candidate = candidate / part
            if candidate.is_symlink():
                raise TypeError(f"{path}: source owner locator traverses a symlink")
    return candidate.resolve(strict=True)


@contextmanager
def without_source_identity():
    """Keep non-durable structural hashes independent of runtime context."""

    boundary_token = _SOURCE_BOUNDARY.set(None)
    anchor_token = _SOURCE_ANCHOR.set(None)
    try:
        yield
    finally:
        _SOURCE_ANCHOR.reset(anchor_token)
        _SOURCE_BOUNDARY.reset(boundary_token)


def _type_source(cls):
    boundaries = _SOURCE_BOUNDARY.get()
    if boundaries is None:
        return None
    from .provenance import capture_type_source

    return capture_type_source(cls, boundaries)


def _verify_type_record(cls, record, path):
    if _SOURCE_BOUNDARY.get() is None:
        return
    sources = _DECODE_SOURCES.get()
    source = sources.get(record.get("type")) if sources is not None else None
    if source is None:
        raise TypeError(
            f"{path}: historical durable type {record.get('type')!r} has no "
            "source identity and cannot be safely resumed"
        )
    from .provenance import verify_type_source

    verify_type_source(cls, source)


def _with_type_source(record, cls):
    capture = _SOURCE_CAPTURE.get()
    if capture is not None:
        name = type_name(cls)
        if name in capture:
            return record
        source = _type_source(cls)
        if source is None:
            return record
        previous = capture.setdefault(name, source)
        if previous != source:
            raise TypeError(f"Conflicting source identity for durable type {name}")
    return record


def type_name(cls):
    if not isinstance(cls, type):
        raise TypeError(
            f"Durable type reference requires a type, got {type(cls).__name__}"
        )
    name = f"{cls.__module__}:{cls.__qualname__}"
    if not _TYPE_NAME.fullmatch(name):
        raise TypeError(f"Type {name!r} has no durable qualified name")
    _TYPES[name] = cls
    return name


def resolve_type(name):
    if type(name) is not str or not _TYPE_NAME.fullmatch(name):
        raise TypeError(f"Invalid durable type reference {name!r}")
    if name in _TYPES:
        return _TYPES[name]
    module, qualname = name.split(":", 1)
    if "<locals>" in qualname:
        raise TypeError(f"Local type {name} must be registered by the resumed workflow")
    # Generated generic classes (for example Model[int]) cannot be recovered by
    # attribute traversal. schema_for() registers annotated generated classes.
    if any(character in qualname for character in "[] ,"):
        raise TypeError(
            f"Generated type {name} must be registered by the resumed workflow"
        )
    value = importlib.import_module(module)
    for part in qualname.split("."):
        value = getattr(value, part)
    if not isinstance(value, type):
        raise TypeError(f"Durable type reference {name} did not resolve to a type")
    _TYPES[name] = value
    return value


def _annotation_namespaces(cls, localns=None):
    """Build the namespaces Python uses for postponed class annotations."""

    module = sys.modules.get(cls.__module__)
    globalns = dict(vars(module)) if module is not None else {}
    namespace = dict(globalns)
    owner = module
    for part in cls.__qualname__.split(".")[:-1]:
        if part == "<locals>" or owner is None:
            break
        owner = getattr(owner, part, None)
        if isinstance(owner, type):
            namespace.update(vars(owner))
    for base in reversed(cls.__mro__):
        namespace.update(vars(base))
    namespace[cls.__name__] = cls
    if localns is not None:
        namespace.update(localns)
    return globalns, namespace


def _resolved_class_annotations(cls, localns=None):
    resolved = {}
    for owner in reversed(cls.__mro__):
        annotations = get_annotations(owner, eval_str=False)
        if not annotations:
            continue
        owner_localns = localns if owner is cls else None
        globalns, namespace = _annotation_namespaces(owner, owner_localns)
        declaration = SimpleNamespace(__annotations__=annotations)
        try:
            hints = get_type_hints(
                declaration,
                globalns=globalns,
                localns=namespace,
                include_extras=True,
            )
        except (NameError, TypeError):
            # A module forward reference can be retried after its defining
            # module has finished importing. Other bases remain independently
            # resolvable from their own defining modules.
            hints = annotations
        resolved.update(hints)
    return resolved


def _pydantic_annotation(name, field, resolved):
    annotation = field.annotation
    if isinstance(annotation, (str, ForwardRef)):
        return resolved.get(name, annotation)
    return annotation


def register_annotation(annotation, _seen=None, *, localns=None):
    """Register concrete types reachable from a resolved type annotation."""

    seen = set() if _seen is None else _seen
    identity = id(annotation)
    if identity in seen:
        return
    seen.add(identity)
    origin = get_origin(annotation)
    if origin is not None:
        register_annotation(origin, seen, localns=localns)
        for argument in get_args(annotation):
            register_annotation(argument, seen, localns=localns)
        return
    if not isinstance(annotation, type) or annotation.__module__ == "typing":
        return
    type_name(annotation)
    if annotation is BaseModel:
        return
    if issubclass(annotation, BaseModel):
        globalns, namespace = _annotation_namespaces(annotation, localns)
        if not annotation.__pydantic_complete__:
            annotation.model_rebuild(
                raise_errors=False, _types_namespace={**globalns, **namespace}
            )
        resolved = _resolved_class_annotations(annotation, localns)
        for name, field in annotation.model_fields.items():
            register_annotation(
                _pydantic_annotation(name, field, resolved),
                seen,
                localns=namespace,
            )
    elif dataclasses.is_dataclass(annotation):
        _, namespace = _annotation_namespaces(annotation, localns)
        resolved = _resolved_class_annotations(annotation, namespace)
        for field in dataclasses.fields(annotation):
            register_annotation(
                resolved.get(field.name, field.type), seen, localns=namespace
            )


class _Traversal:
    def __init__(self):
        self.count = 0
        self.active: set[int] = set()

    def visit(self, value, path, depth, *, compound=False):
        self.count += 1
        if self.count > _MAX_VALUES:
            raise TypeError(
                f"{path}: durable value exceeds the {_MAX_VALUES}-value limit"
            )
        if depth > _MAX_DEPTH:
            raise TypeError(
                f"{path}: durable value exceeds the {_MAX_DEPTH}-level limit"
            )
        if (
            compound
            or isinstance(
                value, (list, dict, MappingProxyType, tuple, set, frozenset, BaseModel)
            )
            or (dataclasses.is_dataclass(value) and not isinstance(value, type))
        ):
            identity = id(value)
            if identity in self.active:
                raise TypeError(f"{path}: cycles are not supported in durable values")
            self.active.add(identity)
            return identity
        return None

    def leave(self, identity):
        if identity is not None:
            self.active.remove(identity)


def _child(path: str, key: str) -> str:
    if key.isidentifier():
        return f"{path}.{key}"
    return f"{path}[{key!r}]"


def _plain_json(value, path, depth, traversal):
    """Validate runtime-owned records that deliberately do not use codec tags."""

    identity = traversal.visit(value, path, depth)
    try:
        if value is None or type(value) in (str, int, bool):
            return value
        if type(value) is float:
            if math.isfinite(value):
                return value
            raise TypeError(f"{path}: non-finite floats are not durable")
        if type(value) is list:
            for index, item in enumerate(value):
                _plain_json(item, f"{path}[{index}]", depth + 1, traversal)
            return value
        if type(value) is dict:
            _string_mapping(value, path)
            for key, item in value.items():
                _plain_json(item, _child(path, key), depth + 1, traversal)
            return value
        raise TypeError(
            f"{path}: runtime record contains unsupported {type(value).__name__}"
        )
    finally:
        traversal.leave(identity)


def _annotation_contains(annotation, names: set[str]) -> bool:
    if type(annotation).__name__ in names:
        return True
    return any(
        _annotation_contains(argument, names) for argument in get_args(annotation)
    )


def _contains_secret(annotation) -> bool:
    origin = get_origin(annotation)
    if origin is not None and _contains_secret(origin):
        return True
    if isinstance(annotation, type):
        try:
            if issubclass(annotation, (Secret, SecretStr, SecretBytes)):
                return True
        except TypeError:
            pass
    return any(_contains_secret(argument) for argument in get_args(annotation))


def _contains_serializer(annotation) -> bool:
    return _annotation_contains(
        annotation, {"PlainSerializer", "WrapSerializer", "SerializeAsAny"}
    )


def _has_custom_core_serializer(schema, _seen=None):
    """Find serializer hooks embedded directly in a Pydantic core schema."""

    seen = set() if _seen is None else _seen
    if isinstance(schema, dict):
        identity = id(schema)
        if identity in seen:
            return False
        seen.add(identity)
        serializer = schema.get("serialization")
        if isinstance(serializer, dict):
            function = serializer.get("function")
            module = getattr(function, "__module__", "")
            # Pydantic installs a few serializers for standard Python types
            # (notably pathlib.Path). They describe the standard type rather
            # than application-controlled redaction or transformation.
            if function is None or not module.startswith(
                ("pydantic.", "pydantic_core.")
            ):
                return True
        return any(_has_custom_core_serializer(item, seen) for item in schema.values())
    if isinstance(schema, (list, tuple)):
        return any(_has_custom_core_serializer(item, seen) for item in schema)
    return False


def _reject_custom_core_serializer(schema, path):
    if _has_custom_core_serializer(schema):
        raise TypeError(
            f"{path}: Pydantic types with custom serializers installed through "
            "core schemas are not durable"
        )


def _has_core_schema_provider(annotation, _seen=None):
    seen = set() if _seen is None else _seen
    identity = id(annotation)
    if identity in seen:
        return False
    seen.add(identity)
    try:
        getattr_static(annotation, "__get_pydantic_core_schema__")
    except AttributeError:
        pass
    else:
        return True
    return any(_has_core_schema_provider(item, seen) for item in get_args(annotation))


def _pydantic_fields(cls: type[BaseModel], path: str):
    if cls.model_dump is not BaseModel.model_dump or (
        cls.model_dump_json is not BaseModel.model_dump_json
    ):
        raise TypeError(
            f"{path}: Pydantic models with custom serializers are not durable"
        )
    decorators = cls.__pydantic_decorators__
    if (
        decorators.field_serializers
        or decorators.model_serializers
        or decorators.computed_fields
    ):
        raise TypeError(
            f"{path}: Pydantic models with custom serializers are not durable"
        )
    if cls.model_config.get("json_encoders"):
        raise TypeError(
            f"{path}: Pydantic models with custom JSON encoders are not durable"
        )
    _reject_custom_core_serializer(cls.__pydantic_core_schema__, path)
    private = getattr(cls, "__private_attributes__", {})
    if private:
        raise TypeError(f"{path}: Pydantic private attributes are not durable")
    base_slots = set(BaseModel.__slots__)
    for base in cls.__mro__:
        if base in {BaseModel, object}:
            continue
        slots = base.__dict__.get("__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        unsupported = set(slots) - base_slots - {"__weakref__"}
        if unsupported:
            label = ", ".join(sorted(unsupported))
            raise TypeError(
                f"{path}: Pydantic model has unsupported state slots: {label}"
            )
    for name, field in cls.model_fields.items():
        if field.exclude is not None or field.exclude_if is not None:
            raise TypeError(
                f"{_child(path, name)}: excluded Pydantic fields are not durable"
            )
        if _contains_secret(field.annotation):
            raise TypeError(f"{_child(path, name)}: secret fields are not durable")
        if _contains_serializer(field.annotation) or any(
            _contains_serializer(metadata) for metadata in field.metadata
        ):
            raise TypeError(
                f"{_child(path, name)}: fields with custom serializers are not durable"
            )
    return cls.model_fields


def _dataclass_fields(cls, path: str, *, localns=None):
    fields = tuple(dataclasses.fields(cls))
    resolved = _resolved_class_annotations(cls, localns)
    schema_candidates = []
    if _has_core_schema_provider(cls):
        schema_candidates.append(cls)
    else:
        schema_candidates.extend(
            annotation
            for annotation in resolved.values()
            if _has_core_schema_provider(annotation)
        )
    checked = set()
    for annotation in schema_candidates:
        identity = id(annotation)
        if identity in checked:
            continue
        checked.add(identity)
        _reject_custom_core_serializer(TypeAdapter(annotation).core_schema, path)
    names = {field.name for field in fields}
    if cls.__new__ is not object.__new__:
        raise TypeError(
            f"{path}: dataclasses with custom or native __new__ are not durable"
        )
    for field in fields:
        if field.name.startswith("_"):
            raise TypeError(
                f"{_child(path, field.name)}: private dataclass fields are not durable"
            )
        if _contains_secret(resolved.get(field.name, field.type)):
            raise TypeError(
                f"{_child(path, field.name)}: secret fields are not durable"
            )
        storage = next(
            (
                base.__dict__[field.name]
                for base in cls.__mro__
                if field.name in base.__dict__
            ),
            None,
        )
        if (
            storage is not None
            and type(storage) is not MemberDescriptorType
            and (
                hasattr(type(storage), "__set__")
                or hasattr(type(storage), "__delete__")
            )
        ):
            raise TypeError(
                f"{_child(path, field.name)}: dataclass field descriptors are not durable"
            )
    for base in cls.__mro__:
        slots = base.__dict__.get("__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        unsupported = set(slots) - names - {"__dict__", "__weakref__"}
        if unsupported:
            label = ", ".join(sorted(unsupported))
            raise TypeError(f"{path}: dataclass has unsupported state slots: {label}")
    for hook in ("__getstate__", "__setstate__"):
        method = cls.__dict__.get(hook)
        if method is not None and not (
            getattr(method, "__module__", None) == "dataclasses"
            and getattr(method, "__name__", "").startswith("_dataclass_")
        ):
            raise TypeError(f"{path}: dataclass {hook} hooks are not durable")
    return fields


def _preflight(annotation, path, localns, *, require_adapter=False):
    """Reject annotations whose values cannot be represented faithfully.

    This check is intended for durable boundaries that know a declared type
    before they have a value to encode. It also registers generated Pydantic
    generic classes needed when a fresh process resumes recorded state.
    """

    seen = set()
    concrete_types = []

    def inspect(current, current_path, namespace=None):
        identity = id(current)
        if identity in seen:
            return
        seen.add(identity)
        if _contains_secret(current):
            raise TypeError(f"{current_path}: secret fields are not durable")
        if _contains_serializer(current):
            raise TypeError(
                f"{current_path}: fields with custom serializers are not durable"
            )
        origin = get_origin(current)
        if origin is not None:
            register_annotation(current, localns=namespace)
            for argument in get_args(current):
                inspect(argument, current_path, namespace)
            return
        if not isinstance(current, type) or current.__module__ == "typing":
            return
        concrete_types.append(current)
        type_name(current)
        if current is BaseModel:
            return
        if issubclass(current, BaseModel):
            globalns, model_namespace = _annotation_namespaces(current, namespace)
            if not current.__pydantic_complete__:
                current.model_rebuild(
                    raise_errors=False,
                    _types_namespace={**globalns, **model_namespace},
                )
            fields = _pydantic_fields(current, current_path)
            resolved = _resolved_class_annotations(current, model_namespace)
            for name, field in fields.items():
                inspect(
                    _pydantic_annotation(name, field, resolved),
                    _child(current_path, name),
                    model_namespace,
                )
        elif dataclasses.is_dataclass(current):
            _, dataclass_namespace = _annotation_namespaces(current, namespace)
            fields = _dataclass_fields(
                current, current_path, localns=dataclass_namespace
            )
            resolved = _resolved_class_annotations(current, dataclass_namespace)
            for field in fields:
                inspect(
                    resolved.get(field.name, field.type),
                    _child(current_path, field.name),
                    dataclass_namespace,
                )

    inspect(annotation, path, localns)
    adapter = None
    aggregate = isinstance(annotation, type) and (
        dataclasses.is_dataclass(annotation) or issubclass(annotation, BaseModel)
    )
    if (
        require_adapter
        or get_origin(annotation) is not None
        or (_has_core_schema_provider(annotation) and not aggregate)
    ):
        adapter = TypeAdapter(annotation)
        _reject_custom_core_serializer(adapter.core_schema, path)
    return adapter, tuple(concrete_types)


def preflight(annotation, path="$", *, localns=None):
    """Reject annotations whose values cannot be represented faithfully.

    This check is intended for durable boundaries that know a declared type
    before they have a value to encode. It also registers generated Pydantic
    generic classes needed when a fresh process resumes recorded state.
    """

    _preflight(annotation, path, localns)
    return annotation


def preflight_types(annotation, path="$", *, localns=None):
    """Preflight an annotation and return its reachable concrete types."""

    return _preflight(annotation, path, localns)[1]


def encode(value, *, record_owners=False):
    """Encode a supported value as JSON-compatible, versioned durable state."""

    if _SOURCE_BOUNDARY.get() is None or _SOURCE_CAPTURE.get() is not None:
        return _encode(value, "$", 0, _Traversal())
    sources = {}
    token = _SOURCE_CAPTURE.set(sources)
    try:
        encoded = _encode(value, "$.value", 0, _Traversal())
    finally:
        _SOURCE_CAPTURE.reset(token)
    owners = (
        _source_owner_record(_SOURCE_BOUNDARY.get(), _SOURCE_ANCHOR.get())
        if record_owners
        else None
    )
    if not sources and not owners:
        return encoded
    capsule = {
        "$botpipe": "capsule",
        "version": 1,
        "sources": dict(sorted(sources.items())),
        "value": encoded,
    }
    if owners is not None:
        capsule["owners"] = owners
    return capsule


def semantic_encoding(value):
    """Remove non-semantic operation ownership metadata from an encoding."""

    if type(value) is not dict or value.get("$botpipe") != "capsule":
        return value
    if "owners" not in value:
        return value
    capsule = dict(value)
    capsule.pop("owners")
    return capsule["value"] if not capsule.get("sources") else capsule


def _encode(value, path, depth, traversal):
    from .artifacts import ArtifactHandle, ArtifactMap

    identity = traversal.visit(
        value, path, depth, compound=isinstance(value, ArtifactMap)
    )
    try:
        if isinstance(value, (Secret, SecretStr, SecretBytes)):
            raise TypeError(f"{path}: secret values are not durable")
        if isinstance(value, ArtifactHandle):
            record = value.to_record()
            _plain_json(record, f"{path}.value", depth + 1, traversal)
            return {"$botpipe": "artifact", "value": record}
        if isinstance(value, ArtifactMap):
            items = tuple(value.items())
            if not all(type(key) is str for key, _ in items):
                raise TypeError(f"{path}: artifact mappings require string keys")
            return {
                "$botpipe": "artifacts",
                "value": {
                    k: _encode(v, _child(path, k), depth + 1, traversal)
                    for k, v in items
                },
            }
        if isinstance(value, Enum):
            return _with_type_source(
                {
                    "$botpipe": "enum",
                    "type": type_name(type(value)),
                    "value": _encode(
                        value.value, f"{path}.value", depth + 1, traversal
                    ),
                },
                type(value),
            )
        if value is None or type(value) in (str, int, bool):
            return value
        if type(value) is float:
            if not math.isfinite(value):
                raise TypeError(f"{path}: non-finite floats are not durable")
            return value
        if isinstance(value, Path) and type(value).__module__ == "pathlib":
            return {"$botpipe": "path", "value": str(value)}
        if type(value) is datetime:
            tz = value.tzinfo
            if tz is not None and type(tz) is not timezone:
                raise TypeError(
                    f"{path}: only datetime.timezone fixed offsets are durable"
                )
            timezone_state = None
            if tz is not None:
                offset = tz.utcoffset(value)
                name = tz.tzname(value)
                if type(offset) is not timedelta or type(name) is not str:
                    raise TypeError(f"{path}: invalid fixed-offset datetime timezone")
                timezone_state = {
                    "offset_microseconds": (
                        offset.days * 86_400_000_000
                        + offset.seconds * 1_000_000
                        + offset.microseconds
                    ),
                    "name": name,
                }
            return {
                "$botpipe": "datetime",
                "value": value.replace(tzinfo=None).isoformat(),
                "fold": value.fold,
                "timezone": timezone_state,
            }
        if type(value) is date:
            return {"$botpipe": "date", "value": value.isoformat()}
        if type(value) is bytes:
            return {
                "$botpipe": "bytes",
                "value": base64.b64encode(value).decode("ascii"),
            }
        if type(value) in (set, frozenset):
            body = [_encode(v, f"{path}[set]", depth + 1, traversal) for v in value]
            body.sort(key=lambda item: json.dumps(item, sort_keys=True))
            return {"$botpipe": type(value).__name__, "value": body}
        if isinstance(value, BaseModel):
            cls = type(value)
            fields = _pydantic_fields(cls, path)
            state = object.__getattribute__(value, "__dict__")
            if set(state) != set(fields):
                unknown = set(state) - set(fields)
                missing = set(fields) - set(state)
                detail = []
                if unknown:
                    detail.append(f"cached or unknown state {sorted(unknown)!r}")
                if missing:
                    detail.append(f"missing fields {sorted(missing)!r}")
                raise TypeError(
                    f"{path}: unsupported Pydantic state ({'; '.join(detail)})"
                )
            private = object.__getattribute__(value, "__pydantic_private__")
            if private:
                raise TypeError(f"{path}: Pydantic private state is not durable")
            extra = object.__getattribute__(value, "__pydantic_extra__")
            if extra is not None and type(extra) is not dict:
                raise TypeError(f"{path}: unsupported Pydantic extra-field storage")
            encoded_fields = {
                name: _encode(state[name], _child(path, name), depth + 1, traversal)
                for name in fields
            }
            encoded_extra = None
            if extra is not None:
                encoded_extra = {
                    key: _encode(item, _child(path, key), depth + 1, traversal)
                    for key, item in _string_mapping(
                        extra, f"{path}.__pydantic_extra__"
                    ).items()
                }
            fields_set = object.__getattribute__(value, "__pydantic_fields_set__")
            if type(fields_set) is not set or not all(
                type(name) is str for name in fields_set
            ):
                raise TypeError(f"{path}: invalid Pydantic fields_set state")
            allowed_set = set(fields) | set(extra or ())
            if not fields_set <= allowed_set:
                raise TypeError(f"{path}: Pydantic fields_set names unknown fields")
            return _with_type_source(
                {
                    "$botpipe": "model",
                    "version": _STATE_VERSION,
                    "type": type_name(cls),
                    "fields": encoded_fields,
                    "fields_set": sorted(fields_set),
                    "extra": encoded_extra,
                },
                cls,
            )
        if isinstance(value, type):
            return _with_type_source(
                {"$botpipe": "type", "type": type_name(value)}, value
            )
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            cls = type(value)
            fields = _dataclass_fields(cls, path)
            names = {field.name for field in fields}
            try:
                instance_dict = object.__getattribute__(value, "__dict__")
            except AttributeError:
                instance_dict = None
            if instance_dict is not None:
                unknown = set(instance_dict) - names
                if unknown:
                    raise TypeError(
                        f"{path}: dataclass has cached or unknown state {sorted(unknown)!r}"
                    )
            return _with_type_source(
                {
                    "$botpipe": "dataclass",
                    "version": _STATE_VERSION,
                    "type": type_name(cls),
                    "fields": {
                        field.name: _encode(
                            object.__getattribute__(value, field.name),
                            _child(path, field.name),
                            depth + 1,
                            traversal,
                        )
                        for field in fields
                    },
                },
                cls,
            )
        if type(value) is tuple:
            return {
                "$botpipe": "tuple",
                "value": [
                    _encode(v, f"{path}[{index}]", depth + 1, traversal)
                    for index, v in enumerate(value)
                ],
            }
        if type(value) is list:
            return [
                _encode(v, f"{path}[{index}]", depth + 1, traversal)
                for index, v in enumerate(value)
            ]
        if type(value) is dict:
            mapping = _string_mapping(value, path)
            return {
                "$botpipe": "dict",
                "value": {
                    k: _encode(v, _child(path, k), depth + 1, traversal)
                    for k, v in mapping.items()
                },
            }
        if isinstance(value, MappingProxyType):
            mapping = _string_mapping(value, path)
            return {
                "$botpipe": "mappingproxy",
                "value": {
                    k: _encode(v, _child(path, k), depth + 1, traversal)
                    for k, v in mapping.items()
                },
            }
        raise TypeError(
            f"{path}: unsupported durable value {type(value).__name__}; "
            "return typed data or an artifact handle"
        )
    finally:
        traversal.leave(identity)


def _string_mapping(value, path):
    if type(value) not in (dict, MappingProxyType):
        raise TypeError(f"{path}: durable mapping state must be an object")
    if not all(type(key) is str for key in value):
        raise TypeError(f"{path}: durable mappings require string keys")
    return value


def _record(value, path, required, optional=()):
    if type(value) is not dict:
        raise TypeError(f"{path}: durable record must be an object")
    if not all(type(key) is str for key in value):
        raise TypeError(f"{path}: durable record keys must be strings")
    keys = set(value)
    required = set(required)
    allowed = required | set(optional)
    missing = required - keys
    unknown = keys - allowed
    if missing:
        raise TypeError(f"{path}: durable record is missing {sorted(missing)!r}")
    if unknown:
        raise TypeError(f"{path}: durable record has unknown keys {sorted(unknown)!r}")
    return value


def _state_record(value, path, kind):
    # Check version before the full envelope so old {value: ...} records receive
    # an actionable migration error rather than a generic missing-fields error.
    if "version" not in value:
        raise TypeError(
            f"{path}: legacy unversioned {kind} state requires an explicit migration"
        )
    required = {"$botpipe", "version", "type", "fields"}
    if kind == "model":
        required |= {"fields_set", "extra"}
    record = _record(value, path, required, optional={"source"})
    version = record["version"]
    if type(version) is not int or version != _STATE_VERSION:
        raise TypeError(f"{path}: unsupported {kind} state version {version!r}")
    if record["$botpipe"] != kind:
        raise TypeError(f"{path}: expected a {kind} durable record")
    if type(record["fields"]) is not dict or not all(
        type(key) is str for key in record["fields"]
    ):
        raise TypeError(f"{path}.fields: durable fields must be a string-keyed object")
    return record


def encoded_body(record):
    """Read a source capsule's value without resolving owners or application types."""

    if type(record) is dict and record.get("$botpipe") == "capsule":
        capsule = _record(
            record,
            "$",
            {"$botpipe", "version", "sources", "value"},
            optional={"owners"},
        )
        if type(capsule["version"]) is not int or capsule["version"] != 1:
            raise TypeError(
                f"$: unsupported source capsule version {capsule['version']!r}"
            )
        _string_mapping(capsule["sources"], "$.sources")
        owners = capsule.get("owners", [])
        if type(owners) is list:
            if not all(type(owner) is str for owner in owners):
                raise TypeError("$.owners: legacy source owners must be path strings")
        elif type(owners) is dict:
            owner_record = _record(
                owners, "$.owners", {"schema", "anchor_kind", "boundaries"}
            )
            if owner_record["schema"] != _OWNER_SCHEMA:
                raise TypeError("$.owners: unsupported source owner schema")
            if owner_record["anchor_kind"] not in {"file", "directory"}:
                raise TypeError("$.owners: invalid source anchor kind")
            boundaries = owner_record["boundaries"]
            if type(boundaries) is not list or not boundaries:
                raise TypeError("$.owners.boundaries: expected a nonempty list")
            for boundary in boundaries:
                item = _record(boundary, "$.owners.boundaries", {"relative", "kind"})
                if item["kind"] not in {"file", "directory"}:
                    raise TypeError("$.owners.boundaries: invalid source boundary kind")
                _portable_owner_relative(item["relative"], "$.owners.boundaries")
        else:
            raise TypeError("$.owners: source owners must be a locator record")
        return capsule["value"]
    return record


def encoded_field(record, name):
    """Return one encoded state field without importing or hydrating its type."""

    record = encoded_body(record)
    if type(record) is not dict:
        raise TypeError("$: durable state record must be an object")
    kind = record.get("$botpipe")
    if kind not in {"model", "dataclass"}:
        raise TypeError(
            f"$: encoded_field requires model or dataclass state, got {kind!r}"
        )
    state = _state_record(record, "$", kind)
    if type(name) is not str:
        raise TypeError("$: durable field name must be a string")
    try:
        return state["fields"][name]
    except KeyError:
        raise KeyError(f"durable {kind} state has no field {name!r}") from None


def verify_sources(value, path="$"):
    """Verify typed envelopes inside an encoded value without hydrating values."""

    sources = {}
    body = value
    if type(value) is dict and value.get("$botpipe") == "capsule":
        record = _record(
            value,
            path,
            {"$botpipe", "version", "sources", "value"},
            optional={"owners"},
        )
        if record["version"] != 1:
            raise TypeError(
                f"{path}: unsupported source capsule version {record['version']!r}"
            )
        sources = _string_mapping(record["sources"], f"{path}.sources")
        for name, identity in sources.items():
            cls = resolve_type(name)
            from .provenance import verify_type_source

            verify_type_source(cls, identity)
        body = record["value"]

    token = _DECODE_SOURCES.set(sources)
    traversal = _Traversal()
    try:

        def visit(item, item_path, depth):
            identity = traversal.visit(
                item, item_path, depth, compound=type(item) in (list, dict)
            )
            try:
                if type(item) is list:
                    for index, child in enumerate(item):
                        visit(child, f"{item_path}[{index}]", depth + 1)
                elif type(item) is dict:
                    kind = item.get("$botpipe")
                    if kind in {"model", "dataclass", "enum", "type"}:
                        cls = resolve_type(item.get("type"))
                        _verify_type_record(cls, item, item_path)
                    if kind in {"dict", "mappingproxy", "artifacts"}:
                        body = item.get("value")
                        if type(body) is dict:
                            for key, child in body.items():
                                visit(child, _child(item_path, key), depth + 1)
                    elif kind in {"tuple", "set", "frozenset"}:
                        body = item.get("value")
                        if type(body) is list:
                            for index, child in enumerate(body):
                                visit(child, f"{item_path}[{index}]", depth + 1)
                    elif kind in {"model", "dataclass"}:
                        fields = item.get("fields")
                        if type(fields) is dict:
                            for key, child in fields.items():
                                visit(child, _child(item_path, key), depth + 1)
                        extra = item.get("extra")
                        if type(extra) is dict:
                            for key, child in extra.items():
                                visit(child, _child(item_path, key), depth + 1)
                    elif kind == "enum" and "value" in item:
                        visit(item["value"], f"{item_path}.value", depth + 1)
            finally:
                traversal.leave(identity)

        visit(body, f"{path}.value" if body is not value else path, 0)
    finally:
        _DECODE_SOURCES.reset(token)


def recorded_source_boundaries(value, root_boundary=None):
    """Return owned boundaries named by one already-verified source capsule."""

    if type(value) is not dict or value.get("$botpipe") != "capsule":
        return ()
    record = _record(
        value,
        "$",
        {"$botpipe", "version", "sources", "value"},
        optional={"owners"},
    )
    sources = _string_mapping(record["sources"], "$.sources")
    from .provenance import type_source_boundary

    owners = record.get("owners", [])
    if type(owners) is list:
        # Version 1 capsules originally stored absolute locations. They remain
        # usable at that exact location, but intentionally gain no relocation
        # semantics retroactively.
        if not all(type(item) is str for item in owners):
            raise TypeError("$.owners: legacy source owners must be path strings")
        result = [Path(item).resolve(strict=True) for item in owners]
    elif type(owners) is dict:
        owner_record = _record(
            owners, "$.owners", {"schema", "anchor_kind", "boundaries"}
        )
        if owner_record["schema"] != _OWNER_SCHEMA:
            raise TypeError(
                f"$.owners: unsupported source owner schema {owner_record['schema']!r}"
            )
        anchor_kind = owner_record["anchor_kind"]
        if anchor_kind not in {"file", "directory"}:
            raise TypeError("$.owners: invalid source anchor kind")
        locators = owner_record["boundaries"]
        if type(locators) is not list or not locators:
            raise TypeError(
                "$.owners.boundaries: source owners must be a nonempty list"
            )
        if root_boundary is None:
            raise TypeError(
                "$.owners: portable source ownership requires the current source anchor"
            )
        anchor = Path(root_boundary).resolve(strict=True)
        if _boundary_kind(anchor) != anchor_kind:
            raise TypeError("$.owners: current source anchor kind changed")
        result = []
        base = anchor if anchor.is_dir() else anchor.parent
        for index, locator in enumerate(locators):
            item = _record(
                locator,
                f"$.owners.boundaries[{index}]",
                {"kind", "relative"},
            )
            relative = item["relative"]
            if item["kind"] not in {"file", "directory"}:
                raise TypeError(
                    f"$.owners.boundaries[{index}]: invalid source owner locator"
                )
            candidate = _resolve_owner_relative(
                base, relative, f"$.owners.boundaries[{index}]"
            )
            if _boundary_kind(candidate) != item["kind"]:
                raise TypeError(
                    f"$.owners.boundaries[{index}]: source owner kind changed"
                )
            result.append(candidate)
        if len(set(result)) != len(result):
            raise TypeError("$.owners: source owner locators are ambiguous")
    else:
        raise TypeError("$.owners: source owners must be a locator record")
    for name, identity in sources.items():
        if type(identity) is dict and identity.get("kind") == "python":
            result.extend(type_source_boundary(resolve_type(name), identity))
    return tuple(dict.fromkeys(result))


def decode(value):
    """Decode a durable value without rerunning application initialization hooks."""

    if type(value) is dict and value.get("$botpipe") == "capsule":
        record = _record(
            value,
            "$",
            {"$botpipe", "version", "sources", "value"},
            optional={"owners"},
        )
        if record["version"] != 1:
            raise TypeError(
                f"$: unsupported source capsule version {record['version']!r}"
            )
        if _SOURCE_BOUNDARY.get() is not None:
            verify_sources(value)
        sources = _string_mapping(record["sources"], "$.sources")
        token = _DECODE_SOURCES.set(sources)
        try:
            return _decode(record["value"], "$.value", 0, _Traversal())
        finally:
            _DECODE_SOURCES.reset(token)
    if _SOURCE_BOUNDARY.get() is not None:
        verify_sources(value)
    return _decode(value, "$", 0, _Traversal())


def _decode(value, path, depth, traversal):
    if type(value) is list:
        identity = traversal.visit(value, path, depth)
        try:
            return [
                _decode(v, f"{path}[{index}]", depth + 1, traversal)
                for index, v in enumerate(value)
            ]
        finally:
            traversal.leave(identity)
    if type(value) is not dict:
        traversal.visit(value, path, depth)
        if value is None or type(value) in (str, int, bool):
            return value
        if type(value) is float and math.isfinite(value):
            return value
        raise TypeError(f"{path}: unsupported encoded value {type(value).__name__}")
    if "$botpipe" not in value:
        raise TypeError(f"{path}: untagged durable mapping state is not supported")
    identity = traversal.visit(value, path, depth)
    try:
        kind = value.get("$botpipe")
        if type(kind) is not str:
            raise TypeError(f"{path}.$botpipe: durable encoding kind must be a string")
        if kind == "artifact":
            record = _record(value, path, {"$botpipe", "value"})
            if type(record["value"]) is not dict:
                raise TypeError(f"{path}.value: artifact record must be an object")
            _plain_json(record["value"], f"{path}.value", depth + 1, traversal)
            from .artifacts import ArtifactHandle

            return ArtifactHandle.from_record(record["value"])
        if kind == "artifacts":
            record = _record(value, path, {"$botpipe", "value"})
            body = _string_mapping(record["value"], f"{path}.value")
            from .artifacts import ArtifactMap

            return ArtifactMap(
                {
                    key: _decode(item, _child(path, key), depth + 1, traversal)
                    for key, item in body.items()
                }
            )
        if kind in {"dict", "mappingproxy"}:
            record = _record(value, path, {"$botpipe", "value"})
            body = _string_mapping(record["value"], f"{path}.value")
            decoded = {
                key: _decode(item, _child(path, key), depth + 1, traversal)
                for key, item in body.items()
            }
            return MappingProxyType(decoded) if kind == "mappingproxy" else decoded
        if kind == "tuple":
            body = _record(value, path, {"$botpipe", "value"})["value"]
            if type(body) is not list:
                raise TypeError(f"{path}.value: tuple state must be an array")
            return tuple(
                _decode(item, f"{path}[{index}]", depth + 1, traversal)
                for index, item in enumerate(body)
            )
        if kind == "bytes":
            body = _record(value, path, {"$botpipe", "value"})["value"]
            if type(body) is not str:
                raise TypeError(f"{path}.value: bytes state must be a string")
            try:
                return base64.b64decode(body, validate=True)
            except ValueError as exc:
                raise TypeError(f"{path}.value: invalid base64 bytes state") from exc
        if kind in ("set", "frozenset"):
            body = _record(value, path, {"$botpipe", "value"})["value"]
            if type(body) is not list:
                raise TypeError(f"{path}.value: {kind} state must be an array")
            decoded = (
                _decode(item, f"{path}[{index}]", depth + 1, traversal)
                for index, item in enumerate(body)
            )
            return (frozenset if kind == "frozenset" else set)(decoded)
        if kind == "path":
            body = _record(value, path, {"$botpipe", "value"})["value"]
            if type(body) is not str:
                raise TypeError(f"{path}.value: path state must be a string")
            return Path(body)
        if kind == "date":
            body = _record(value, path, {"$botpipe", "value"})["value"]
            if type(body) is not str:
                raise TypeError(f"{path}.value: date state must be a string")
            try:
                return date.fromisoformat(body)
            except ValueError as exc:
                raise TypeError(f"{path}.value: invalid date state") from exc
        if kind == "datetime":
            record = _record(value, path, {"$botpipe", "value", "fold", "timezone"})
            body = record["value"]
            if type(body) is not str:
                raise TypeError(f"{path}.value: datetime state must be a string")
            fold = record["fold"]
            if type(fold) is not int or fold not in (0, 1):
                raise TypeError(f"{path}.fold: datetime fold must be 0 or 1")
            try:
                result = datetime.fromisoformat(body)
            except ValueError as exc:
                raise TypeError(f"{path}.value: invalid datetime state") from exc
            if result.tzinfo is not None:
                raise TypeError(
                    f"{path}.value: datetime wall time must not contain an offset"
                )
            timezone_state = record["timezone"]
            tz = None
            if timezone_state is not None:
                timezone_record = _record(
                    timezone_state,
                    f"{path}.timezone",
                    {"offset_microseconds", "name"},
                )
                offset = timezone_record["offset_microseconds"]
                name = timezone_record["name"]
                if type(offset) is not int:
                    raise TypeError(
                        f"{path}.timezone.offset_microseconds: expected an integer"
                    )
                if type(name) is not str:
                    raise TypeError(f"{path}.timezone.name: expected a string")
                try:
                    tz = timezone(timedelta(microseconds=offset), name)
                except (OverflowError, ValueError) as exc:
                    raise TypeError(
                        f"{path}.timezone: invalid fixed-offset timezone"
                    ) from exc
            return result.replace(tzinfo=tz, fold=fold)
        if kind in {"model", "dataclass"}:
            record = _state_record(value, path, kind)
            cls = resolve_type(record["type"])
            _verify_type_record(cls, record, path)
            if kind == "model":
                if not issubclass(cls, BaseModel):
                    raise TypeError(
                        f"{path}.type: {record['type']} is not a Pydantic model"
                    )
                fields = _pydantic_fields(cls, path)
            else:
                if not dataclasses.is_dataclass(cls):
                    raise TypeError(f"{path}.type: {record['type']} is not a dataclass")
                fields = {field.name: field for field in _dataclass_fields(cls, path)}
            if set(record["fields"]) != set(fields):
                raise TypeError(
                    f"{path}.fields: recorded fields do not match {record['type']}"
                )
            if kind == "dataclass":
                decoded_fields = {
                    name: _decode(item, _child(path, name), depth + 1, traversal)
                    for name, item in record["fields"].items()
                }
                instance = object.__new__(cls)
                for name, item in decoded_fields.items():
                    object.__setattr__(instance, name, item)
                return instance
            fields_set = record["fields_set"]
            if (
                type(fields_set) is not list
                or not all(type(name) is str for name in fields_set)
                or len(fields_set) != len(set(fields_set))
            ):
                raise TypeError(
                    f"{path}.fields_set: expected unique field-name strings"
                )
            extra_record = record["extra"]
            if extra_record is not None:
                extra_record = _string_mapping(extra_record, f"{path}.extra")
            allowed_set = set(fields) | set(extra_record or ())
            if not set(fields_set) <= allowed_set:
                raise TypeError(f"{path}.fields_set: names unknown fields")
            if extra_record is not None and cls.model_config.get("extra") != "allow":
                raise TypeError(f"{path}.extra: model does not allow extra fields")
            decoded_fields = {
                name: _decode(item, _child(path, name), depth + 1, traversal)
                for name, item in record["fields"].items()
            }
            decoded_extra = None
            if extra_record is not None:
                decoded_extra = {
                    name: _decode(item, _child(path, name), depth + 1, traversal)
                    for name, item in extra_record.items()
                }
            instance = object.__new__(cls)
            object.__setattr__(instance, "__dict__", decoded_fields)
            object.__setattr__(instance, "__pydantic_fields_set__", set(fields_set))
            if not cls.__pydantic_root_model__:
                object.__setattr__(instance, "__pydantic_extra__", decoded_extra)
                object.__setattr__(instance, "__pydantic_private__", None)
            return instance
        if kind in {"type", "enum"}:
            required = {"$botpipe", "type"}
            if kind == "enum":
                required.add("value")
            record = _record(value, path, required, optional={"source"})
            cls = resolve_type(record["type"])
            _verify_type_record(cls, record, path)
            if kind == "type":
                return cls
            if not issubclass(cls, Enum):
                raise TypeError(f"{path}.type: {record['type']} is not an enum")
            return cls(_decode(record["value"], f"{path}.value", depth + 1, traversal))
        raise TypeError(f"{path}: unknown durable encoding {kind!r}")
    finally:
        traversal.leave(identity)


def dumps(value):
    return json.dumps(
        encode(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def schema_for(annotation):
    if annotation in (None, type(None)):
        return {"type": "null"}
    adapter = _preflight(annotation, "$", None, require_adapter=True)[0]
    return adapter.json_schema()
