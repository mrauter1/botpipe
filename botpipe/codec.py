"""Explicit, bounded JSON state for durable execution; never pickle state."""

from __future__ import annotations

import base64
import dataclasses
import importlib
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from enum import CONFORM, EJECT, KEEP, STRICT, Enum, Flag
from inspect import get_annotations, getattr_static
from pathlib import Path
from types import MappingProxyType, MemberDescriptorType, SimpleNamespace, UnionType
from typing import (
    Annotated,
    Any,
    ForwardRef,
    Literal,
    TypeAliasType,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

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
    module, qualname = name.split(":", 1)
    if "<locals>" in qualname:
        if name in _TYPES:
            return _TYPES[name]
        raise TypeError(f"Local type {name} must be registered by the resumed workflow")
    # Generated generic classes (for example Model[int]) cannot be recovered by
    # attribute traversal. schema_for() registers annotated generated classes.
    if any(character in qualname for character in "[] ,"):
        if name in _TYPES:
            return _TYPES[name]
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


class _Contracts:
    """Build canonical storage contracts with operation-local bounded memoization."""

    def __init__(self):
        self.memo = {}
        self.active = set()
        self.alias_memo = {}
        self.active_aliases = set()
        self.value_traversal = _Traversal()
        self.count = 0

    def _visit(self, path, depth):
        self.count += 1
        if self.count > _MAX_VALUES:
            raise TypeError(
                f"{path}: durable contract exceeds the {_MAX_VALUES}-value limit"
            )
        if depth > _MAX_DEPTH:
            raise TypeError(
                f"{path}: durable contract exceeds the {_MAX_DEPTH}-level limit"
            )

    def annotation(self, annotation, path, depth=0):
        self._visit(path, depth)
        if annotation is None or annotation is type(None):
            return {"kind": "none"}
        if annotation is ...:
            return {"kind": "ellipsis"}
        if annotation is Annotated or get_origin(annotation) is Annotated:
            arguments = get_args(annotation)
            target = arguments[0] if arguments else annotation
            return self.annotation(target, path, depth + 1)
        if isinstance(annotation, str):
            return {"kind": "forward", "name": annotation}
        if isinstance(annotation, ForwardRef):
            return {"kind": "forward", "name": annotation.__forward_arg__}
        if _is_type_alias(annotation):
            return self.alias(annotation, path, depth + 1)
        if isinstance(annotation, TypeVar):
            record = {"kind": "typevar", "name": annotation.__name__}
            if annotation.__constraints__:
                record["constraints"] = sorted(
                    (
                        self.annotation(item, path, depth + 1)
                        for item in annotation.__constraints__
                    ),
                    key=_canonical_key,
                )
            elif annotation.__bound__ is not None:
                record["bound"] = self.annotation(annotation.__bound__, path, depth + 1)
            return record
        origin = get_origin(annotation)
        if origin is not None:
            if _is_type_alias(origin):
                return {
                    "kind": "generic-alias",
                    "value": self.alias(origin, path, depth + 1),
                    "arguments": [
                        self.annotation(item, path, depth + 1)
                        for item in get_args(annotation)
                    ],
                }
            if origin is Literal:
                values = [
                    self.literal(item, path, depth + 1) for item in get_args(annotation)
                ]
                values.sort(key=_canonical_key)
                return {
                    "kind": "literal",
                    "values": values,
                }
            arguments = [
                self.annotation(item, path, depth + 1) for item in get_args(annotation)
            ]
            if origin in (Union, UnionType):
                arguments.sort(key=_canonical_key)
                return {"kind": "union", "arguments": arguments}
            origin_record = (
                self.annotation(origin, path, depth + 1)
                if isinstance(origin, type)
                else {"kind": "typing", "name": str(origin)}
            )
            return {
                "kind": "generic",
                "origin": origin_record,
                "arguments": arguments,
            }
        if annotation is Any:
            return {"kind": "any"}
        if isinstance(annotation, type):
            return {"kind": "type", "name": type_name(annotation)}
        if type(annotation) in (str, int, bool) or annotation is None:
            return {"kind": "literal", "value": annotation}
        if type(annotation) is float and math.isfinite(annotation):
            return {"kind": "literal", "value": annotation}
        if getattr(annotation, "__module__", None) == "typing":
            return {"kind": "typing", "name": str(annotation)}
        raise TypeError(f"{path}: unsupported durable field annotation {annotation!r}")

    def alias(self, alias, path, depth):
        cached = self.alias_memo.get(alias)
        if cached is not None:
            return cached
        if alias in self.active_aliases:
            return {"kind": "recursive-alias"}
        self.active_aliases.add(alias)
        try:
            contract = self.annotation(alias.__value__, path, depth + 1)
            self.alias_memo[alias] = contract
            return contract
        finally:
            self.active_aliases.remove(alias)

    def literal(self, value, path, depth):
        self._visit(path, depth)
        if value is None or type(value) in (str, int, bool):
            return value
        if type(value) is float and math.isfinite(value):
            return value
        if type(value) is bytes:
            return {"bytes": base64.b64encode(value).decode("ascii")}
        if isinstance(value, Enum):
            return {
                "enum": type_name(type(value)),
                "member": value.name,
            }
        if isinstance(value, type):
            return {"type": type_name(value)}
        raise TypeError(f"{path}: unsupported durable literal {value!r}")

    def for_type(self, cls, path, depth=0):
        self._visit(path, depth)
        cached = self.memo.get(cls)
        if cached is not None:
            return cached
        name = type_name(cls)
        if cls in self.active:
            return {"kind": "reference", "type": name}
        self.active.add(cls)
        try:
            if issubclass(cls, Enum):
                members = []
                for member_name, member in sorted(cls.__members__.items()):
                    members.append(
                        [
                            member_name,
                            _encode(
                                member.value,
                                f"{path}.members[{member_name!r}]",
                                depth + 1,
                                self.value_traversal,
                                self,
                            ),
                        ]
                    )
                contract = {
                    "kind": "enum",
                    "type": name,
                    "member_type": type_name(cls._member_type_),
                    "flag": issubclass(cls, Flag),
                    "members": members,
                }
            elif issubclass(cls, BaseException):
                slots = []
                for owner in cls.__mro__:
                    if owner is BaseException:
                        continue
                    for slot_name, descriptor in vars(owner).items():
                        if isinstance(descriptor, MemberDescriptorType):
                            slots.append([type_name(owner), slot_name])
                slots.sort()
                if issubclass(cls, OSError):
                    native_family = type_name(OSError)
                elif cls.__module__ == "builtins":
                    native_family = name
                else:
                    native_family = type_name(
                        next(
                            base
                            for base in cls.__mro__[1:]
                            if base.__module__ == "builtins"
                            and issubclass(base, BaseException)
                        )
                    )
                contract = {
                    "kind": "exception",
                    "type": name,
                    "native_family": native_family,
                    "slots": slots,
                }
            elif issubclass(cls, BaseModel):
                fields = _pydantic_fields(cls, path)
                resolved = _resolved_class_annotations(cls)
                contract = {
                    "kind": "model",
                    "type": name,
                    "fields": [
                        [
                            field_name,
                            self.annotation(
                                _pydantic_annotation(field_name, field, resolved),
                                _child(path, field_name),
                                depth + 1,
                            ),
                        ]
                        for field_name, field in sorted(fields.items())
                    ],
                    "extra": cls.model_config.get("extra") == "allow",
                    "root": bool(cls.__pydantic_root_model__),
                }
            elif dataclasses.is_dataclass(cls):
                _, namespace = _annotation_namespaces(cls)
                fields = _dataclass_fields(cls, path, localns=namespace)
                resolved = _resolved_class_annotations(cls, namespace)
                contract = {
                    "kind": "dataclass",
                    "type": name,
                    "fields": [
                        [
                            field.name,
                            self.annotation(
                                resolved.get(field.name, field.type),
                                _child(path, field.name),
                                depth + 1,
                            ),
                        ]
                        for field in sorted(fields, key=lambda field: field.name)
                    ],
                }
            else:
                contract = {"kind": "type", "type": name}
            self.memo[cls] = contract
            return contract
        finally:
            self.active.remove(cls)


def _canonical_key(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _is_type_alias(value):
    return isinstance(value, TypeAliasType) or (
        type(value).__name__ == "TypeAliasType"
        and type(value).__module__ == "typing_extensions"
    )


_NO_STANDARD_FLAG_RESULT = object()
_FLAG_INSTANCE_FIELDS = frozenset({"_value_", "_name_", "_inverted_"})


def _flag_has_native_instance_state(value):
    """Return whether a pseudo-member has only core state and disposable caches."""

    try:
        state = object.__getattribute__(value, "__dict__")
    except AttributeError:
        state = {}
    if any(name not in _FLAG_INSTANCE_FIELDS for name in state):
        return False
    for owner in type(value).__mro__:
        for name, descriptor in vars(owner).items():
            if name in _FLAG_INSTANCE_FIELDS or not isinstance(
                descriptor, MemberDescriptorType
            ):
                continue
            try:
                descriptor.__get__(value, type(value))
            except AttributeError:
                continue
            return False
    return True


def _flag_hook(cls, name):
    hook = getattr_static(cls, name)
    return getattr(hook, "__func__", hook)


def _standard_flag_result(cls, raw):
    """Predict stdlib Flag._missing_ output without invoking application hooks."""

    member_type = cls._member_type_
    if getattr_static(cls, "__setattr__") is not getattr_static(
        member_type, "__setattr__"
    ) or getattr_static(cls, "__getattribute__") is not getattr_static(
        member_type, "__getattribute__"
    ):
        return _NO_STANDARD_FLAG_RESULT
    try:
        getattr_static(cls, "__getattr__")
    except AttributeError:
        pass
    else:
        return _NO_STANDARD_FLAG_RESULT
    if _flag_hook(cls, "_missing_") is not _flag_hook(Flag, "_missing_"):
        return _NO_STANDARD_FLAG_RESULT

    value = raw
    flag_mask = cls._flag_mask_
    singles_mask = cls._singles_mask_
    all_bits = cls._all_bits_
    boundary = cls._boundary_
    if not ~all_bits <= value <= all_bits or value & (all_bits ^ flag_mask):
        if boundary is STRICT:
            return _NO_STANDARD_FLAG_RESULT
        if boundary is CONFORM:
            value &= flag_mask
        elif boundary is EJECT:
            return _NO_STANDARD_FLAG_RESULT
        elif boundary is KEEP:
            if value < 0:
                value = max(all_bits + 1, 2 ** value.bit_length()) + value
        else:
            return _NO_STANDARD_FLAG_RESULT
    if value < 0:
        value = all_bits + 1 + value

    unknown = value & ~flag_mask
    aliases = value & ~singles_mask
    member_value = value & singles_mask
    if unknown and boundary is not KEEP:
        return _NO_STANDARD_FLAG_RESULT
    if not (member_value or aliases):
        return value, None

    iterator = _flag_hook(cls, "_iter_member_")
    by_value = _flag_hook(Flag, "_iter_member_by_value_")
    by_definition = _flag_hook(Flag, "_iter_member_by_def_")
    if iterator not in (by_value, by_definition):
        return _NO_STANDARD_FLAG_RESULT
    if (
        iterator is by_definition
        and _flag_hook(cls, "_iter_member_by_value_") is not by_value
    ):
        return _NO_STANDARD_FLAG_RESULT
    members = []
    remaining = member_value & flag_mask
    while remaining:
        bit = remaining & -remaining
        member = cls._value2member_map_.get(bit)
        if member is None:
            return _NO_STANDARD_FLAG_RESULT
        members.append(member)
        remaining ^= bit
    if iterator is by_definition:
        if any(
            type(object.__getattribute__(member, "_sort_order_")) is not int
            for member in members
        ):
            return _NO_STANDARD_FLAG_RESULT
        members.sort(key=lambda member: object.__getattribute__(member, "_sort_order_"))

    combined_value = 0
    for member in members:
        combined_value |= object.__getattribute__(member, "_value_")
    if aliases:
        equality = getattr_static(cls, "__eq__")
        native_equality = object.__eq__ if cls._member_type_ is object else int.__eq__
        if (members or len(cls._member_map_) > 1) and equality is not native_equality:
            return _NO_STANDARD_FLAG_RESULT
        for member in cls._member_map_.values():
            if any(member is present for present in members):
                continue
            member_raw = object.__getattribute__(member, "_value_")
            if member_raw and member_raw & value == member_raw:
                members.append(member)
                combined_value |= member_raw

    unknown = value ^ combined_value
    names = [object.__getattribute__(member, "_name_") for member in members]
    if any(type(name) is not str for name in names):
        return _NO_STANDARD_FLAG_RESULT
    name = "|".join(names)
    if not combined_value:
        name = None
    elif unknown and boundary is STRICT:
        return _NO_STANDARD_FLAG_RESULT
    elif unknown:
        if getattr_static(cls, "_numeric_repr_") is not repr:
            return _NO_STANDARD_FLAG_RESULT
        name += f"|{unknown!r}"
    return value, name


def _new_flag_member(cls, raw, name):
    if cls._member_type_ is object:
        member = object.__new__(cls)
    else:
        member = int.__new__(cls, raw)
    object.__setattr__(member, "_value_", raw)
    object.__setattr__(member, "_name_", name)
    return member


def _compatible_cached_flag_member(member, cls, raw, name):
    if type(member) is not cls:
        return False
    try:
        member_raw = object.__getattribute__(member, "_value_")
        member_name = object.__getattribute__(member, "_name_")
    except AttributeError:
        return False
    return (
        type(member_raw) is int
        and member_raw == raw
        and type(member_name) is type(name)
        and member_name == name
        and _flag_has_native_instance_state(member)
    )


def encode(value):
    """Encode supported values with canonical, source-free storage contracts."""

    return _encode(value, "$", 0, _Traversal(), _Contracts())


def _encode(value, path, depth, traversal, contracts):
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
                    k: _encode(v, _child(path, k), depth + 1, traversal, contracts)
                    for k, v in items
                },
            }
        if isinstance(value, Enum):
            cls = type(value)
            member = value.name
            declared = (
                type(member) is str
                and member in cls.__members__
                and cls.__members__[member] is value
            )
            if not declared:
                if (
                    not isinstance(value, Flag)
                    or cls._member_type_ not in (object, int)
                    or type(value.value) is not int
                ):
                    raise TypeError(f"{path}: unsupported unnamed enum value")
                if not _flag_has_native_instance_state(value):
                    raise TypeError(
                        f"{path}: pseudo-member has unsupported instance state"
                    )
            return {
                "$botpipe": "enum",
                "type": type_name(cls),
                "contract": contracts.for_type(cls, f"{path}.contract"),
                "member": member,
                "value": _encode(
                    value.value, f"{path}.value", depth + 1, traversal, contracts
                ),
            }
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
            body = [
                _encode(v, f"{path}[set]", depth + 1, traversal, contracts)
                for v in value
            ]
            body.sort(key=_canonical_key)
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
                name: _encode(
                    state[name], _child(path, name), depth + 1, traversal, contracts
                )
                for name in fields
            }
            encoded_extra = None
            if extra is not None:
                encoded_extra = {
                    key: _encode(
                        item, _child(path, key), depth + 1, traversal, contracts
                    )
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
                "contract": contracts.for_type(cls, f"{path}.contract"),
                "fields": encoded_fields,
                "fields_set": sorted(fields_set),
                "extra": encoded_extra,
            }
        if isinstance(value, type):
            return {
                "$botpipe": "type",
                "type": type_name(value),
                "contract": contracts.for_type(value, f"{path}.contract"),
            }
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
                "contract": contracts.for_type(cls, f"{path}.contract"),
                "fields": {
                    field.name: _encode(
                        object.__getattribute__(value, field.name),
                        _child(path, field.name),
                        depth + 1,
                        traversal,
                        contracts,
                    )
                    for field in fields
                },
            }
        if type(value) is tuple:
            return {
                "$botpipe": "tuple",
                "value": [
                    _encode(v, f"{path}[{index}]", depth + 1, traversal, contracts)
                    for index, v in enumerate(value)
                ],
            }
        if type(value) is list:
            return [
                _encode(v, f"{path}[{index}]", depth + 1, traversal, contracts)
                for index, v in enumerate(value)
            ]
        if type(value) is dict:
            mapping = _string_mapping(value, path)
            return {
                "$botpipe": "dict",
                "value": {
                    k: _encode(v, _child(path, k), depth + 1, traversal, contracts)
                    for k, v in mapping.items()
                },
            }
        if isinstance(value, MappingProxyType):
            mapping = _string_mapping(value, path)
            return {
                "$botpipe": "mappingproxy",
                "value": {
                    k: _encode(v, _child(path, k), depth + 1, traversal, contracts)
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
    required = {"$botpipe", "version", "type", "contract", "fields"}
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


def _verify_datetime_record(record, path):
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
        raise TypeError(f"{path}.value: datetime wall time must not contain an offset")
    timezone_state = record["timezone"]
    if timezone_state is None:
        return
    timezone_record = _record(
        timezone_state,
        f"{path}.timezone",
        {"offset_microseconds", "name"},
    )
    offset = timezone_record["offset_microseconds"]
    name = timezone_record["name"]
    if type(offset) is not int:
        raise TypeError(f"{path}.timezone.offset_microseconds: expected an integer")
    if type(name) is not str:
        raise TypeError(f"{path}.timezone.name: expected a string")
    try:
        timezone(timedelta(microseconds=offset), name)
    except (OverflowError, ValueError) as exc:
        raise TypeError(f"{path}.timezone: invalid fixed-offset timezone") from exc


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


def verify_contracts(value, path="$"):
    """Verify every typed storage contract without hydrating recorded values."""

    traversal = _Traversal()
    contracts = _Contracts()
    contract_traversal = _Traversal()
    verified_contracts = {}

    def visit(item, item_path, depth):
        identity = traversal.visit(
            item, item_path, depth, compound=type(item) in (list, dict)
        )
        try:
            if type(item) is list:
                for index, child in enumerate(item):
                    visit(child, f"{item_path}[{index}]", depth + 1)
                return
            if type(item) is not dict:
                if item is None or type(item) in (str, int, bool):
                    return
                if type(item) is float and math.isfinite(item):
                    return
                raise TypeError(
                    f"{item_path}: unsupported encoded value {type(item).__name__}"
                )
            if "$botpipe" not in item:
                raise TypeError(
                    f"{item_path}: untagged durable mapping state is not supported"
                )
            kind = item.get("$botpipe")
            if type(kind) is not str:
                raise TypeError(
                    f"{item_path}.$botpipe: durable encoding kind must be a string"
                )
            if kind in {"model", "dataclass"}:
                record = _state_record(item, item_path, kind)
                actual, _cls = _verify_contract(
                    record,
                    item_path,
                    contracts,
                    contract_traversal,
                    verified_contracts,
                    depth,
                )
                if actual["kind"] != kind:
                    label = "Pydantic model" if kind == "model" else "dataclass"
                    raise TypeError(
                        f"{item_path}.type: {record['type']} is not a {label}"
                    )
                field_names = {name for name, _ in actual["fields"]}
                if set(record["fields"]) != field_names:
                    raise TypeError(
                        f"{item_path}.fields: recorded fields do not match "
                        f"{record['type']}"
                    )
                if kind == "model":
                    fields_set = record["fields_set"]
                    if (
                        type(fields_set) is not list
                        or not all(type(name) is str for name in fields_set)
                        or len(fields_set) != len(set(fields_set))
                    ):
                        raise TypeError(
                            f"{item_path}.fields_set: expected unique "
                            "field-name strings"
                        )
                    extra = record["extra"]
                    if extra is not None:
                        extra = _string_mapping(extra, f"{item_path}.extra")
                        if not actual["extra"]:
                            raise TypeError(
                                f"{item_path}.extra: model does not allow extra fields"
                            )
                        overlap = field_names & set(extra)
                        if overlap:
                            raise TypeError(
                                f"{item_path}.extra: duplicates declared fields "
                                f"{sorted(overlap)!r}"
                            )
                    if not set(fields_set) <= field_names | set(extra or ()):
                        raise TypeError(f"{item_path}.fields_set: names unknown fields")
                for key, child in record["fields"].items():
                    visit(child, _child(item_path, key), depth + 1)
                extra = record.get("extra")
                if extra is not None:
                    for key, child in _string_mapping(
                        extra, f"{item_path}.extra"
                    ).items():
                        visit(child, _child(f"{item_path}.extra", key), depth + 1)
                return
            if kind == "type":
                record = _record(item, item_path, {"$botpipe", "type", "contract"})
                _verify_contract(
                    record,
                    item_path,
                    contracts,
                    contract_traversal,
                    verified_contracts,
                    depth,
                )
                return
            if kind == "enum":
                record = _record(
                    item,
                    item_path,
                    {"$botpipe", "type", "contract", "member", "value"},
                )
                actual, cls = _verify_contract(
                    record,
                    item_path,
                    contracts,
                    contract_traversal,
                    verified_contracts,
                    depth,
                )
                if not issubclass(cls, Enum) or actual["kind"] != "enum":
                    raise TypeError(
                        f"{item_path}.type: {record['type']} is not an enum"
                    )
                member = record["member"]
                members = dict(actual["members"])
                visit(record["value"], f"{item_path}.value", depth + 1)
                if type(member) is str and member in members:
                    expected = members[member]
                elif (
                    issubclass(cls, Flag)
                    and cls._member_type_ in (object, int)
                    and (member is None or type(member) is str)
                    and type(record["value"]) is int
                ):
                    expected = record["value"]
                else:
                    raise TypeError(f"{item_path}.member: invalid enum member")
                if _canonical_key(record["value"]) != _canonical_key(expected):
                    raise TypeError(
                        f"{item_path}.value: recorded enum value does not match "
                        f"{record['type']}.{member}"
                    )
                return
            if kind == "artifact":
                record = _record(item, item_path, {"$botpipe", "value"})
                body = record["value"]
                if type(body) is not dict:
                    raise TypeError(
                        f"{item_path}.value: artifact record must be an object"
                    )
                artifact = _record(
                    body,
                    f"{item_path}.value",
                    {"name", "path", "source_path", "kind", "digest", "schema"},
                )
                for key in ("name", "path", "source_path", "kind", "digest"):
                    if type(artifact[key]) is not str:
                        raise TypeError(f"{item_path}.value.{key}: expected a string")
                if (
                    artifact["schema"] is not None
                    and type(artifact["schema"]) is not dict
                ):
                    raise TypeError(
                        f"{item_path}.value.schema: expected an object or null"
                    )
                _plain_json(body, f"{item_path}.value", depth + 1, traversal)
                return
            if kind in {"dict", "mappingproxy", "artifacts"}:
                record = _record(item, item_path, {"$botpipe", "value"})
                body = _string_mapping(record["value"], f"{item_path}.value")
                for key, child in body.items():
                    visit(child, _child(item_path, key), depth + 1)
                return
            if kind in {"tuple", "set", "frozenset"}:
                body = _record(item, item_path, {"$botpipe", "value"})["value"]
                if type(body) is not list:
                    raise TypeError(f"{item_path}.value: {kind} state must be an array")
                for index, child in enumerate(body):
                    visit(child, f"{item_path}[{index}]", depth + 1)
                return
            if kind in {"bytes", "path", "date"}:
                body = _record(item, item_path, {"$botpipe", "value"})["value"]
                if type(body) is not str:
                    raise TypeError(f"{item_path}.value: {kind} state must be a string")
                if kind == "bytes":
                    try:
                        base64.b64decode(body, validate=True)
                    except ValueError as exc:
                        raise TypeError(
                            f"{item_path}.value: invalid base64 bytes state"
                        ) from exc
                elif kind == "date":
                    try:
                        date.fromisoformat(body)
                    except ValueError as exc:
                        raise TypeError(
                            f"{item_path}.value: invalid date state"
                        ) from exc
                return
            if kind == "datetime":
                record = _record(
                    item,
                    item_path,
                    {"$botpipe", "value", "fold", "timezone"},
                )
                _verify_datetime_record(record, item_path)
                return
            raise TypeError(f"{item_path}: unknown durable encoding {kind!r}")
        finally:
            traversal.leave(identity)

    visit(value, path, 0)


def _verify_contract(
    record, path, contracts, contract_traversal, verified_contracts, depth
):
    stored = record["contract"]
    cls = resolve_type(record["type"])
    actual = contracts.for_type(cls, f"{path}.contract")
    expected = verified_contracts.get(record["type"])
    if expected is None:
        _plain_json(stored, f"{path}.contract", 0, contract_traversal)
        expected = _canonical_key(actual)
        verified_contracts[record["type"]] = expected
    try:
        encoded_stored = _canonical_key(stored)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{path}.contract: invalid storage contract") from exc
    if encoded_stored != expected:
        raise TypeError(f"{path}: storage contract for {record['type']} changed")
    return actual, cls


def decode(value):
    """Decode durable state without rerunning application initialization hooks."""

    verify_contracts(value)
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
            required = {"$botpipe", "type", "contract"}
            if kind == "enum":
                required |= {"member", "value"}
            record = _record(value, path, required)
            cls = resolve_type(record["type"])
            if kind == "type":
                return cls
            if not issubclass(cls, Enum):
                raise TypeError(f"{path}.type: {record['type']} is not an enum")
            composite = record["member"]
            if type(composite) is str:
                member = cls.__members__.get(composite)
                if member is not None:
                    return member
            if (
                issubclass(cls, Flag)
                and cls._member_type_ in (object, int)
                and (composite is None or type(composite) is str)
            ):
                raw = record["value"]
                cached = cls._value2member_map_.get(raw)
                if cached is not None and _compatible_cached_flag_member(
                    cached, cls, raw, composite
                ):
                    return cached
                member = _new_flag_member(cls, raw, composite)
                if _standard_flag_result(cls, raw) != (raw, composite):
                    return member
                winner = cls._value2member_map_.setdefault(raw, member)
                if _compatible_cached_flag_member(winner, cls, raw, composite):
                    return winner
                return member
            raise TypeError(
                f"{path}.member: {record['member']!r} is not a member of "
                f"{record['type']}"
            )
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
