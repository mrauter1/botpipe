"""Read-only projections built from one authoritative journal snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import codec
from .artifacts import ArtifactHandle, ArtifactMap
from .dispatches import aggregate_usage, dispatch_records
from .journal import JournalSnapshot


@dataclass(frozen=True)
class RunReadProjection:
    run: dict[str, Any]
    operations: list[dict[str, Any]]
    events: list[dict[str, Any]]
    artifacts: ArtifactMap
    usage: dict[str, int | float]

    def inspection(self):
        return {
            "run": self.run,
            "operations": self.operations,
            "events": self.events,
            "artifacts": self.artifacts.to_record(),
            "usage": self.usage,
        }


def project_run(snapshot: JournalSnapshot) -> RunReadProjection:
    """Build all public read fields from the same committed evidence view."""

    events = [dict(event) for event in snapshot.events]
    physical_dispatches = dispatch_records(events)
    operations = []
    artifacts = {}
    total_usage: dict[str, int | float] = {}

    for source in snapshot.operations:
        record = dict(source)
        observed = physical_dispatches.get(record["id"])
        if observed:
            record["dispatches"] = observed
            record["usage"] = aggregate_usage(observed)
            record["usage_availability"] = _usage_availability(
                observed, record["usage"]
            )
        else:
            # Preserve legacy/manual response usage only when no immutable
            # physical dispatch evidence exists. It must never fill a dispatch
            # whose usage is unknown or partial.
            response = record.get("response") or {}
            record["usage"] = response.get("usage", {})
        for key, value in record["usage"].items():
            if isinstance(value, (int, float)):
                total_usage[key] = total_usage.get(key, 0) + value
        _collect_artifacts(record, artifacts)
        operations.append(record)

    return RunReadProjection(
        run=dict(snapshot.run),
        operations=operations,
        events=events,
        artifacts=ArtifactMap(artifacts),
        usage=total_usage,
    )


def _usage_availability(dispatches, usage):
    if all(item.get("usage_availability") == "known_total" for item in dispatches):
        return "known_total"
    return "partial" if usage else "unknown"


def _collect_artifacts(record, artifacts):
    if record.get("status") != "completed":
        return
    kind = record.get("kind")
    encoded = record.get("result")
    if kind == "provider":
        encoded = codec.encoded_field(encoded, "artifacts")
        handles = _artifact_map(encoded)
    elif kind in {"worklist.complete", "worklist_complete", "read"}:
        handle = _artifact(encoded)
        handles = {} if handle is None else {handle.name: handle}
    else:
        return
    for name, handle in handles.items():
        artifacts[f"{record['scope']}/{record['ordinal']}/{name}"] = handle


def _artifact(encoded):
    encoded = codec.encoded_body(encoded)
    if type(encoded) is dict and encoded.get("$botpipe") == "dict":
        encoded = _inspection_value(encoded)
    if (
        type(encoded) is dict
        and {
            "name",
            "path",
            "source_path",
            "kind",
            "digest",
        }
        <= encoded.keys()
    ):
        return ArtifactHandle.from_record(encoded)
    if type(encoded) is not dict or encoded.get("$botpipe") != "artifact":
        return None
    value = encoded.get("value")
    if type(value) is not dict:
        return None
    return ArtifactHandle.from_record(value)


def _inspection_value(encoded):
    """Decode plain durable containers without resolving application types."""

    if encoded is None or type(encoded) in {str, int, float, bool}:
        return encoded
    if type(encoded) is list:
        return [_inspection_value(item) for item in encoded]
    if type(encoded) is not dict:
        raise TypeError("Artifact record contains an unsupported value")
    kind = encoded.get("$botpipe")
    if kind == "capsule":
        return _inspection_value(codec.encoded_body(encoded))
    if kind == "dict" and type(encoded.get("value")) is dict:
        if not all(type(key) is str for key in encoded["value"]):
            raise TypeError("Artifact record contains a non-string mapping key")
        return {
            key: _inspection_value(value) for key, value in encoded["value"].items()
        }
    if kind == "path" and type(encoded.get("value")) is str:
        return encoded["value"]
    raise TypeError("Artifact record contains non-inspection durable state")


def _artifact_map(encoded):
    encoded = codec.encoded_body(encoded)
    if type(encoded) is not dict or encoded.get("$botpipe") != "artifacts":
        raise TypeError("Provider result artifacts are not an encoded artifact map")
    values = encoded.get("value")
    if type(values) is not dict:
        raise TypeError("Provider result artifacts must be an object")
    handles = {}
    for name, value in values.items():
        handle = _artifact(value)
        if type(name) is not str or handle is None:
            raise TypeError("Provider result contains an invalid artifact record")
        handles[name] = handle
    return handles
