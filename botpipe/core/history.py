"""Read-only run history and derived telemetry helpers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .schema_registry import (
    CHECKPOINT_SCHEMA,
    RUNTIME_EVENT_SCHEMA,
    RUNTIME_TRACE_SCHEMA,
    migrate_schemaless_payload,
    validate_persisted_schema,
)
from .statuses import finalization_to_step_status, route_to_step_status


DEFAULT_ACCEPTED_ROUTE_TAGS = frozenset({"done", "accepted", "approved"})
_STATUS_PRIORITY = {
    "failed": 5,
    "running": 4,
    "awaiting_input": 3,
    "completed": 2,
    "pending": 1,
}


@dataclass(frozen=True, slots=True)
class StepInstanceKey:
    """Stable telemetry key for one step instance."""

    step_name: str
    scope: str | None = None
    item_id: str | None = None


@dataclass(slots=True)
class _TelemetryAccumulator:
    step_name: str
    scope: str | None
    item_id: str | None
    started_count: int = 0
    finished_count: int = 0
    accepted_once: bool = False
    latest_route: str | None = None
    latest_timestamp: str | None = None
    last_status: str = "pending"
    first_started_at: str | None = None
    last_started_at: str | None = None
    first_finished_at: str | None = None
    last_finished_at: str | None = None
    total_duration_seconds: float = 0.0
    latest_duration_seconds: float | None = None
    errors: list[dict[str, Any]] = None  # type: ignore[assignment]
    artifact_validation_failures: list[dict[str, Any]] = None  # type: ignore[assignment]
    routes: list[dict[str, Any]] = None  # type: ignore[assignment]
    attempt_keys: dict[str, set[tuple[str | None, int]]] = None  # type: ignore[assignment]
    token_usage_from_attempts: dict[str, dict[str, int]] = None  # type: ignore[assignment]
    token_usage_from_step_finished: dict[str, dict[str, int]] = None  # type: ignore[assignment]
    execution_starts: dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []
        if self.artifact_validation_failures is None:
            self.artifact_validation_failures = []
        if self.routes is None:
            self.routes = []
        if self.attempt_keys is None:
            self.attempt_keys = defaultdict(set)
        if self.token_usage_from_attempts is None:
            self.token_usage_from_attempts = {}
        if self.token_usage_from_step_finished is None:
            self.token_usage_from_step_finished = {}
        if self.execution_starts is None:
            self.execution_starts = {}


@dataclass(frozen=True, slots=True)
class _HistoryIndex:
    trace_records: tuple[dict[str, Any], ...]
    event_records: tuple[dict[str, Any], ...]
    telemetry_by_key: dict[StepInstanceKey, dict[str, Any]]
    failure_records: tuple[dict[str, Any], ...]
    route_records: tuple[dict[str, Any], ...]


class HistoryReader:
    """Read-only history reader bound to one run directory."""

    def __init__(self, run_folder: Path) -> None:
        self._run_folder = run_folder.resolve()
        self._trace_file = self._run_folder / "trace.jsonl"
        self._events_file = self._run_folder / "events.jsonl"
        self._checkpoint_file = self._run_folder / "checkpoint.json"
        self._jsonl_cache: dict[Path, tuple[tuple[bool, int, int], tuple[dict[str, Any], ...]]] = {}
        self._object_cache: dict[Path, tuple[tuple[bool, int, int], dict[str, Any] | None]] = {}
        self._index_cache: tuple[tuple[tuple[bool, int, int], tuple[bool, int, int], tuple[bool, int, int]], _HistoryIndex] | None = None

    def events(self) -> tuple[dict[str, Any], ...]:
        return self._index().event_records

    def trace(self) -> tuple[dict[str, Any], ...]:
        return self._index().trace_records

    def routes(
        self,
        *,
        step: str | None = None,
        scope: str | None = None,
        item_id: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        records = self._index().route_records
        return tuple(
            record
            for record in records
            if _route_matches(record, step=step, scope=scope, item_id=item_id)
        )

    def failures(
        self,
        step: str | None = None,
        *,
        scope: str | None = None,
        item_id: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        records = self._index().failure_records
        return tuple(
            record
            for record in records
            if _failure_matches(record, step=step, scope=scope, item_id=item_id)
        )

    def token_usage(
        self,
        step: str | None = None,
        *,
        scope: str | None = None,
        item_id: str | None = None,
    ) -> dict[str, dict[str, int]]:
        telemetry = self.step_telemetry(step, scope=scope, item_id=item_id)
        if isinstance(telemetry, dict) and telemetry and all(isinstance(key, StepInstanceKey) for key in telemetry):
            combined = _empty_token_usage()
            for payload in telemetry.values():
                _merge_token_usage(combined, payload.get("token_usage"))
            return _prune_token_usage(combined)
        if isinstance(telemetry, dict):
            return _prune_token_usage(_copy_token_usage(telemetry.get("token_usage")))
        return {}

    def step_telemetry(
        self,
        step: str | None = None,
        *,
        scope: str | None = None,
        item_id: str | None = None,
        success_routes: set[str] | frozenset[str] | tuple[str, ...] | None = None,
    ) -> dict[StepInstanceKey, dict[str, Any]] | dict[str, Any]:
        index = self._index()
        if success_routes is None or set(success_routes) == set(DEFAULT_ACCEPTED_ROUTE_TAGS):
            telemetry_by_key = index.telemetry_by_key
        else:
            telemetry_by_key = self._recompute_telemetry(success_routes=frozenset(success_routes))
        if step is None:
            return {
                key: payload
                for key, payload in telemetry_by_key.items()
                if _step_key_matches(key, step=None, scope=scope, item_id=item_id)
            }
        matching = [
            payload
            for key, payload in telemetry_by_key.items()
            if _step_key_matches(key, step=step, scope=scope, item_id=item_id)
        ]
        if not matching:
            return _empty_telemetry(step_name=step, scope=scope, item_id=item_id)
        if item_id is not None or any(
            payload.get("item_id") == item_id and payload.get("scope") == scope for payload in matching
        ):
            return dict(matching[0])
        return _merge_telemetry_payloads(
            matching,
            step_name=step,
            scope=scope,
            item_id=item_id,
        )

    def _index(self) -> _HistoryIndex:
        signature = (
            _path_signature(self._trace_file),
            _path_signature(self._events_file),
            _path_signature(self._checkpoint_file),
        )
        if self._index_cache is not None and self._index_cache[0] == signature:
            return self._index_cache[1]
        index = self._build_index()
        self._index_cache = (signature, index)
        return index

    def _build_index(self) -> _HistoryIndex:
        trace_records = self._read_jsonl(self._trace_file)
        event_records = self._read_jsonl(self._events_file)
        checkpoint_payload = self._read_json_object(self._checkpoint_file)
        success_routes = DEFAULT_ACCEPTED_ROUTE_TAGS
        if trace_records:
            telemetry_by_key, failure_records, route_records = self._telemetry_from_trace(
                trace_records,
                checkpoint_payload=checkpoint_payload,
                success_routes=success_routes,
            )
        else:
            telemetry_by_key, failure_records, route_records = self._telemetry_from_events(
                event_records,
                checkpoint_payload=checkpoint_payload,
                success_routes=success_routes,
            )
        return _HistoryIndex(
            trace_records=trace_records,
            event_records=event_records,
            telemetry_by_key=telemetry_by_key,
            failure_records=failure_records,
            route_records=route_records,
        )

    def _recompute_telemetry(
        self,
        *,
        success_routes: frozenset[str],
    ) -> dict[StepInstanceKey, dict[str, Any]]:
        trace_records = self._read_jsonl(self._trace_file)
        event_records = self._read_jsonl(self._events_file)
        checkpoint_payload = self._read_json_object(self._checkpoint_file)
        if trace_records:
            telemetry_by_key, _, _ = self._telemetry_from_trace(
                trace_records,
                checkpoint_payload=checkpoint_payload,
                success_routes=success_routes,
            )
            return telemetry_by_key
        telemetry_by_key, _, _ = self._telemetry_from_events(
            event_records,
            checkpoint_payload=checkpoint_payload,
            success_routes=success_routes,
        )
        return telemetry_by_key

    def _telemetry_from_trace(
        self,
        records: tuple[dict[str, Any], ...],
        *,
        checkpoint_payload: dict[str, Any] | None,
        success_routes: frozenset[str],
    ) -> tuple[dict[StepInstanceKey, dict[str, Any]], tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
        accumulators: dict[StepInstanceKey, _TelemetryAccumulator] = {}
        failure_records: list[dict[str, Any]] = []
        route_records: list[dict[str, Any]] = []
        for record in records:
            event_type = record.get("event_type")
            key = _step_key_from_record(record)
            if event_type == "step_started" and key is not None:
                acc = accumulators.setdefault(key, _new_accumulator(key))
                self._record_step_started(acc, record)
                continue
            if event_type == "step_finished" and key is not None:
                acc = accumulators.setdefault(key, _new_accumulator(key))
                route_record = self._record_step_finished(acc, record, success_routes=success_routes)
                route_records.append(route_record)
                continue
            if event_type in {"provider_attempt_started", "provider_attempt_finished", "provider_attempt_failed"} and key is not None:
                acc = accumulators.setdefault(key, _new_accumulator(key))
                maybe_failure = self._record_provider_attempt(acc, record)
                if maybe_failure is not None:
                    failure_records.append(maybe_failure)
                continue
            if event_type == "artifact_validation_failed" and key is not None:
                acc = accumulators.setdefault(key, _new_accumulator(key))
                failure = self._record_artifact_validation(acc, record)
                failure_records.append(failure)
                continue
            if event_type == "hook_failed" and key is not None:
                acc = accumulators.setdefault(key, _new_accumulator(key))
                failure = {
                    "event_type": "hook_failed",
                    "step_name": key.step_name,
                    "scope": key.scope,
                    "item_id": key.item_id,
                    "phase": record.get("phase"),
                    "hook": record.get("hook_name") or record.get("hook"),
                    "error": record.get("error"),
                    "timestamp": _string_value(record.get("timestamp")),
                }
                acc.errors.append(failure)
                failure_records.append(failure)
        checkpoint_failure = _checkpoint_failure_record(checkpoint_payload)
        if checkpoint_failure is not None:
            failure_records.append(checkpoint_failure)
            checkpoint_key = _step_key_from_failure(checkpoint_failure)
            if checkpoint_key is not None:
                acc = accumulators.setdefault(checkpoint_key, _new_accumulator(checkpoint_key))
                acc.errors.append(checkpoint_failure)
        telemetry_by_key = {
            key: _finalize_telemetry(acc, success_routes=success_routes)
            for key, acc in accumulators.items()
        }
        return telemetry_by_key, tuple(failure_records), tuple(route_records)

    def _telemetry_from_events(
        self,
        records: tuple[dict[str, Any], ...],
        *,
        checkpoint_payload: dict[str, Any] | None,
        success_routes: frozenset[str],
    ) -> tuple[dict[StepInstanceKey, dict[str, Any]], tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
        accumulators: dict[StepInstanceKey, _TelemetryAccumulator] = {}
        failure_records: list[dict[str, Any]] = []
        for record in records:
            event_type = record.get("event_type")
            if event_type == "step_executed":
                step_name = _string_value(record.get("step_name"))
                if step_name is None:
                    continue
                key = StepInstanceKey(step_name=step_name)
                acc = accumulators.setdefault(key, _new_accumulator(key))
                acc.finished_count += 1
                acc.last_status = "completed"
                continue
            key = _step_key_from_record(record)
            if event_type in {"provider_attempt_started", "provider_attempt_finished", "provider_attempt_failed"} and key is not None:
                acc = accumulators.setdefault(key, _new_accumulator(key))
                maybe_failure = self._record_provider_attempt(acc, record)
                if maybe_failure is not None:
                    failure_records.append(maybe_failure)
                continue
            if event_type == "artifact_validation_failed" and key is not None:
                acc = accumulators.setdefault(key, _new_accumulator(key))
                failure = self._record_artifact_validation(acc, record)
                failure_records.append(failure)
                continue
            if event_type == "hook_failed" and key is not None:
                acc = accumulators.setdefault(key, _new_accumulator(key))
                failure = {
                    "event_type": "hook_failed",
                    "step_name": key.step_name,
                    "scope": key.scope,
                    "item_id": key.item_id,
                    "phase": record.get("phase"),
                    "hook": record.get("hook_name") or record.get("hook"),
                    "error": record.get("error"),
                    "timestamp": _string_value(record.get("ts")),
                }
                acc.errors.append(failure)
                failure_records.append(failure)
        checkpoint_failure = _checkpoint_failure_record(checkpoint_payload)
        if checkpoint_failure is not None:
            failure_records.append(checkpoint_failure)
            checkpoint_key = _step_key_from_failure(checkpoint_failure)
            if checkpoint_key is not None:
                acc = accumulators.setdefault(checkpoint_key, _new_accumulator(checkpoint_key))
                acc.errors.append(checkpoint_failure)
        telemetry_by_key = {
            key: _finalize_telemetry(acc, success_routes=success_routes)
            for key, acc in accumulators.items()
        }
        return telemetry_by_key, tuple(failure_records), ()

    def _record_step_started(self, acc: _TelemetryAccumulator, record: Mapping[str, Any]) -> None:
        timestamp = _string_value(record.get("timestamp"))
        acc.started_count += 1
        acc.last_status = "running"
        acc.latest_timestamp = timestamp or acc.latest_timestamp
        acc.first_started_at = acc.first_started_at or timestamp
        acc.last_started_at = timestamp or acc.last_started_at
        step_execution_id = _string_value(record.get("step_execution_id"))
        if step_execution_id is not None and timestamp is not None:
            acc.execution_starts[step_execution_id] = timestamp

    def _record_step_finished(
        self,
        acc: _TelemetryAccumulator,
        record: Mapping[str, Any],
        *,
        success_routes: frozenset[str],
    ) -> dict[str, Any]:
        timestamp = _string_value(record.get("timestamp"))
        final_route = _string_value(record.get("final_route")) or _string_value(_mapping_get(record.get("event"), "tag"))
        candidate_route = _string_value(record.get("candidate_route"))
        runtime_control = _string_value(record.get("runtime_control"))
        pending_input_id = _string_value(record.get("pending_input_id"))
        target_step = _string_value(record.get("target_step"))
        terminal = _string_value(record.get("terminal"))
        provider_attempted = record.get("provider_attempted")
        producer_attempted = record.get("producer_attempted")
        verifier_attempted = record.get("verifier_attempted")
        source_hook = _string_value(record.get("source_hook"))
        source_phase = _string_value(record.get("source_phase"))
        acc.finished_count += 1
        acc.latest_route = final_route
        acc.latest_timestamp = timestamp or acc.latest_timestamp
        acc.first_finished_at = acc.first_finished_at or timestamp
        acc.last_finished_at = timestamp or acc.last_finished_at
        if final_route in success_routes:
            acc.accepted_once = True
        acc.last_status = finalization_to_step_status(
            final_route=final_route,
            runtime_control=runtime_control,
            terminal=terminal,
        )
        usage = _mapping(record.get("provider_usage"))
        if usage:
            for phase, payload in usage.items():
                if isinstance(phase, str) and isinstance(payload, Mapping):
                    _merge_token_payload(acc.token_usage_from_step_finished, phase, payload)
        step_execution_id = _string_value(record.get("step_execution_id"))
        started_at = acc.execution_starts.get(step_execution_id) if step_execution_id is not None else None
        if started_at is not None and timestamp is not None:
            duration = _duration_seconds(started_at, timestamp)
            if duration is not None:
                acc.total_duration_seconds += duration
                acc.latest_duration_seconds = duration
        route_record = {
            "event_type": "step_finished",
            "step_name": acc.step_name,
            "scope": acc.scope,
            "item_id": acc.item_id,
            "candidate_route": candidate_route,
            "final_route": final_route,
            "runtime_control": runtime_control,
            "pending_input_id": pending_input_id,
            "target_step": target_step,
            "terminal": terminal,
            "provider_attributable": bool(record.get("provider_attributable")),
            "provider_attempted": provider_attempted if isinstance(provider_attempted, bool) else None,
            "producer_attempted": producer_attempted if isinstance(producer_attempted, bool) else None,
            "verifier_attempted": verifier_attempted if isinstance(verifier_attempted, bool) else None,
            "source_hook": source_hook,
            "source_phase": source_phase,
            "visit": _int_value(record.get("visit")),
            "step_execution_id": step_execution_id,
            "timestamp": timestamp,
            "hook_route_redirects": tuple(record.get("hook_route_redirects") or ()),
        }
        acc.routes.append(route_record)
        return route_record

    def _record_provider_attempt(
        self,
        acc: _TelemetryAccumulator,
        record: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        turn_kind = _string_value(record.get("turn_kind")) or "unknown"
        attempt = _int_value(record.get("attempt")) or 0
        step_execution_id = _string_value(record.get("step_execution_id"))
        acc.attempt_keys[turn_kind].add((step_execution_id, attempt))
        event_type = _string_value(record.get("event_type"))
        if event_type == "provider_attempt_finished":
            usage = _mapping(record.get("token_usage"))
            if usage:
                usage_phase = "repair" if turn_kind == "outcome_repair" else turn_kind
                _merge_token_payload(acc.token_usage_from_attempts, usage_phase, usage)
            return None
        if event_type != "provider_attempt_failed":
            return None
        failure_context = _mapping(record.get("failure_context")) or {}
        failure = {
            "event_type": "provider_attempt_failed",
            "step_name": acc.step_name,
            "scope": acc.scope,
            "item_id": acc.item_id,
            "turn_kind": turn_kind,
            "attempt": attempt,
            "step_execution_id": step_execution_id,
            "failure_context": failure_context,
            "timestamp": _string_value(record.get("timestamp")) or _string_value(record.get("ts")),
        }
        acc.errors.append(failure)
        acc.last_status = "failed"
        return failure

    def _record_artifact_validation(self, acc: _TelemetryAccumulator, record: Mapping[str, Any]) -> dict[str, Any]:
        failure = {
            "event_type": "artifact_validation_failed",
            "step_name": acc.step_name,
            "scope": acc.scope,
            "item_id": acc.item_id,
            "route": _string_value(record.get("route")),
            "artifact_name": _string_value(record.get("artifact_name")),
            "qualified_name": _string_value(record.get("qualified_name")),
            "path": _string_value(record.get("path")),
            "validation_kind": _string_value(record.get("validation_kind")),
            "errors": tuple(_string_list(record.get("errors"))),
            "provider_attributable": bool(record.get("provider_attributable")),
            "timestamp": _string_value(record.get("timestamp")) or _string_value(record.get("ts")),
        }
        acc.artifact_validation_failures.append(failure)
        acc.errors.append(failure)
        acc.last_status = "failed"
        return failure

    def _read_jsonl(self, path: Path) -> tuple[dict[str, Any], ...]:
        signature = _path_signature(path)
        cached = self._jsonl_cache.get(path)
        if cached is not None and cached[0] == signature:
            return cached[1]
        if not path.exists():
            records: tuple[dict[str, Any], ...] = ()
        else:
            payloads: list[dict[str, Any]] = []
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                if not raw_line.strip():
                    continue
                try:
                    value = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    if path == self._trace_file:
                        validate_persisted_schema(
                            value,
                            expected=RUNTIME_TRACE_SCHEMA,
                            artifact_name=str(path),
                            legacy_migrator=lambda payload: migrate_schemaless_payload(payload, expected=RUNTIME_TRACE_SCHEMA),
                        )
                    elif path == self._events_file:
                        validate_persisted_schema(
                            value,
                            expected=RUNTIME_EVENT_SCHEMA,
                            artifact_name=str(path),
                            legacy_migrator=lambda payload: migrate_schemaless_payload(payload, expected=RUNTIME_EVENT_SCHEMA),
                        )
                    payloads.append(value)
            records = tuple(payloads)
        self._jsonl_cache[path] = (signature, records)
        return records

    def _read_json_object(self, path: Path) -> dict[str, Any] | None:
        signature = _path_signature(path)
        cached = self._object_cache.get(path)
        if cached is not None and cached[0] == signature:
            return cached[1]
        if not path.exists():
            payload = None
        else:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                value = None
            payload = value if isinstance(value, dict) else None
            if payload is not None and path == self._checkpoint_file:
                validate_persisted_schema(
                    payload,
                    expected=CHECKPOINT_SCHEMA,
                    artifact_name=str(path),
                    legacy_migrator=lambda value: migrate_schemaless_payload(value, expected=CHECKPOINT_SCHEMA),
                )
        self._object_cache[path] = (signature, payload)
        return payload


def _new_accumulator(key: StepInstanceKey) -> _TelemetryAccumulator:
    return _TelemetryAccumulator(
        step_name=key.step_name,
        scope=key.scope,
        item_id=key.item_id,
    )


def _finalize_telemetry(
    acc: _TelemetryAccumulator,
    *,
    success_routes: frozenset[str],
) -> dict[str, Any]:
    do_attempts = sum(
        len(values)
        for phase, values in acc.attempt_keys.items()
        if phase in {"producer", "llm", "operation", "step"}
    )
    verify_attempts = len(acc.attempt_keys.get("verifier", set()))
    retry_count = max(do_attempts, verify_attempts, 1 if acc.started_count or acc.finished_count else 0) - 1
    if retry_count < 0:
        retry_count = 0
    token_usage = _select_token_usage(acc)
    status = acc.last_status
    if acc.finished_count and status in {"awaiting_input", "failed", "completed"}:
        pass
    elif acc.finished_count and acc.latest_route in success_routes:
        status = "completed"
    elif acc.finished_count and acc.latest_route is not None:
        status = route_to_step_status(acc.latest_route, completed=True)
    elif acc.started_count:
        status = "running"
    elif acc.errors:
        status = "failed"
    return {
        "step_name": acc.step_name,
        "scope": acc.scope,
        "item_id": acc.item_id,
        "status": status,
        "completed": acc.finished_count > 0,
        "finished_once": acc.finished_count > 0,
        "accepted_once": acc.accepted_once,
        "retry_count": retry_count,
        "timestamps": {
            "first_started_at": acc.first_started_at,
            "last_started_at": acc.last_started_at,
            "first_finished_at": acc.first_finished_at,
            "last_finished_at": acc.last_finished_at,
        },
        "durations": {
            "latest_seconds": acc.latest_duration_seconds,
            "total_seconds": acc.total_duration_seconds,
        },
        "errors": list(acc.errors),
        "artifact_validation_failures": list(acc.artifact_validation_failures),
        "token_usage": _prune_token_usage(token_usage),
        "do_attempts": do_attempts,
        "verify_attempts": verify_attempts,
    }


def _select_token_usage(acc: _TelemetryAccumulator) -> dict[str, dict[str, int]]:
    combined = _copy_token_usage(acc.token_usage_from_attempts)
    for phase, payload in acc.token_usage_from_step_finished.items():
        if phase not in combined:
            combined[phase] = dict(payload)
    return combined


def _merge_telemetry_payloads(
    payloads: list[dict[str, Any]],
    *,
    step_name: str,
    scope: str | None,
    item_id: str | None,
) -> dict[str, Any]:
    merged = _empty_telemetry(step_name=step_name, scope=scope, item_id=item_id)
    best_status = merged["status"]
    best_priority = _STATUS_PRIORITY.get(best_status, 0)
    for payload in payloads:
        merged["completed"] = bool(merged["completed"] or payload.get("completed"))
        merged["finished_once"] = bool(merged["finished_once"] or payload.get("finished_once"))
        merged["accepted_once"] = bool(merged["accepted_once"] or payload.get("accepted_once"))
        merged["retry_count"] += int(payload.get("retry_count") or 0)
        merged["do_attempts"] += int(payload.get("do_attempts") or 0)
        merged["verify_attempts"] += int(payload.get("verify_attempts") or 0)
        _merge_timestamp_bounds(merged["timestamps"], payload.get("timestamps"))
        _merge_duration_totals(merged["durations"], payload.get("durations"))
        merged["errors"].extend(list(payload.get("errors") or ()))
        merged["artifact_validation_failures"].extend(list(payload.get("artifact_validation_failures") or ()))
        _merge_token_usage(merged["token_usage"], payload.get("token_usage"))
        candidate_status = str(payload.get("status") or "pending")
        candidate_priority = _STATUS_PRIORITY.get(candidate_status, 0)
        if candidate_priority >= best_priority:
            best_status = candidate_status
            best_priority = candidate_priority
    merged["status"] = best_status
    return merged


def _empty_telemetry(*, step_name: str, scope: str | None, item_id: str | None) -> dict[str, Any]:
    return {
        "step_name": step_name,
        "scope": scope,
        "item_id": item_id,
        "status": "pending",
        "completed": False,
        "finished_once": False,
        "accepted_once": False,
        "retry_count": 0,
        "timestamps": {
            "first_started_at": None,
            "last_started_at": None,
            "first_finished_at": None,
            "last_finished_at": None,
        },
        "durations": {
            "latest_seconds": None,
            "total_seconds": 0.0,
        },
        "errors": [],
        "artifact_validation_failures": [],
        "token_usage": {},
        "do_attempts": 0,
        "verify_attempts": 0,
    }


def _step_key_from_record(record: Mapping[str, Any]) -> StepInstanceKey | None:
    step_name = _string_value(record.get("step_name"))
    if step_name is None:
        return None
    return StepInstanceKey(
        step_name=step_name,
        scope=_string_value(record.get("scope")),
        item_id=_string_value(record.get("item_id")),
    )


def _step_key_from_failure(record: Mapping[str, Any]) -> StepInstanceKey | None:
    step_name = _string_value(record.get("step_name")) or _string_value(record.get("step"))
    if step_name is None:
        return None
    return StepInstanceKey(
        step_name=step_name,
        scope=_string_value(record.get("scope")),
        item_id=_string_value(record.get("item_id")),
    )


def _route_matches(
    record: Mapping[str, Any],
    *,
    step: str | None,
    scope: str | None,
    item_id: str | None,
) -> bool:
    if step is not None and record.get("step_name") != step:
        return False
    if scope is not None and record.get("scope") != scope:
        return False
    if item_id is not None and record.get("item_id") != item_id:
        return False
    return True


def _failure_matches(
    record: Mapping[str, Any],
    *,
    step: str | None,
    scope: str | None,
    item_id: str | None,
) -> bool:
    record_step = record.get("step_name") or record.get("step")
    if step is not None and record_step != step:
        return False
    if scope is not None and record.get("scope") != scope:
        return False
    if item_id is not None and record.get("item_id") != item_id:
        return False
    return True


def _step_key_matches(
    key: StepInstanceKey,
    *,
    step: str | None,
    scope: str | None,
    item_id: str | None,
) -> bool:
    if step is not None and key.step_name != step:
        return False
    if scope is not None and key.scope != scope:
        return False
    if item_id is not None and key.item_id != item_id:
        return False
    return True


def _checkpoint_failure_record(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    failure_context = payload.get("failure_context")
    if not isinstance(failure_context, dict) or not failure_context:
        return None
    record = dict(failure_context)
    record.setdefault("event_type", "checkpoint_failure")
    return record


def _duration_seconds(started_at: str, finished_at: str) -> float | None:
    try:
        started = datetime.fromisoformat(started_at)
        finished = datetime.fromisoformat(finished_at)
    except ValueError:
        return None
    return max((finished - started).total_seconds(), 0.0)


def _merge_timestamp_bounds(target: dict[str, Any], payload: Any) -> None:
    if not isinstance(payload, Mapping):
        return
    for earlier_key, later_key in (
        ("first_started_at", "first_started_at"),
        ("last_started_at", "last_started_at"),
        ("first_finished_at", "first_finished_at"),
        ("last_finished_at", "last_finished_at"),
    ):
        candidate = _string_value(payload.get(earlier_key))
        if candidate is None:
            continue
        current = _string_value(target.get(later_key))
        if current is None:
            target[later_key] = candidate
            continue
        if "first_" in earlier_key:
            target[later_key] = min(current, candidate)
        else:
            target[later_key] = max(current, candidate)


def _merge_duration_totals(target: dict[str, Any], payload: Any) -> None:
    if not isinstance(payload, Mapping):
        return
    target["total_seconds"] = float(target.get("total_seconds") or 0.0) + float(payload.get("total_seconds") or 0.0)
    latest = payload.get("latest_seconds")
    if latest is not None:
        target["latest_seconds"] = latest


def _empty_token_usage() -> dict[str, dict[str, int]]:
    return {}


def _copy_token_usage(value: Any) -> dict[str, dict[str, int]]:
    if not isinstance(value, Mapping):
        return {}
    copied: dict[str, dict[str, int]] = {}
    for phase, payload in value.items():
        if isinstance(phase, str) and isinstance(payload, Mapping):
            copied[phase] = {
                key: int(amount)
                for key, amount in payload.items()
                if isinstance(key, str) and isinstance(amount, int)
            }
    return copied


def _merge_token_usage(target: dict[str, dict[str, int]], payload: Any) -> None:
    if not isinstance(payload, Mapping):
        return
    for phase, usage in payload.items():
        if not isinstance(phase, str) or not isinstance(usage, Mapping):
            continue
        _merge_token_payload(target, phase, usage)


def _merge_token_payload(target: dict[str, dict[str, int]], phase: str, payload: Mapping[str, Any]) -> None:
    phase_bucket = target.setdefault(phase, {})
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, int):
            continue
        phase_bucket[key] = phase_bucket.get(key, 0) + value


def _prune_token_usage(payload: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    return {phase: dict(values) for phase, values in payload.items() if values}


def _path_signature(path: Path) -> tuple[bool, int, int]:
    if not path.exists():
        return (False, 0, 0)
    stat = path.stat()
    return (True, stat.st_size, stat.st_mtime_ns)


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_value(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _mapping_get(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str)]


__all__ = ["DEFAULT_ACCEPTED_ROUTE_TAGS", "HistoryReader", "StepInstanceKey"]
