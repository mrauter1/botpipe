"""Explicit JSON values for durable execution; never pickle executable state."""

from __future__ import annotations

import base64
import dataclasses
import importlib
import json
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

_TYPES: dict[str, type] = {}


def type_name(cls):
    name = f"{cls.__module__}:{cls.__qualname__}"
    _TYPES[name] = cls
    return name


def resolve_type(name):
    if name in _TYPES:
        return _TYPES[name]
    module, qualname = name.split(":", 1)
    if "<locals>" in qualname:
        raise TypeError(f"Local type {name} must be registered by the resumed workflow")
    value = importlib.import_module(module)
    for part in qualname.split("."):
        value = getattr(value, part)
    _TYPES[name] = value
    return value


def encode(value):
    from .artifacts import ArtifactHandle, ArtifactMap

    if isinstance(value, ArtifactHandle):
        return {"$botpipe": "artifact", "value": value.to_record()}
    if isinstance(value, ArtifactMap):
        return {
            "$botpipe": "artifacts",
            "value": {k: encode(v) for k, v in value.items()},
        }
    if isinstance(value, Enum):
        return {
            "$botpipe": "enum",
            "type": type_name(type(value)),
            "value": encode(value.value),
        }
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return {"$botpipe": "path", "value": str(value)}
    if isinstance(value, (datetime, date)):
        return {"$botpipe": type(value).__name__, "value": value.isoformat()}
    if isinstance(value, bytes):
        return {"$botpipe": "bytes", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, (set, frozenset)):
        body = sorted(
            (encode(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True)
        )
        return {"$botpipe": type(value).__name__, "value": body}
    if isinstance(value, BaseModel):
        return {
            "$botpipe": "model",
            "type": type_name(type(value)),
            "value": value.model_dump(mode="json"),
        }
    if isinstance(value, type):
        return {"$botpipe": "type", "type": type_name(value)}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            "$botpipe": "dataclass",
            "type": type_name(type(value)),
            "value": {
                f.name: encode(getattr(value, f.name))
                for f in dataclasses.fields(value)
            },
        }
    if isinstance(value, tuple):
        return {"$botpipe": "tuple", "value": [encode(v) for v in value]}
    if isinstance(value, list):
        return [encode(v) for v in value]
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise TypeError("Durable mappings require string keys")
        return {"$botpipe": "dict", "value": {k: encode(v) for k, v in value.items()}}
    raise TypeError(
        f"Unsupported durable value {type(value).__name__}; return typed data or an artifact handle"
    )


def decode(value):
    if isinstance(value, list):
        return [decode(v) for v in value]
    if not isinstance(value, dict) or "$botpipe" not in value:
        return value
    kind, body = value["$botpipe"], value.get("value")
    if kind == "artifact":
        from .artifacts import ArtifactHandle

        return ArtifactHandle.from_record(body)
    if kind == "artifacts":
        from .artifacts import ArtifactMap

        return ArtifactMap({k: decode(v) for k, v in body.items()})
    if kind == "dict":
        return {k: decode(v) for k, v in body.items()}
    if kind == "tuple":
        return tuple(decode(v) for v in body)
    if kind == "bytes":
        return base64.b64decode(body, validate=True)
    if kind in ("set", "frozenset"):
        return (frozenset if kind == "frozenset" else set)(decode(v) for v in body)
    if kind == "path":
        return Path(body)
    if kind == "datetime":
        return datetime.fromisoformat(body)
    if kind == "date":
        return date.fromisoformat(body)
    cls = resolve_type(value["type"])
    if kind == "type":
        return cls
    if kind == "model":
        return cls.model_validate(body)
    if kind == "enum":
        return cls(decode(body))
    if kind == "dataclass":
        return cls(**{k: decode(v) for k, v in body.items()})
    raise TypeError(f"Unknown durable encoding {kind}")


def dumps(value):
    return json.dumps(
        encode(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def schema_for(annotation):
    if annotation in (None, type(None)):
        return {"type": "null"}
    if isinstance(annotation, type):
        type_name(annotation)
    return TypeAdapter(annotation).json_schema()
