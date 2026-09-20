"""Explicit, bounded JSON state for durable execution; never pickle state."""

from __future__ import annotations

import base64
import dataclasses
import importlib
import json
import math
import re
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType, MemberDescriptorType
from typing import get_args, get_origin

from pydantic import BaseModel, Secret, SecretBytes, SecretStr, TypeAdapter

_TYPES: dict[str, type] = {}
_STATE_VERSION = 1
_MAX_DEPTH = 100
_MAX_VALUES = 100_000
_TYPE_NAME = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[^:\x00\r\n]{1,1000}$")


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


def register_annotation(annotation, _seen=None):
    """Register concrete types reachable from a resolved type annotation."""

    seen = set() if _seen is None else _seen
    identity = id(annotation)
    if identity in seen:
        return
    seen.add(identity)
    origin = get_origin(annotation)
    if origin is not None:
        register_annotation(origin, seen)
        for argument in get_args(annotation):
            register_annotation(argument, seen)
        return
    if not isinstance(annotation, type) or annotation.__module__ == "typing":
        return
    type_name(annotation)
    if issubclass(annotation, BaseModel):
        for field in annotation.model_fields.values():
            register_annotation(field.annotation, seen)
    elif dataclasses.is_dataclass(annotation):
        for field in dataclasses.fields(annotation):
            register_annotation(field.type, seen)


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


def _dataclass_fields(cls, path: str):
    fields = tuple(dataclasses.fields(cls))
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
        if _contains_secret(field.type):
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


def encode(value):
    """Encode a supported value as JSON-compatible, versioned durable state."""

    return _encode(value, "$", 0, _Traversal())


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
            return {
                "$botpipe": "enum",
                "type": type_name(type(value)),
                "value": _encode(value.value, f"{path}.value", depth + 1, traversal),
            }
        if value is None or type(value) in (str, int, bool):
            return value
        if type(value) is float:
            if not math.isfinite(value):
                raise TypeError(f"{path}: non-finite floats are not durable")
            return value
        if isinstance(value, Path) and type(value).__module__ == "pathlib":
            return {"$botpipe": "path", "value": str(value)}
        if type(value) in (datetime, date):
            return {"$botpipe": type(value).__name__, "value": value.isoformat()}
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
            return {
                "$botpipe": "model",
                "version": _STATE_VERSION,
                "type": type_name(cls),
                "fields": encoded_fields,
                "fields_set": sorted(fields_set),
                "extra": encoded_extra,
            }
        if isinstance(value, type):
            return {"$botpipe": "type", "type": type_name(value)}
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
            return {
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
            }
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
    record = _record(value, path, required)
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


def encoded_field(record, name):
    """Return one encoded state field without importing or hydrating its type."""

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


def decode(value):
    """Decode a durable value without rerunning application initialization hooks."""

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
        if kind in {"datetime", "date"}:
            body = _record(value, path, {"$botpipe", "value"})["value"]
            if type(body) is not str:
                raise TypeError(f"{path}.value: {kind} state must be a string")
            try:
                return (datetime if kind == "datetime" else date).fromisoformat(body)
            except ValueError as exc:
                raise TypeError(f"{path}.value: invalid {kind} state") from exc
        if kind in {"model", "dataclass"}:
            record = _state_record(value, path, kind)
            cls = resolve_type(record["type"])
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
            record = _record(value, path, required)
            cls = resolve_type(record["type"])
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
    register_annotation(annotation)
    return TypeAdapter(annotation).json_schema()
