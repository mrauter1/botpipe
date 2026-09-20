"""Optimizer over durable journal observations and Python source manifests."""

from __future__ import annotations

import ast
import inspect
import json
import math
import textwrap
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from statistics import mean
from typing import Any, get_type_hints

from botpipe.codec import decode as decode_durable

_FAILURES = frozenset({"failed", "interrupted", "budget_exceeded", "cancelled"})


@dataclass(frozen=True, slots=True)
class SourceSite:
    site_id: str
    name: str
    kind: str
    line: int


@dataclass(frozen=True, slots=True)
class SourceManifest:
    workflow_name: str
    module: str
    qualname: str
    signature: str
    source_path: str | None
    source_sha256: str
    workflow_version: str | None
    topology_dynamic: bool
    sites: tuple[SourceSite, ...] = ()
    branch_lines: tuple[int, ...] = ()
    input_schema: dict[str, Any] | None = None
    return_annotation: str | None = None


@dataclass(frozen=True, slots=True)
class OperationObservation:
    operation_id: str
    run_id: str
    scope: str
    ordinal: int
    kind: str
    name: str
    status: str
    outcome: str | None
    attempts: int
    duration_ms: float | None
    usage: dict[str, float]
    inputs: dict[str, Any]
    result: Any
    error: str | None
    artifacts: tuple[str, ...] = ()
    dispatches: tuple[ProviderDispatchObservation, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderDispatchObservation:
    dispatch_id: str
    attempt: int | None
    generation: int | None
    outcome: str
    usage_availability: str
    usage: dict[str, float]
    elapsed_seconds: float | None


@dataclass(frozen=True, slots=True)
class RunObservation:
    run_id: str
    run_ref: str
    task_id: str | None
    workflow_name: str | None
    workflow_version: str | None
    workflow_identity: str | None
    surface_id: str | None
    orchestration_id: str | None
    provenance_state: str
    status: str
    operations: tuple[OperationObservation, ...]
    artifacts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OperationMetrics:
    name: str
    kind: str
    observation_count: int
    success_count: int
    failure_count: int
    retry_count: int
    mean_duration_ms: float | None
    total_tokens: int
    outcome_counts: dict[str, int]
    evidence_operation_ids: tuple[str, ...]

    @property
    def failure_rate(self) -> float:
        return (
            self.failure_count / self.observation_count
            if self.observation_count
            else 0.0
        )


@dataclass(frozen=True, slots=True)
class OptimizationCandidate:
    candidate_id: str
    target_name: str
    target_kind: str
    category: str
    score: float
    rationale: str
    proposed_change: str
    evidence_operation_ids: tuple[str, ...]
    requires_ablation: bool = False


@dataclass(frozen=True, slots=True)
class OptimizationReport:
    workflow_name: str
    observed_run_ids: tuple[str, ...]
    observed_operation_count: int
    candidates: tuple[OptimizationCandidate, ...]
    metrics: tuple[OperationMetrics, ...]
    source_manifest: SourceManifest | None = None
    unseen_declared_paths: tuple[str, ...] = ()
    observation_absent: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def capture_source_manifest(workflow: Callable[..., Any]) -> SourceManifest:
    """Describe a callable while declaring that its Python topology is dynamic."""
    target = inspect.unwrap(workflow)
    name = str(
        getattr(workflow, "workflow_name", None)
        or getattr(workflow, "name", None)
        or target.__name__
    )
    try:
        source = inspect.getsource(target)
        source_path = inspect.getsourcefile(target)
        first_line = inspect.getsourcelines(target)[1]
    except (OSError, TypeError):
        source, source_path, first_line = "", None, 1
    sites: list[SourceSite] = []
    branches: list[int] = []
    if source:
        tree = ast.parse(textwrap.dedent(source))
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.Match, ast.For, ast.While, ast.Try)):
                branches.append(first_line + node.lineno - 1)
            call = node.value if isinstance(node, ast.Await) else node
            if not isinstance(call, ast.Call):
                continue
            kind, call_name = _source_call_identity(call)
            if kind is None:
                continue
            line = first_line + call.lineno - 1
            sites.append(
                SourceSite(
                    f"{target.__qualname__}:{line}:{kind}:{call_name}",
                    call_name,
                    kind,
                    line,
                )
            )
    input_schema = None
    try:
        signature = inspect.signature(target)
        parameters = list(signature.parameters.values())
        try:
            hints = get_type_hints(target)
        except (NameError, TypeError):
            hints = {}
        annotation = (
            hints.get(parameters[0].name, parameters[0].annotation)
            if parameters
            else None
        )
        if hasattr(annotation, "model_json_schema"):
            input_schema = annotation.model_json_schema()
        return_annotation = inspect.formatannotation(
            hints.get("return", signature.return_annotation)
        )
    except (TypeError, ValueError):
        return_annotation = None
    return SourceManifest(
        workflow_name=name,
        module=target.__module__,
        qualname=target.__qualname__,
        signature=str(inspect.signature(target)),
        source_path=None if source_path is None else str(Path(source_path).resolve()),
        source_sha256=sha256(source.encode()).hexdigest(),
        workflow_version=getattr(workflow, "fingerprint", None),
        topology_dynamic=True,
        sites=tuple(sorted(sites, key=lambda item: (item.line, item.site_id))),
        branch_lines=tuple(sorted(set(branches))),
        input_schema=input_schema,
        return_annotation=return_annotation,
    )


def load_run_observation(payload: Mapping[str, Any]) -> RunObservation:
    """Normalize ``Botpipe.inspect`` output into optimizer observations."""
    run = _mapping(payload.get("run"))
    run_id = _text(run.get("run_id") or payload.get("run_id"), "run_id")
    workflow_name = run.get("workflow_name") or run.get("workflow") or run.get("name")
    provenance_start = _mapping(run.get("provenance_start"))
    provenance_end = _mapping(run.get("provenance_end"))
    start_identity = provenance_start.get("workflow_identity")
    end_identity = provenance_end.get("workflow_identity")
    start_surface = provenance_start.get("surface_id")
    end_surface = provenance_end.get("surface_id")
    start_orchestration = provenance_start.get("orchestration_id")
    end_orchestration = provenance_end.get("orchestration_id")
    if (
        provenance_start.get("verified") is True
        and provenance_end.get("verified") is True
        and start_identity == end_identity
        and start_surface == end_surface
        and start_orchestration == end_orchestration
        and start_identity
        and start_surface
        and start_orchestration
    ):
        provenance_state = "known"
        workflow_identity_value = str(start_identity)
        surface_id = str(start_surface)
        orchestration_id = str(start_orchestration)
    elif any(
        value
        for value in (
            start_identity,
            end_identity,
            start_surface,
            end_surface,
            start_orchestration,
            end_orchestration,
        )
    ):
        provenance_state = "mixed"
        workflow_identity_value = None
        surface_id = None
        orchestration_id = None
    else:
        provenance_state = "unknown"
        workflow_identity_value = None
        surface_id = None
        orchestration_id = None
    raw_operations = payload.get("operations", ())
    if not isinstance(raw_operations, Sequence) or isinstance(
        raw_operations, (str, bytes)
    ):
        raise TypeError("inspection operations must be a sequence")
    raw_dispatches: Mapping[str, Any] = {}
    try:
        from botpipe.dispatches import dispatch_records

        events = payload.get("events", ())
        if isinstance(events, Sequence) and not isinstance(events, (str, bytes)):
            raw_dispatches = dispatch_records(events)
    except (KeyError, TypeError, ValueError):
        raw_dispatches = {}
    operations = tuple(
        _load_operation(
            item,
            run_id,
            raw_dispatches.get(
                str(_mapping(item).get("operation_id") or _mapping(item).get("id")), ()
            ),
        )
        for item in raw_operations
    )
    ids = [item.operation_id for item in operations]
    if len(ids) != len(set(ids)):
        raise ValueError("inspection contains duplicate operation ids")
    return RunObservation(
        run_id=run_id,
        run_ref=(f"{run.get('task_id')}/{run_id}" if run.get("task_id") else run_id),
        task_id=None if run.get("task_id") is None else str(run.get("task_id")),
        workflow_name=None if workflow_name is None else str(workflow_name),
        workflow_version=(
            None if run.get("version") is None else str(run.get("version"))
        ),
        workflow_identity=workflow_identity_value,
        surface_id=surface_id,
        orchestration_id=orchestration_id,
        provenance_state=provenance_state,
        status=str(run.get("status") or "unknown").lower(),
        operations=operations,
        artifacts=_artifact_names(payload.get("artifacts", ())),
    )


def build_operation_metrics(
    runs: Iterable[RunObservation],
) -> tuple[OperationMetrics, ...]:
    grouped: dict[tuple[str, str], list[OperationObservation]] = defaultdict(list)
    for run in runs:
        for operation in run.operations:
            grouped[(operation.name, operation.kind)].append(operation)
    metrics: list[OperationMetrics] = []
    for (name, kind), observations in grouped.items():
        durations = [
            item.duration_ms for item in observations if item.duration_ms is not None
        ]
        outcomes = Counter(item.outcome for item in observations if item.outcome)
        metrics.append(
            OperationMetrics(
                name=name,
                kind=kind,
                observation_count=len(observations),
                success_count=sum(item.status == "completed" for item in observations),
                failure_count=sum(item.status in _FAILURES for item in observations),
                retry_count=sum(max(0, item.attempts - 1) for item in observations),
                mean_duration_ms=None if not durations else round(mean(durations), 3),
                total_tokens=sum(_token_total(item.usage) for item in observations),
                outcome_counts=dict(sorted(outcomes.items())),
                evidence_operation_ids=tuple(
                    item.operation_id for item in observations
                ),
            )
        )
    return tuple(sorted(metrics, key=lambda item: (item.name, item.kind)))


def rank_optimization_candidates(
    metrics: Sequence[OperationMetrics], *, limit: int = 10
) -> tuple[OptimizationCandidate, ...]:
    """Rank observed sites; unobserved source declarations never receive scores."""
    if limit < 1:
        raise ValueError("limit must be positive")
    if not metrics:
        return ()
    max_tokens = max((item.total_tokens for item in metrics), default=0) or 1
    max_duration = (
        max((item.mean_duration_ms or 0.0 for item in metrics), default=0.0) or 1.0
    )
    candidates: list[OptimizationCandidate] = []
    for metric in metrics:
        score = round(
            metric.failure_rate * 60
            + min(metric.retry_count, 5) * 4
            + metric.total_tokens / max_tokens * 20
            + (metric.mean_duration_ms or 0) / max_duration * 15,
            3,
        )
        if metric.failure_count or metric.retry_count:
            category = "reliability"
            change = "Tighten the typed result contract and validation feedback; test the observed failure outcomes."
        elif metric.total_tokens:
            category = "token_cost"
            change = "Reduce repeated context and prompt surface, then compare typed-output quality and token use."
        elif metric.mean_duration_ms is not None:
            category = "latency"
            change = "Measure the slow work and evaluate a smaller or independently cached operation boundary."
        else:
            category = "evidence_gap"
            change = "Capture outcome, timing, and usage evidence before proposing an implementation change."
        digest = sha256(f"{metric.kind}:{metric.name}:{category}".encode()).hexdigest()[
            :12
        ]
        candidates.append(
            OptimizationCandidate(
                candidate_id=f"opt-{digest}",
                target_name=metric.name,
                target_kind=metric.kind,
                category=category,
                score=score,
                rationale=(
                    f"Observed {metric.observation_count} operation(s): {metric.failure_count} failures, "
                    f"{metric.retry_count} retries, {metric.total_tokens} tokens, "
                    f"mean duration {metric.mean_duration_ms!r} ms."
                ),
                proposed_change=change,
                evidence_operation_ids=metric.evidence_operation_ids,
                requires_ablation=category in {"token_cost", "latency"},
            )
        )
    candidates.sort(key=lambda item: (-item.score, item.target_name, item.target_kind))
    return tuple(candidates[:limit])


def optimize_observations(
    workflow_name: str,
    inspections: Iterable[Mapping[str, Any] | RunObservation],
    *,
    source_manifest: SourceManifest | None = None,
    limit: int = 10,
) -> OptimizationReport:
    runs = tuple(
        item if isinstance(item, RunObservation) else load_run_observation(item)
        for item in inspections
    )
    mismatched = sorted(
        {
            run.workflow_name
            for run in runs
            if run.workflow_name and run.workflow_name != workflow_name
        }
    )
    if mismatched:
        raise ValueError(
            f"observations belong to other workflows: {', '.join(mismatched)}"
        )
    metrics = build_operation_metrics(runs)
    observed_names = {metric.name for metric in metrics}
    if source_manifest is not None and source_manifest.workflow_name != workflow_name:
        raise ValueError(
            "source manifest workflow_name does not match report workflow_name"
        )
    unseen = (
        ()
        if source_manifest is None
        else tuple(
            site.site_id
            for site in source_manifest.sites
            if site.name not in observed_names
        )
    )
    report = OptimizationReport(
        workflow_name=workflow_name,
        observed_run_ids=tuple(run.run_id for run in runs),
        observed_operation_count=sum(len(run.operations) for run in runs),
        candidates=rank_optimization_candidates(metrics, limit=limit),
        metrics=metrics,
        source_manifest=source_manifest,
        unseen_declared_paths=unseen,
        observation_absent=not metrics,
    )
    validate_optimization_report(report, runs=runs)
    return report


def validate_optimization_candidate(
    candidate: OptimizationCandidate,
    *,
    observed_operations: Iterable[OperationObservation],
) -> None:
    observations = tuple(observed_operations)
    by_id = {item.operation_id: item for item in observations}
    if not candidate.evidence_operation_ids:
        raise ValueError(
            f"candidate {candidate.candidate_id} has no observed operation evidence"
        )
    missing = sorted(set(candidate.evidence_operation_ids) - set(by_id))
    if missing:
        raise ValueError(
            f"candidate {candidate.candidate_id} cites unknown operations: {', '.join(missing)}"
        )
    if any(
        by_id[item].name != candidate.target_name
        for item in candidate.evidence_operation_ids
    ):
        raise ValueError(
            f"candidate {candidate.candidate_id} mixes evidence from another target"
        )
    if not math.isfinite(candidate.score) or candidate.score < 0:
        raise ValueError(f"candidate {candidate.candidate_id} has an invalid score")


def validate_optimization_report(
    report: OptimizationReport, *, runs: Iterable[RunObservation]
) -> None:
    observations = tuple(operation for run in runs for operation in run.operations)
    if report.observation_absent != (len(observations) == 0):
        raise ValueError(
            "observation_absent must reflect the supplied journal evidence"
        )
    ids = [item.candidate_id for item in report.candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("optimization candidate ids must be unique")
    for candidate in report.candidates:
        validate_optimization_candidate(candidate, observed_operations=observations)


def write_optimization_report(report: OptimizationReport, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(target)
    return target


def _load_operation(
    raw: Any, run_id: str, event_dispatches: Any = ()
) -> OperationObservation:
    item = _mapping(raw)
    operation_id = _text(item.get("operation_id") or item.get("id"), "operation id")
    result = _decode(item.get("result"))
    result_map = result if isinstance(result, Mapping) else {}
    value = result_map.get("value", getattr(result, "value", result))
    result_usage = result_map.get("usage", getattr(result, "usage", {}))
    result_artifacts = result_map.get("artifacts", getattr(result, "artifacts", ()))
    decoded_inputs = _decode(item.get("inputs"))
    inputs = dict(_mapping(decoded_inputs))
    attempts = item.get("attempts") or item.get("attempt")
    if attempts is None and isinstance(inputs.get("attempt"), int):
        attempts = inputs["attempt"] + 1
    attempts = attempts or 1
    try:
        attempts = max(1, int(attempts))
    except (TypeError, ValueError):
        attempts = 1
    supplied_dispatches = item.get("dispatches", event_dispatches)
    if not isinstance(supplied_dispatches, Sequence) or isinstance(
        supplied_dispatches, (str, bytes)
    ):
        supplied_dispatches = ()
    return OperationObservation(
        operation_id=operation_id,
        run_id=str(item.get("run_id") or run_id),
        scope=str(item.get("scope") or "root"),
        ordinal=int(item.get("ordinal") or 0),
        kind=str(item.get("kind") or "unknown"),
        name=str(item.get("name") or item.get("site") or item.get("kind") or "unknown"),
        status=str(item.get("status") or "unknown").lower(),
        outcome=_extract_outcome(value),
        attempts=attempts,
        duration_ms=_duration_ms(item),
        usage=_number_mapping(item.get("usage") or result_usage),
        inputs=inputs,
        result=value,
        error=None if item.get("error") is None else str(item.get("error")),
        artifacts=_artifact_names(result_artifacts or item.get("artifacts") or ()),
        dispatches=tuple(_load_dispatch(value) for value in supplied_dispatches),
    )


def _load_dispatch(raw: Any) -> ProviderDispatchObservation:
    item = _mapping(raw)
    elapsed = item.get("elapsed_seconds")
    if (
        not isinstance(elapsed, (int, float))
        or isinstance(elapsed, bool)
        or not math.isfinite(elapsed)
        or elapsed < 0
    ):
        elapsed = None
    return ProviderDispatchObservation(
        dispatch_id=_text(item.get("dispatch_id"), "dispatch id"),
        attempt=_optional_integer(item.get("attempt")),
        generation=_optional_integer(item.get("generation")),
        outcome=str(item.get("outcome") or "unknown").lower(),
        usage_availability=str(item.get("usage_availability") or "unknown").lower(),
        usage=_number_mapping(item.get("usage") or item),
        elapsed_seconds=None if elapsed is None else float(elapsed),
    )


def _optional_integer(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_call_identity(call: ast.Call) -> tuple[str | None, str]:
    func = call.func
    if isinstance(func, ast.Name) and func.id in {"ask", "parallel"}:
        return func.id, _keyword_string(call, "name") or func.id
    if isinstance(func, ast.Attribute) and func.attr in {
        "run",
        "arun",
        "operation",
        "scope_call",
    }:
        owner = func.value.id if isinstance(func.value, ast.Name) else func.attr
        return ("provider" if func.attr in {"run", "arun"} else func.attr), (
            _keyword_string(call, "name") or owner
        )
    return None, ""


def _decode(value: Any) -> Any:
    """Decode current durable journal values while accepting plain inspection fixtures."""
    try:
        return decode_durable(value)
    except (AttributeError, ImportError, TypeError, ValueError):
        return value


def _keyword_string(call: ast.Call, name: str) -> str | None:
    for keyword in call.keywords:
        if (
            keyword.arg == name
            and isinstance(keyword.value, ast.Constant)
            and isinstance(keyword.value.value, str)
        ):
            return keyword.value.value
    return None


def _extract_outcome(value: Any) -> str | None:
    for key in ("outcome", "decision", "route", "tag", "status"):
        candidate = (
            value.get(key) if isinstance(value, Mapping) else getattr(value, key, None)
        )
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _duration_ms(item: Mapping[str, Any]) -> float | None:
    explicit = item.get("duration_ms")
    if isinstance(explicit, (int, float)) and not isinstance(explicit, bool):
        value = float(explicit)
        return value if math.isfinite(value) and value >= 0 else None
    started, finished = (
        _timestamp(item.get("started_at")),
        _timestamp(item.get("finished_at")),
    )
    if started is None or finished is None:
        return None
    value = (finished - started).total_seconds() * 1000
    return value if math.isfinite(value) and value >= 0 else None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _token_total(usage: Mapping[str, float]) -> int:
    if "total_tokens" in usage:
        return max(0, int(usage["total_tokens"]))
    return max(
        0, int(sum(value for key, value in usage.items() if key.endswith("tokens")))
    )


def _number_mapping(value: Any) -> dict[str, float]:
    return (
        {
            str(key): float(number)
            for key, number in value.items()
            if isinstance(number, (int, float)) and not isinstance(number, bool)
        }
        if isinstance(value, Mapping)
        else {}
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"inspection must define a non-empty {label}")
    return value.strip()


def _artifact_names(value: Any) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        return tuple(sorted(str(key) for key in value))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(
            sorted(
                str(item.get("name") or item.get("path") or "artifact")
                if isinstance(item, Mapping)
                else str(
                    getattr(item, "name", None) or getattr(item, "path", None) or item
                )
                for item in value
            )
        )
    return ()
