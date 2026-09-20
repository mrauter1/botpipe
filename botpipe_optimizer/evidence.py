"""Bounded, content-addressed evidence snapshots over durable journal operations."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .optimization import RunObservation, SourceManifest, load_run_observation

type Objective = Literal["reliability", "token_usage", "latency"]
type Availability = Literal["known_total", "partial", "unknown", "not_attempted"]


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class SelectionPolicy(EvidenceRecord):
    explicit_run_refs: bool
    route_tags: tuple[str, ...] = ()
    selected_run_count: int = Field(ge=0)
    admitted_run_count: int = Field(ge=0)
    focused_observation_count: int = Field(ge=0)
    captured_observation_count: int = Field(ge=0)


class EvidenceIssue(EvidenceRecord):
    run_ref: str | None = None
    observation_id: str | None = None
    dimension: str
    reason: str


class ExcludedRun(EvidenceRecord):
    run_ref: str
    reason: str
    bytes: int = Field(ge=0)


class Observation(EvidenceRecord):
    observation_id: str = Field(pattern=r"^observation_[0-9a-f]{64}$")
    operation_id: str
    run_ref: str
    group_id: str
    step_id: str
    step_kind: str
    scope: str
    status: str
    outcome: str | None = None
    focused: bool
    direct_failure: bool
    rework_rejection: bool
    attempted_dispatch_count: int = Field(ge=0)
    usage_availability: Availability
    known_total_tokens: int | None = Field(default=None, ge=0)
    elapsed_available: bool
    elapsed_seconds: float | None = Field(default=None, ge=0)


class RunEvidence(EvidenceRecord):
    run_ref: str
    task_id: str | None = None
    run_id: str
    status: str
    workflow_identity: str
    workflow_surface_id: str | None = None
    orchestration_id: str | None = None
    provenance_state: Literal["known", "unknown", "mixed"]
    structural_group_id: str
    observation_ids: tuple[str, ...]


class EvidenceGroup(EvidenceRecord):
    group_id: str
    workflow_identity: str
    workflow_surface_id: str | None = None
    orchestration_id: str | None = None
    run_refs: tuple[str, ...]
    current_match: bool


class StepMetric(EvidenceRecord):
    metric_id: str
    group_id: str
    step_id: str
    step_kind: str
    observation_count: int = Field(ge=0)
    distinct_run_count: int = Field(ge=0)
    direct_failure_count: int = Field(ge=0)
    direct_failure_run_count: int = Field(ge=0)
    rework_rejection_count: int = Field(ge=0)
    rework_run_count: int = Field(ge=0)
    attempted_dispatch_count: int = Field(ge=0)
    complete_usage: bool
    known_total_tokens: int | None = Field(default=None, ge=0)
    complete_elapsed: bool
    total_elapsed_seconds: float | None = Field(default=None, ge=0)


class StepRanking(EvidenceRecord):
    rank: int = Field(ge=1)
    metric_id: str
    group_id: str
    step_id: str
    objective: Objective
    direct_failure_run_count: int = Field(ge=0)
    rework_run_count: int = Field(ge=0)
    distinct_run_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    known_total_tokens: int | None = Field(default=None, ge=0)
    total_elapsed_seconds: float | None = Field(default=None, ge=0)


class EvidenceBudget(EvidenceRecord):
    max_bytes: int = Field(gt=0)
    admitted_bytes: int = Field(ge=0)
    omitted_bytes: int = Field(ge=0)
    budget_limited: bool


class EvidenceSnapshot(EvidenceRecord):
    schema_version: Literal["botpipe.workflow_optimization.evidence/v2"] = Field(
        default="botpipe.workflow_optimization.evidence/v2",
        alias="schema",
    )
    snapshot_id: str = Field(pattern=r"^evidence_[0-9a-f]{64}$")
    selected_workflow: str
    baseline_surface_manifest_id: str
    objective: Objective
    selection: SelectionPolicy
    runs: tuple[RunEvidence, ...]
    excluded_runs: tuple[ExcludedRun, ...] = ()
    issues: tuple[EvidenceIssue, ...] = ()
    observations: tuple[Observation, ...]
    groups: tuple[EvidenceGroup, ...]
    selected_group_id: str | None = None
    recommendation_basis: Literal[
        "current_verified",
        "historical_verified",
        "historical_unverified",
        "no_comparable_evidence",
    ]
    step_metrics: tuple[StepMetric, ...]
    shortlist: tuple[StepRanking, ...]
    measure_first: tuple[str, ...] = ()
    next_action: Literal["propose_changes", "collect_evidence", "no_change"]
    budget: EvidenceBudget

    @model_validator(mode="after")
    def identity_matches(self):
        if self.snapshot_id != _content_id("evidence", self, {"snapshot_id"}):
            raise ValueError("snapshot_id does not match canonical evidence content")
        return self

    def citable_observation_ids(self) -> frozenset[str]:
        return frozenset(item.observation_id for item in self.observations)


def capture_evidence_snapshot(
    selected_workflow: str,
    inspections: Iterable[Mapping[str, Any] | RunObservation],
    *,
    source_manifest: SourceManifest,
    objective: Objective = "reliability",
    top_k_steps: int = 1,
    max_evidence_bytes: int = 50 * 1024 * 1024,
    explicit_run_refs: bool = False,
    route_tags: tuple[str, ...] = (),
    current_workflow_identity: str | None = None,
    current_surface_id: str | None = None,
    current_orchestration_id: str | None = None,
    baseline_surface_manifest_id: str | None = None,
) -> EvidenceSnapshot:
    """Normalize, bound, group, and rank journal observations without estimating missing data."""
    if top_k_steps <= 0 or max_evidence_bytes <= 0:
        raise ValueError("top_k_steps and max_evidence_bytes must be positive")
    if objective not in {"reliability", "token_usage", "latency"}:
        raise ValueError("unsupported optimizer objective")
    supplied = tuple(inspections)
    routes = tuple(dict.fromkeys(route_tags))
    admitted: list[RunObservation] = []
    excluded: list[ExcludedRun] = []
    admitted_bytes = len(_canonical(source_manifest))
    omitted_bytes = 0
    if admitted_bytes > max_evidence_bytes:
        raise ValueError("selected workflow manifest exceeds max_evidence_bytes")
    for raw in supplied:
        run = raw if isinstance(raw, RunObservation) else load_run_observation(raw)
        if run.workflow_name and run.workflow_name != selected_workflow:
            raise ValueError(
                f"run {run.run_id} belongs to {run.workflow_name}, not {selected_workflow}"
            )
        size = len(_canonical(run))
        if admitted_bytes + size > max_evidence_bytes:
            excluded.append(
                ExcludedRun(
                    run_ref=run.run_ref, reason="input_limit_exceeded", bytes=size
                )
            )
            omitted_bytes += size
            continue
        admitted.append(run)
        admitted_bytes += size

    observations: list[Observation] = []
    issues: list[EvidenceIssue] = []
    run_records: list[RunEvidence] = []
    groups: dict[str, list[str]] = defaultdict(list)
    group_versions: dict[str, str | None] = {}
    group_workflow_ids: dict[str, str] = {}
    group_orchestration_ids: dict[str, str | None] = {}
    group_order: list[str] = []
    for run in admitted:
        known = (
            run.provenance_state == "known"
            and bool(run.workflow_identity)
            and bool(run.surface_id)
            and bool(run.orchestration_id)
        )
        group_key = (
            json.dumps(
                [run.workflow_identity, run.surface_id, run.orchestration_id],
                separators=(",", ":"),
            )
            if known
            else f"{run.provenance_state}:{run.run_id}"
        )
        group_id = "group_" + sha256(group_key.encode()).hexdigest()
        if group_id not in groups:
            group_order.append(group_id)
        groups[group_id].append(run.run_ref)
        group_versions[group_id] = run.surface_id if known else None
        group_workflow_ids[group_id] = (
            run.workflow_identity or run.workflow_name or selected_workflow
        )
        group_orchestration_ids[group_id] = run.orchestration_id if known else None
        ids: list[str] = []
        for operation in run.operations:
            observation_payload = {
                "run_ref": run.run_ref,
                "operation_id": operation.operation_id,
                "group_id": group_id,
                "step_id": operation.name,
                "step_kind": operation.kind,
            }
            observation_id = (
                "observation_" + sha256(_canonical(observation_payload)).hexdigest()
            )
            ids.append(observation_id)
            usage_state, tokens, dispatch_count = _usage(
                operation.kind,
                operation.usage,
                operation.dispatches,
                operation.attempts,
            )
            elapsed_available, elapsed_seconds = _elapsed(operation)
            direct_failure = operation.status in {
                "failed",
                "interrupted",
                "budget_exceeded",
                "cancelled",
            } or any(
                dispatch.outcome in {"failed", "timed_out", "interrupted", "cancelled"}
                for dispatch in operation.dispatches
            )
            observation = Observation(
                observation_id=observation_id,
                operation_id=operation.operation_id,
                run_ref=run.run_ref,
                group_id=group_id,
                step_id=operation.name,
                step_kind=operation.kind,
                scope=operation.scope,
                status=operation.status,
                outcome=operation.outcome,
                focused=not routes or operation.outcome in routes,
                direct_failure=direct_failure,
                rework_rejection=operation.outcome
                in {"needs_rework", "rejected", "needs_replan"},
                attempted_dispatch_count=dispatch_count,
                usage_availability=usage_state,
                known_total_tokens=tokens,
                elapsed_available=elapsed_available,
                elapsed_seconds=elapsed_seconds,
            )
            observations.append(observation)
            if run.provenance_state != "known":
                issues.append(
                    EvidenceIssue(
                        run_ref=run.run_ref,
                        observation_id=observation_id,
                        dimension="provenance",
                        reason=f"{run.provenance_state}_workflow_surface",
                    )
                )
            if operation.kind == "provider" and usage_state != "known_total":
                issues.append(
                    EvidenceIssue(
                        run_ref=run.run_ref,
                        observation_id=observation_id,
                        dimension="token_usage",
                        reason=f"{usage_state}_dispatch_usage",
                    )
                )
            if not elapsed_available:
                issues.append(
                    EvidenceIssue(
                        run_ref=run.run_ref,
                        observation_id=observation_id,
                        dimension="latency",
                        reason="elapsed_time_unavailable",
                    )
                )
        run_records.append(
            RunEvidence(
                run_ref=run.run_ref,
                task_id=run.task_id,
                run_id=run.run_id,
                status=run.status,
                workflow_identity=run.workflow_identity
                or run.workflow_name
                or selected_workflow,
                workflow_surface_id=run.surface_id if known else None,
                orchestration_id=run.orchestration_id if known else None,
                provenance_state=run.provenance_state,
                structural_group_id=group_id,
                observation_ids=tuple(ids),
            )
        )

    group_records = tuple(
        EvidenceGroup(
            group_id=group_id,
            workflow_identity=group_workflow_ids[group_id],
            workflow_surface_id=group_versions[group_id],
            orchestration_id=group_orchestration_ids[group_id],
            run_refs=tuple(sorted(refs)),
            current_match=bool(
                current_workflow_identity
                and current_surface_id
                and (current_orchestration_id or source_manifest.workflow_version)
                and group_workflow_ids[group_id] == current_workflow_identity
                and group_versions[group_id] == current_surface_id
                and group_orchestration_ids[group_id]
                == (current_orchestration_id or source_manifest.workflow_version)
            ),
        )
        for group_id, refs in sorted(groups.items())
    )
    selected_group = next(
        (item.group_id for item in group_records if item.current_match), None
    )
    if selected_group is None and group_order:
        selected_group = group_order[0]
    comparable = [
        item
        for item in observations
        if item.group_id == selected_group and item.focused
    ]
    metrics = _metrics(comparable)
    shortlist, measure_first = _rank(metrics, objective, top_k_steps)
    if shortlist:
        next_action = "propose_changes"
    elif objective == "reliability" and comparable:
        next_action = "no_change"
    else:
        next_action = "collect_evidence"
    basis = (
        "no_comparable_evidence"
        if selected_group is None
        else "current_verified"
        if any(item.current_match for item in group_records)
        else "historical_verified"
        if group_versions.get(selected_group)
        else "historical_unverified"
    )
    baseline_id = baseline_surface_manifest_id or baseline_surface_id(source_manifest)
    payload = {
        "schema": "botpipe.workflow_optimization.evidence/v2",
        "snapshot_id": "evidence_" + "0" * 64,
        "selected_workflow": selected_workflow,
        "baseline_surface_manifest_id": baseline_id,
        "objective": objective,
        "selection": SelectionPolicy(
            explicit_run_refs=explicit_run_refs,
            route_tags=routes,
            selected_run_count=len(supplied),
            admitted_run_count=len(admitted),
            focused_observation_count=sum(item.focused for item in observations),
            captured_observation_count=len(observations),
        ),
        "runs": tuple(run_records),
        "excluded_runs": tuple(excluded),
        "issues": tuple(issues),
        "observations": tuple(observations),
        "groups": group_records,
        "selected_group_id": selected_group,
        "recommendation_basis": basis,
        "step_metrics": metrics,
        "shortlist": shortlist,
        "measure_first": measure_first,
        "next_action": next_action,
        "budget": EvidenceBudget(
            max_bytes=max_evidence_bytes,
            admitted_bytes=admitted_bytes,
            omitted_bytes=omitted_bytes,
            budget_limited=bool(excluded),
        ),
    }
    provisional = EvidenceSnapshot.model_construct(**payload)
    payload["snapshot_id"] = _content_id("evidence", provisional, {"snapshot_id"})
    return EvidenceSnapshot.model_validate(payload)


def _metrics(observations: list[Observation]) -> tuple[StepMetric, ...]:
    grouped: dict[tuple[str, str, str], list[Observation]] = defaultdict(list)
    for item in observations:
        grouped[(item.group_id, item.step_id, item.step_kind)].append(item)
    result = []
    for (group_id, step_id, kind), values in sorted(grouped.items()):
        dispatches = [item for item in values if item.step_kind == "provider"]
        complete_usage = bool(dispatches) and all(
            item.usage_availability == "known_total" for item in dispatches
        )
        complete_elapsed = all(item.elapsed_available for item in values)
        result.append(
            StepMetric(
                metric_id="metric_"
                + sha256(f"{group_id}:{kind}:{step_id}".encode()).hexdigest(),
                group_id=group_id,
                step_id=step_id,
                step_kind=kind,
                observation_count=len(values),
                distinct_run_count=len({item.run_ref for item in values}),
                direct_failure_count=sum(item.direct_failure for item in values),
                direct_failure_run_count=len(
                    {item.run_ref for item in values if item.direct_failure}
                ),
                rework_rejection_count=sum(item.rework_rejection for item in values),
                rework_run_count=len(
                    {item.run_ref for item in values if item.rework_rejection}
                ),
                attempted_dispatch_count=sum(
                    item.attempted_dispatch_count for item in dispatches
                ),
                complete_usage=complete_usage,
                known_total_tokens=(
                    sum(item.known_total_tokens or 0 for item in dispatches)
                    if complete_usage
                    else None
                ),
                complete_elapsed=complete_elapsed,
                total_elapsed_seconds=(
                    sum(item.elapsed_seconds or 0 for item in values)
                    if complete_elapsed
                    else None
                ),
            )
        )
    return tuple(result)


def _rank(metrics: tuple[StepMetric, ...], objective: Objective, top_k: int):
    if objective == "reliability":
        eligible = [
            item
            for item in metrics
            if item.direct_failure_count or item.rework_rejection_count
        ]
        eligible.sort(
            key=lambda item: (
                -item.direct_failure_run_count,
                -item.rework_run_count,
                item.step_id,
                item.group_id,
            )
        )
        measure = ()
    elif objective == "token_usage":
        eligible = [
            item
            for item in metrics
            if item.complete_usage and (item.known_total_tokens or 0) > 0
        ]
        eligible.sort(
            key=lambda item: (
                -(item.known_total_tokens or 0),
                item.step_id,
                item.group_id,
            )
        )
        measure = tuple(item.metric_id for item in metrics if not item.complete_usage)
    else:
        eligible = [
            item
            for item in metrics
            if item.complete_elapsed and (item.total_elapsed_seconds or 0) > 0
        ]
        eligible.sort(
            key=lambda item: (
                -(item.total_elapsed_seconds or 0),
                item.step_id,
                item.group_id,
            )
        )
        measure = tuple(item.metric_id for item in metrics if not item.complete_elapsed)
    rankings = tuple(
        StepRanking(
            rank=index,
            metric_id=item.metric_id,
            group_id=item.group_id,
            step_id=item.step_id,
            objective=objective,
            direct_failure_run_count=item.direct_failure_run_count,
            rework_run_count=item.rework_run_count,
            distinct_run_count=item.distinct_run_count,
            observation_count=item.observation_count,
            known_total_tokens=item.known_total_tokens,
            total_elapsed_seconds=item.total_elapsed_seconds,
        )
        for index, item in enumerate(eligible[:top_k], 1)
    )
    return rankings, tuple(sorted(measure))


def _usage(
    kind: str, usage: Mapping[str, float], dispatches: tuple[Any, ...], attempts: int
) -> tuple[Availability, int | None, int]:
    if kind != "provider":
        return "not_attempted", None, 0
    if dispatches:
        if all(item.usage_availability == "known_total" for item in dispatches):
            totals = [_known_token_total(item.usage) for item in dispatches]
            if all(item is not None for item in totals):
                return (
                    "known_total",
                    sum(item for item in totals if item is not None),
                    len(dispatches),
                )
        if any(item.usage for item in dispatches):
            return "partial", None, len(dispatches)
        return "unknown", None, len(dispatches)
    if attempts != 1:
        return "unknown", None, attempts
    state, tokens = _legacy_usage(usage)
    return state, tokens, 1


def _legacy_usage(usage: Mapping[str, float]) -> tuple[Availability, int | None]:
    finite = {
        key: value
        for key, value in usage.items()
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    }
    if "total_tokens" in finite:
        return "known_total", int(finite["total_tokens"])
    if "input_tokens" in finite and "output_tokens" in finite:
        return "known_total", int(finite["input_tokens"] + finite["output_tokens"])
    if finite:
        return "partial", None
    return "unknown", None


def _known_token_total(usage: Mapping[str, float]) -> int | None:
    state, total = _legacy_usage(usage)
    return total if state == "known_total" else None


def _elapsed(operation: Any) -> tuple[bool, float | None]:
    if operation.kind == "provider" and operation.dispatches:
        if all(item.elapsed_seconds is not None for item in operation.dispatches):
            return True, sum(item.elapsed_seconds for item in operation.dispatches)
        return False, None
    if operation.kind == "provider" and operation.attempts != 1:
        return False, None
    duration = operation.duration_ms
    available = duration is not None and math.isfinite(duration) and duration >= 0
    return available, duration / 1000 if available else None


def _canonical(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    elif hasattr(value, "to_dict"):
        value = value.to_dict()
    elif hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict

        value = asdict(value)
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False
    ).encode()


def baseline_surface_id(value: SourceManifest | Mapping[str, Any]) -> str:
    return "baseline_" + sha256(_canonical(value)).hexdigest()


def _content_id(prefix: str, value: BaseModel, exclude: set[str]) -> str:
    payload = value.model_dump(mode="json")
    for key in exclude:
        payload.pop(key, None)
    return f"{prefix}_{sha256(_canonical(payload)).hexdigest()}"


__all__ = [
    "Availability",
    "EvidenceBudget",
    "EvidenceGroup",
    "EvidenceIssue",
    "EvidenceSnapshot",
    "ExcludedRun",
    "Objective",
    "Observation",
    "RunEvidence",
    "SelectionPolicy",
    "StepMetric",
    "StepRanking",
    "baseline_surface_id",
    "capture_evidence_snapshot",
]
