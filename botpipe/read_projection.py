"""Read-only projections built from one authoritative journal snapshot."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
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
    execution, operation_revisions = project_execution_provenance(events)
    physical_dispatches = dispatch_records(events)
    operations = []
    artifacts = {}
    total_usage: dict[str, int | float] = {}

    for source in snapshot.operations:
        record = dict(source)
        operation_id = str(record.get("operation_id") or record.get("id") or "")
        record.update(
            operation_revisions.get(
                operation_id,
                {
                    "provenance_state": "unknown",
                    "workflow_identity": None,
                    "surface_id": None,
                    "orchestration_id": None,
                },
            )
        )
        observed = physical_dispatches.get(operation_id)
        if observed:
            record["dispatches"] = observed
            record["usage"] = aggregate_usage(observed)
            record["usage_availability"] = _usage_availability(
                observed, record["usage"]
            )
        else:
            record["usage"] = {}
        for key, value in record["usage"].items():
            if isinstance(value, (int, float)):
                total_usage[key] = total_usage.get(key, 0) + value
        _collect_artifacts(record, artifacts)
        operations.append(record)

    run = dict(snapshot.run)
    run.update(execution)
    return RunReadProjection(
        run=run,
        operations=operations,
        events=events,
        artifacts=ArtifactMap(artifacts),
        usage=total_usage,
    )


def project_execution_revision(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Derive the one provable run revision from its append-only observations."""

    revision, _ = project_execution_provenance(events)
    return revision


def project_execution_provenance(
    events: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Fold execution segments and attribute newly created operations to them."""

    observed_revisions: list[tuple[str, str, str]] = []
    operation_revisions: dict[str, dict[str, Any]] = {}
    open_revision: tuple[str, str, str] | None = None
    open_operations: list[str] | None = None
    unavailable = False

    def unknown() -> dict[str, Any]:
        return {
            "provenance_state": "unknown",
            "workflow_identity": None,
            "surface_id": None,
            "orchestration_id": None,
        }

    def known(revision: tuple[str, str, str]) -> dict[str, Any]:
        return {
            "provenance_state": "known",
            "workflow_identity": revision[0],
            "surface_id": revision[1],
            "orchestration_id": revision[2],
        }

    for event in events:
        event_name = event.get("event")
        if event_name in {"operation_intent", "operation_started"}:
            operation_id = event.get("operation_id")
            if isinstance(operation_id, str) and operation_id:
                if open_operations is None:
                    operation_revisions[operation_id] = unknown()
                    unavailable = True
                else:
                    open_operations.append(operation_id)
            continue
        if event_name != "execution_revision":
            continue
        data = event.get("data")
        phase = data.get("phase") if isinstance(data, Mapping) else None
        revision = _verified_revision(
            data.get("provenance") if isinstance(data, Mapping) else None
        )
        if phase == "start":
            if open_operations is not None:
                for operation_id in open_operations:
                    operation_revisions[operation_id] = unknown()
                unavailable = True
            open_revision = revision
            open_operations = []
            if revision is None:
                unavailable = True
            continue
        if phase == "end" and open_operations is not None:
            if open_revision is not None and revision == open_revision:
                observed_revisions.append(revision)
                attribution = known(revision)
            else:
                unavailable = True
                attribution = unknown()
            for operation_id in open_operations:
                previous = operation_revisions.get(operation_id)
                if previous is not None and previous != attribution:
                    operation_revisions[operation_id] = unknown()
                    unavailable = True
                else:
                    operation_revisions[operation_id] = dict(attribution)
            open_revision = None
            open_operations = None
            continue
        unavailable = True

    if open_operations is not None:
        for operation_id in open_operations:
            operation_revisions[operation_id] = unknown()
        unavailable = True

    unique = set(observed_revisions)
    if unavailable or not unique:
        result = unknown()
    elif len(unique) == 1:
        result = known(next(iter(unique)))
    else:
        result = {
            "provenance_state": "mixed",
            "workflow_identity": None,
            "surface_id": None,
            "orchestration_id": None,
        }
    return result, operation_revisions


def _verified_revision(value: Any) -> tuple[str, str, str] | None:
    if not isinstance(value, Mapping) or value.get("verified") is not True:
        return None
    fields = tuple(
        value.get(key)
        for key in ("workflow_identity", "surface_id", "orchestration_id")
    )
    if not all(isinstance(item, str) and item for item in fields):
        return None
    return fields


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
