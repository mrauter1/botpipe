"""Optimizer-v2 evidence capture and deterministic observed-burden ranking."""
from __future__ import annotations

import json
import os
import shutil
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from botpipe.core.statuses import route_is_rework

EVIDENCE_SNAPSHOT_SCHEMA = "botpipe.workflow_optimization.evidence/v2"
DEFAULT_MAX_EVIDENCE_BYTES = 50 * 1024 * 1024
Objective = Literal["reliability", "token_usage", "latency"]


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True, serialize_by_alias=True)


class SelectionPolicy(_Record):
    explicit_run_refs: bool
    route_tags: tuple[str, ...] = ()
    denominator: Literal["full_captured_group", "focused_subset"]
    selected_run_count: int = Field(ge=0)
    admitted_run_count: int = Field(ge=0)
    focused_observation_count: int = Field(ge=0)
    captured_observation_count: int = Field(ge=0)


class EvidenceIssue(_Record):
    run_ref: str | None = None
    observation_id: str | None = None
    dimension: str
    reason: str
    detail: str | None = None


class ExcludedRun(_Record):
    run_ref: str
    reason: str
    bytes: int | None = Field(default=None, ge=0)


class RawEvidenceReference(_Record):
    role: str
    source_path: str | None = None
    recorded_sha256: str | None = None
    recorded_bytes: int | None = Field(default=None, ge=0)
    verification: Literal["verified", "missing_metadata", "invalid_path", "missing", "not_regular", "symlink_escape", "digest_mismatch", "byte_count_mismatch", "budget_omitted"]
    snapshot_path: str | None = None
    snapshot_sha256: str | None = None
    snapshot_bytes: int | None = Field(default=None, ge=0)


class UsageAttempt(_Record):
    dispatch_id: str
    phase: str
    attempt: int | None = Field(default=None, ge=1)
    provider: str | None = None
    model: str | None = None
    effort: str | None = None
    outcome: str | None = None
    availability: Literal["known_total", "partial", "unknown"]
    total_source: Literal["reported", "derived", "unavailable"]
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    elapsed_seconds: float | None = Field(default=None, ge=0)


class Observation(_Record):
    observation_id: str
    run_ref: str
    sequence: int = Field(ge=0)
    execution_identity: str
    identity_source: Literal["step_execution_id", "sequence_fallback"]
    visit: int | None = Field(default=None, ge=0)
    step_id: str
    step_kind: str
    scope: str | None = None
    item_id: str | None = None
    lane_id: str | None = None
    lineage: Literal["known", "unknown"]
    route: str | None = None
    target_step: str | None = None
    outcome: str | None = None
    runtime_control: str | None = None
    provider: str | None = None
    source_hook: str | None = None
    redirect: str | None = None
    focused: bool
    direct_failure: bool
    rework_rejection: bool
    rework_cycle: bool = False
    associated_next_observation_id: str | None = None
    raw_references: tuple[RawEvidenceReference, ...] = ()
    attempts: tuple[UsageAttempt, ...] = ()
    usage_availability: Literal["known_total", "partial", "unknown", "not_attempted"]
    known_total_tokens: int = Field(ge=0)
    elapsed_seconds: float | None = Field(default=None, ge=0)
    elapsed_available: bool = False

    @property
    def raw_content_citable(self) -> bool:
        return any(item.verification == "verified" for item in self.raw_references)


class RunEvidence(_Record):
    run_ref: str
    task_id: str
    run_id: str
    status: str | None = None
    terminal: str | None = None
    completed_at: str | None = None
    workflow_identity: str
    surface_manifest_id: str | None = None
    topology_id: str | None = None
    parameter_digest: str | None = None
    configuration_digest: str | None = None
    provider_policy_identity: str | None = None
    case_identity: str | None = None
    provenance_state: Literal["known", "unknown", "mixed"]
    structural_group_id: str | None = None
    observation_ids: tuple[str, ...] = ()


class EvidenceGroup(_Record):
    group_id: str
    workflow_identity: str
    surface_manifest_id: str
    topology_id: str
    run_refs: tuple[str, ...]
    current_match: bool
    latest_completion: str | None = None
    latest_run_ref: str | None = None


class ResourceBreakdown(_Record):
    provider: str | None = None
    model: str | None = None
    effort: str | None = None
    attempted_dispatches: int = Field(ge=0)
    known_total_tokens: int = Field(ge=0)


class StepMetric(_Record):
    metric_id: str
    group_id: str
    group_scope: Literal["structural_group", "single_run"]
    step_id: str
    step_kind: str
    observation_count: int = Field(ge=0)
    distinct_run_count: int = Field(ge=0)
    direct_failure_count: int = Field(ge=0)
    direct_failure_run_count: int = Field(ge=0)
    rework_rejection_count: int = Field(ge=0)
    rework_run_count: int = Field(ge=0)
    rework_cycle_count: int = Field(ge=0)
    attempted_dispatch_count: int = Field(ge=0)
    complete_usage: bool
    known_total_tokens: int = Field(ge=0)
    complete_elapsed: bool
    total_elapsed_seconds: float = Field(ge=0)
    resource_breakdowns: tuple[ResourceBreakdown, ...] = ()
    parameter_digests: tuple[str, ...] = ()
    configuration_digests: tuple[str, ...] = ()
    case_identities: tuple[str, ...] = ()


class StepRanking(_Record):
    rank: int = Field(ge=1)
    metric_id: str
    group_id: str
    step_id: str
    objective: Objective
    direct_failure_run_count: int = Field(ge=0)
    rework_run_count: int = Field(ge=0)
    distinct_run_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    attempted_dispatch_count: int = Field(ge=0)
    known_total_tokens: int = Field(ge=0)
    total_elapsed_seconds: float = Field(ge=0)


class EvidenceBudget(_Record):
    max_bytes: int = Field(gt=0)
    admitted_bytes: int = Field(ge=0)
    omitted_bytes: int = Field(ge=0)
    budget_limited: bool
    omitted_observation_ids: tuple[str, ...] = ()


class EvidenceSnapshot(_Record):
    schema_version: Literal["botpipe.workflow_optimization.evidence/v2"] = Field(default=EVIDENCE_SNAPSHOT_SCHEMA, alias="schema")
    snapshot_id: str
    selected_workflow: str
    baseline_surface_manifest_id: str | None = None
    objective: Objective
    selection: SelectionPolicy
    runs: tuple[RunEvidence, ...]
    excluded_runs: tuple[ExcludedRun, ...] = ()
    issues: tuple[EvidenceIssue, ...] = ()
    observations: tuple[Observation, ...]
    groups: tuple[EvidenceGroup, ...] = ()
    selected_group_id: str | None = None
    recommendation_basis: Literal["current_verified", "historical_verified", "historical_unverified", "no_comparable_evidence"]
    step_metrics: tuple[StepMetric, ...] = ()
    shortlist: tuple[StepRanking, ...] = ()
    measure_first: tuple[str, ...] = ()
    next_action: Literal["propose_changes", "collect_evidence", "no_change"]
    budget: EvidenceBudget

    @model_validator(mode="after")
    def _check_id(self) -> "EvidenceSnapshot":
        if self.snapshot_id != _snapshot_digest(self.model_dump(mode="json")):
            raise ValueError("snapshot_id does not match canonical evidence content")
        return self

    def verify_identity(self) -> bool:
        return self.snapshot_id == _snapshot_digest(self.model_dump(mode="json"))

    def citable_observation_ids(self, *, require_raw_content: bool = False) -> frozenset[str]:
        return frozenset(item.observation_id for item in self.observations if not require_raw_content or item.raw_content_citable)


class _Draft(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    observation: dict[str, Any]
    raw: dict[str, Any]


class _Captured(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    run_dir: Path
    run_json: dict[str, Any]
    trace: list[dict[str, Any]]
    watermark: dict[Path, tuple[int, int, int, int]]
    core_bytes: int
    provenance: dict[str, Any]
    drafts: list[_Draft]


def capture_evidence_snapshot(
    root: Path,
    selected_workflow: str,
    run_dirs: Sequence[Path],
    snapshot_dir: Path,
    *,
    route_tags: Sequence[str] = (),
    objective: Objective = "reliability",
    top_k_steps: int = 1,
    max_evidence_bytes: int = DEFAULT_MAX_EVIDENCE_BYTES,
    explicit_run_refs: bool = False,
    current_workflow_identity: str | None = None,
    current_surface_manifest_id: str | None = None,
    current_topology_id: str | None = None,
) -> EvidenceSnapshot:
    """Capture stable evidence once, group comparable runs, and rank observed burden."""
    repo_root = root.resolve()
    if not selected_workflow.strip():
        raise ValueError("selected_workflow must be non-empty")
    if objective not in {"reliability", "token_usage", "latency"}:
        raise ValueError("objective must be reliability, token_usage, or latency")
    if top_k_steps <= 0 or max_evidence_bytes <= 0:
        raise ValueError("top_k_steps and max_evidence_bytes must be positive")
    routes = tuple(dict.fromkeys(_required_text(value, "route_tags") for value in route_tags))
    destination = snapshot_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    remaining = max_evidence_bytes
    admitted_bytes = omitted_bytes = 0
    excluded: list[ExcludedRun] = []
    issues: list[EvidenceIssue] = []
    captured: list[_Captured] = []

    for source in run_dirs:
        run_dir = source.resolve()
        try:
            run_dir.relative_to(repo_root)
        except ValueError:
            if explicit_run_refs:
                raise ValueError(f"explicit run directory is outside the capture root: {run_dir}")
            excluded.append(ExcludedRun(run_ref=run_dir.name, reason="run_outside_capture_root"))
            continue
        run_ref = _path_run_ref(run_dir)
        if run_dir.parent.name != "runs" or run_dir.parent.parent.name != f"wf_{selected_workflow}":
            if explicit_run_refs:
                raise ValueError(f"explicit run directory has the wrong workflow identity: {run_dir}")
            excluded.append(ExcludedRun(run_ref=run_ref, reason="wrong_selected_workflow"))
            continue
        required = [run_dir / "run.json", run_dir / "trace.jsonl"]
        optional = [run_dir / "git_tracking.jsonl", run_dir / "static_step_graph.json", run_dir / "provenance.json"]
        missing = next((item.name for item in required if not item.is_file()), None)
        if missing:
            excluded.append(ExcludedRun(run_ref=run_ref, reason=f"missing_{missing.replace('.', '_')}"))
            continue
        files = required + [item for item in optional if item.is_file()]
        try:
            watermark = {item: _watermark(item) for item in files}
            size = sum(mark[2] for mark in watermark.values())
        except OSError as exc:
            excluded.append(ExcludedRun(run_ref=run_ref, reason="unreadable_core_input"))
            issues.append(EvidenceIssue(run_ref=run_ref, dimension="core", reason="unreadable", detail=_error_detail(exc)))
            continue
        if size > remaining:
            excluded.append(ExcludedRun(run_ref=run_ref, reason="input_limit_exceeded", bytes=size))
            omitted_bytes += size
            continue
        try:
            run_json, trace = _read_json(required[0]), _read_jsonl(required[1])
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            excluded.append(ExcludedRun(run_ref=run_ref, reason="invalid_core_input", bytes=size))
            issues.append(EvidenceIssue(run_ref=run_ref, dimension="core", reason="invalid", detail=_error_detail(exc)))
            continue
        schemas = {record.get("schema") for record in trace if record.get("schema") is not None}
        if run_json.get("schema") not in {None, "botpipe.run_metadata/v1"} or not schemas.issubset({"botpipe.runtime_trace/v1"}):
            excluded.append(ExcludedRun(run_ref=run_ref, reason="unsupported_core_schema", bytes=size))
            continue
        task_id, run_id = run_ref.split("/", 1)
        if _text(run_json.get("task_id")) != task_id or _text(run_json.get("run_id")) != run_id:
            if explicit_run_refs:
                raise ValueError(f"explicit run {run_ref} has mismatched recorded identity")
            excluded.append(ExcludedRun(run_ref=run_ref, reason="wrong_run_identity", bytes=size))
            continue
        if _text(run_json.get("workflow_name")) != selected_workflow:
            if explicit_run_refs:
                raise ValueError(f"explicit run {run_ref} belongs to a different workflow")
            excluded.append(ExcludedRun(run_ref=run_ref, reason="wrong_selected_workflow", bytes=size))
            continue
        status = (_text(run_json.get("status")) or "").lower()
        if status in {"running", "active", "in_progress", "resuming"}:
            if explicit_run_refs:
                raise ValueError(f"explicit run {run_ref} is active; pause or complete it before evidence capture")
            excluded.append(ExcludedRun(run_ref=run_ref, reason="active_run_excluded", bytes=size))
            continue
        graph = None
        graph_path = run_dir / "static_step_graph.json"
        if graph_path.is_file():
            try:
                graph = _read_json(graph_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                issues.append(EvidenceIssue(run_ref=run_ref, dimension="topology", reason="invalid", detail=_error_detail(exc)))
        else:
            issues.append(EvidenceIssue(run_ref=run_ref, dimension="topology", reason="missing"))
        git_path = run_dir / "git_tracking.jsonl"
        if not git_path.is_file() or git_path.stat().st_size == 0:
            issues.append(EvidenceIssue(run_ref=run_ref, dimension="git", reason="missing_or_empty"))
        else:
            try:
                _read_jsonl(git_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                issues.append(EvidenceIssue(run_ref=run_ref, dimension="git", reason="invalid", detail=_error_detail(exc)))
        provenance = _provenance(run_ref, run_json, trace, graph, selected_workflow)
        drafts = _observations(run_ref, trace, graph, routes, issues)
        captured.append(_Captured(run_dir=run_dir, run_json=run_json, trace=trace, watermark=watermark, core_bytes=size, provenance=provenance, drafts=drafts))
        remaining -= size
        admitted_bytes += size

    raw_cache: dict[tuple[Path, str, int], tuple[str, str, int]] = {}
    normalized: dict[str, Observation] = {}
    omitted_ids: set[str] = set()
    for item, draft in _raw_order(captured):
        refs = []
        for role, value in sorted(draft.raw.items()):
            ref, spent, omitted = _copy_raw(item.run_dir, destination, item.provenance["run_ref"], role, value, remaining, raw_cache)
            refs.append(ref)
            remaining -= spent
            admitted_bytes += spent
            omitted_bytes += omitted
            if ref.verification != "verified":
                issues.append(EvidenceIssue(run_ref=item.provenance["run_ref"], observation_id=draft.observation["observation_id"], dimension="raw_content", reason=ref.verification))
            if ref.verification == "budget_omitted":
                omitted_ids.add(draft.observation["observation_id"])
        normalized[draft.observation["observation_id"]] = Observation.model_validate({**draft.observation, "raw_references": refs})

    stable: list[_Captured] = []
    for item in captured:
        try:
            unchanged = all(_watermark(path) == mark for path, mark in item.watermark.items())
            unchanged = unchanged and _read_json(item.run_dir / "run.json").get("status") == item.run_json.get("status")
        except (OSError, ValueError, json.JSONDecodeError):
            unchanged = False
        if unchanged:
            stable.append(item)
        else:
            excluded.append(ExcludedRun(run_ref=item.provenance["run_ref"], reason="concurrently_changed", bytes=item.core_bytes))
            issues.append(EvidenceIssue(run_ref=item.provenance["run_ref"], dimension="core", reason="concurrently_changed"))
            admitted_bytes -= item.core_bytes
    observations = _lineage([normalized[d.observation["observation_id"]] for item in stable for d in item.drafts])
    groups, runs = _groups(
        stable,
        observations,
        current_workflow_identity,
        current_surface_manifest_id,
        current_topology_id,
    )
    selected_group, basis, sets = _analysis_sets(groups, runs, observations, explicit_run_refs)
    metrics = _metrics(sets, runs)
    shortlist, measure_first = _rank(metrics, objective, top_k_steps)
    if basis == "historical_unverified":
        action = "collect_evidence"
    elif shortlist:
        action = "propose_changes"
    elif observations or issues or excluded:
        action = "collect_evidence"
    else:
        action = "no_change"
    payload = {
        "schema": EVIDENCE_SNAPSHOT_SCHEMA,
        "snapshot_id": "",
        "selected_workflow": selected_workflow,
        "baseline_surface_manifest_id": current_surface_manifest_id,
        "objective": objective,
        "selection": {"explicit_run_refs": explicit_run_refs, "route_tags": routes, "denominator": "focused_subset" if routes else "full_captured_group", "selected_run_count": len(run_dirs), "admitted_run_count": len(runs), "focused_observation_count": sum(o.focused for o in observations), "captured_observation_count": len(observations)},
        "runs": [item.model_dump(mode="json") for item in runs],
        "excluded_runs": [item.model_dump(mode="json") for item in excluded],
        "issues": [item.model_dump(mode="json") for item in issues],
        "observations": [item.model_dump(mode="json") for item in observations],
        "groups": [item.model_dump(mode="json") for item in groups],
        "selected_group_id": selected_group,
        "recommendation_basis": basis,
        "step_metrics": [item.model_dump(mode="json") for item in metrics],
        "shortlist": [item.model_dump(mode="json") for item in shortlist],
        "measure_first": measure_first,
        "next_action": action,
        "budget": {"max_bytes": max_evidence_bytes, "admitted_bytes": admitted_bytes, "omitted_bytes": omitted_bytes, "budget_limited": bool(omitted_ids or any(item.reason == "input_limit_exceeded" for item in excluded)), "omitted_observation_ids": sorted(omitted_ids)},
    }
    payload["snapshot_id"] = _snapshot_digest(payload)
    return EvidenceSnapshot.model_validate(payload)


def write_evidence_snapshot(snapshot: EvidenceSnapshot, path: Path) -> Path:
    if not snapshot.verify_identity():
        raise ValueError("cannot write evidence snapshot with invalid identity")
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def read_evidence_snapshot(path: Path) -> EvidenceSnapshot:
    return EvidenceSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def _observations(run_ref: str, trace: Sequence[Mapping[str, Any]], graph: Mapping[str, Any] | None, routes: Sequence[str], issues: list[EvidenceIssue]) -> list[_Draft]:
    finished = [r for r in trace if r.get("event_type") == "step_finished" and isinstance(r.get("step_name"), str) and isinstance(r.get("sequence"), int)]
    dispatch = [r for r in trace if str(r.get("event_type", "")).startswith("provider_dispatch_")]
    semantic = [r for r in trace if str(r.get("event_type", "")).startswith("provider_attempt_")]
    sequential = _legacy_sequential(graph)
    result: list[_Draft] = []
    seen: set[str] = set()
    for record in finished:
        sequence, step = int(record["sequence"]), str(record["step_name"])
        execution = _text(record.get("step_execution_id"))
        identity = execution or f"sequence:{sequence}"
        observation_id = f"{run_ref}:{identity}"
        if observation_id in seen:
            observation_id += f":sequence:{sequence}"
            issues.append(EvidenceIssue(run_ref=run_ref, dimension="execution_identity", reason="duplicate"))
        seen.add(observation_id)
        scope, item_id = _text(record.get("scope")), _text(record.get("item_id"))
        if scope is not None or item_id is not None:
            lane, lineage = _hash({"run": run_ref, "scope": scope, "item": item_id}), "known"
        elif sequential:
            lane, lineage = _hash({"run": run_ref, "legacy": "sequential"}), "known"
        else:
            lane, lineage = None, "unknown"
        route = _route(record)
        target = _text(record.get("target_step")) or _target(graph, step, route)
        matching = _events(dispatch, record, identity, sequence)
        attempts = _attempts(matching) if matching else (_attempts(_events(semantic, record, identity, sequence)) or _legacy_attempts(record))
        availability, tokens = _usage(attempts)
        elapsed = _elapsed(record)
        result.append(_Draft(observation={
            "observation_id": observation_id, "run_ref": run_ref, "sequence": sequence,
            "execution_identity": identity, "identity_source": "step_execution_id" if execution else "sequence_fallback",
            "visit": _nn(record.get("visit")), "step_id": step, "step_kind": _text(record.get("step_kind")) or "unknown",
            "scope": scope, "item_id": item_id, "lane_id": lane, "lineage": lineage, "route": route,
            "target_step": target, "outcome": _outcome(record), "runtime_control": _text(record.get("runtime_control")),
            "provider": _text(record.get("provider")), "source_hook": _text(record.get("source_hook")),
            "redirect": _text(record.get("redirect")) or _text(record.get("redirect_step")),
            "focused": not routes or route in routes, "direct_failure": _failure(record, route),
            "rework_rejection": bool(route and route_is_rework(route)), "attempts": attempts,
            "usage_availability": availability, "known_total_tokens": tokens,
            "elapsed_seconds": elapsed, "elapsed_available": elapsed is not None,
        }, raw=dict(record.get("raw_output_refs")) if isinstance(record.get("raw_output_refs"), Mapping) else {}))
    return result


def _lineage(observations: Sequence[Observation]) -> list[Observation]:
    lanes: dict[str, list[Observation]] = defaultdict(list)
    for item in observations:
        if item.lane_id:
            lanes[item.lane_id].append(item)
    updates: dict[str, dict[str, Any]] = {}
    for lane in lanes.values():
        lane.sort(key=lambda x: (x.sequence, x.visit if x.visit is not None else -1, x.observation_id))
        for before, after in zip(lane, lane[1:]):
            matched = before.target_step == after.step_id
            updates[before.observation_id] = {
                "associated_next_observation_id": after.observation_id if matched else None,
                "rework_cycle": bool(before.rework_rejection and before.target_step == before.step_id == after.step_id and ((after.visit > before.visit) if before.visit is not None and after.visit is not None else after.sequence > before.sequence)),
            }
    return [item.model_copy(update=updates.get(item.observation_id, {})) for item in observations]


def _groups(
    captured: Sequence[_Captured],
    observations: Sequence[Observation],
    current_workflow: str | None,
    current_surface: str | None,
    current_topology: str | None,
) -> tuple[list[EvidenceGroup], list[RunEvidence]]:
    obs_ids: dict[str, list[str]] = defaultdict(list)
    for item in observations:
        obs_ids[item.run_ref].append(item.observation_id)
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in captured:
        p = item.provenance
        if p["provenance_state"] == "known" and p["surface_manifest_id"] and p["topology_id"]:
            buckets[(p["workflow_identity"], p["surface_manifest_id"], p["topology_id"])].append(p)
    groups, by_run = [], {}
    for (workflow, surface, topology), members in sorted(buckets.items()):
        group_id = "group-" + _hash({"workflow": workflow, "surface": surface, "topology": topology})[:20]
        for member in members:
            by_run[member["run_ref"]] = group_id
        latest = max(((m["completed_at"] or "", m["run_ref"]) for m in members), default=("", ""))
        groups.append(EvidenceGroup(group_id=group_id, workflow_identity=workflow, surface_manifest_id=surface, topology_id=topology, run_refs=tuple(sorted(m["run_ref"] for m in members)), current_match=workflow == current_workflow and surface == current_surface and topology == current_topology, latest_completion=latest[0] or None, latest_run_ref=latest[1] or None))
    runs = [RunEvidence(**item.provenance, structural_group_id=by_run.get(item.provenance["run_ref"]), observation_ids=tuple(obs_ids[item.provenance["run_ref"]])) for item in captured]
    return groups, runs


def _analysis_sets(groups: Sequence[EvidenceGroup], runs: Sequence[RunEvidence], observations: Sequence[Observation], explicit: bool):
    current = [g for g in groups if g.current_match]
    if current:
        chosen = max(current, key=lambda g: (g.latest_completion or "", g.latest_run_ref or ""))
        refs = set(chosen.run_refs)
        return chosen.group_id, "current_verified", [(chosen.group_id, "structural_group", [o for o in observations if o.run_ref in refs])]
    if not explicit:
        return None, "no_comparable_evidence", []
    known, unknown = {r.structural_group_id for r in runs if r.structural_group_id}, any(r.structural_group_id is None for r in runs)
    if len(known) == 1 and not unknown:
        group_id = next(iter(known))
        return group_id, "historical_verified", [(group_id, "structural_group", list(observations))]
    return None, "historical_unverified", [(f"run:{r.run_ref}", "single_run", [o for o in observations if o.run_ref == r.run_ref]) for r in runs]


def _metrics(sets, runs: Sequence[RunEvidence]) -> list[StepMetric]:
    run_map = {r.run_ref: r for r in runs}
    result = []
    for group_id, scope, observations in sets:
        by_step: dict[str, list[Observation]] = defaultdict(list)
        for item in observations:
            if item.focused:
                by_step[item.step_id].append(item)
        for step, values in sorted(by_step.items()):
            attempts = [a for o in values for a in o.attempts]
            breakdown: dict[tuple[str | None, str | None, str | None], list[UsageAttempt]] = defaultdict(list)
            for attempt in attempts:
                breakdown[(attempt.provider, attempt.model, attempt.effort)].append(attempt)
            refs = {o.run_ref for o in values}
            result.append(StepMetric(
                metric_id="metric-" + _hash({"group": group_id, "step": step})[:20], group_id=group_id, group_scope=scope,
                step_id=step, step_kind=values[0].step_kind, observation_count=len(values), distinct_run_count=len(refs),
                direct_failure_count=sum(o.direct_failure for o in values), direct_failure_run_count=len({o.run_ref for o in values if o.direct_failure}),
                rework_rejection_count=sum(o.rework_rejection for o in values), rework_run_count=len({o.run_ref for o in values if o.rework_rejection}), rework_cycle_count=sum(o.rework_cycle for o in values),
                attempted_dispatch_count=len(attempts), complete_usage=all(a.availability == "known_total" for a in attempts),
                known_total_tokens=sum(a.total_tokens or 0 for a in attempts if a.availability == "known_total"),
                complete_elapsed=all(o.elapsed_available for o in values), total_elapsed_seconds=sum(o.elapsed_seconds or 0 for o in values),
                resource_breakdowns=tuple(ResourceBreakdown(provider=k[0], model=k[1], effort=k[2], attempted_dispatches=len(items), known_total_tokens=sum(a.total_tokens or 0 for a in items if a.availability == "known_total")) for k, items in sorted(breakdown.items(), key=lambda x: tuple(v or "" for v in x[0]))),
                parameter_digests=tuple(sorted({run_map[r].parameter_digest for r in refs if run_map[r].parameter_digest})),
                configuration_digests=tuple(sorted({run_map[r].configuration_digest for r in refs if run_map[r].configuration_digest})),
                case_identities=tuple(sorted({run_map[r].case_identity for r in refs if run_map[r].case_identity})),
            ))
    return result


def _rank(metrics: Sequence[StepMetric], objective: Objective, top_k: int):
    if objective == "reliability":
        eligible = [m for m in metrics if m.direct_failure_count or m.rework_rejection_count]
        eligible.sort(key=lambda m: (-m.direct_failure_run_count, -m.rework_run_count, m.step_id, m.group_id)); measure = ()
    elif objective == "token_usage":
        eligible = [m for m in metrics if m.complete_usage and m.known_total_tokens > 0]
        eligible.sort(key=lambda m: (-m.known_total_tokens, m.step_id, m.group_id)); measure = tuple(sorted(m.metric_id for m in metrics if not m.complete_usage))
    else:
        eligible = [m for m in metrics if m.complete_elapsed and m.total_elapsed_seconds > 0]
        eligible.sort(key=lambda m: (-m.total_elapsed_seconds, m.step_id, m.group_id)); measure = tuple(sorted(m.metric_id for m in metrics if not m.complete_elapsed))
    rankings = [StepRanking(rank=i, metric_id=m.metric_id, group_id=m.group_id, step_id=m.step_id, objective=objective, direct_failure_run_count=m.direct_failure_run_count, rework_run_count=m.rework_run_count, distinct_run_count=m.distinct_run_count, observation_count=m.observation_count, attempted_dispatch_count=m.attempted_dispatch_count, known_total_tokens=m.known_total_tokens, total_elapsed_seconds=m.total_elapsed_seconds) for i, m in enumerate(eligible[:top_k], 1)]
    return rankings, measure


def _provenance(run_ref: str, run_json: Mapping[str, Any], trace: Sequence[Mapping[str, Any]], graph: Mapping[str, Any] | None, workflow: str) -> dict[str, Any]:
    root = _map(run_json.get("provenance")) or _map(run_json.get("workflow_provenance"))
    starts = [r for r in trace if r.get("event_type") in {"run_started", "workflow_started"}]
    ends = [r for r in trace if r.get("event_type") in {"run_finished", "workflow_finished"}]
    trace_start = (_map(starts[0].get("provenance")) or starts[0]) if starts else {}
    trace_end = (_map(ends[-1].get("provenance")) or ends[-1]) if ends else {}
    start, end = {**_map(root.get("start")), **trace_start}, {**_map(root.get("end")), **trace_end}
    sources = [start, end, root]
    def val(*names):
        for source in sources:
            for name in names:
                if _text(source.get(name)): return _text(source.get(name))
        for name in names:
            if _text(run_json.get(name)): return _text(run_json.get(name))
        return None
    workflow_id = val("workflow_identity", "workflow_name") or workflow
    surface = val("workflow_surface_manifest_id", "surface_manifest_id")
    topology = val("topology_id", "normalized_topology_id") or ("topology-" + _hash(_normalized_topology(graph)) if graph else None)
    mixed = any(_first(start, names) and _first(end, names) and _first(start, names) != _first(end, names) for names in (("workflow_identity", "workflow_name"), ("workflow_surface_manifest_id", "surface_manifest_id"), ("topology_id", "normalized_topology_id")))
    mixed = mixed or start.get("source_identity_matched") is False or end.get("source_identity_matched") is False
    mixed = mixed or any(_text(source.get("provenance_status")) in {"mixed", "mixed_or_unavailable"} for source in (start, end, root))
    task_id, run_id = run_ref.split("/", 1)
    workflow_input = _map(run_json.get("workflow_input"))
    return {"run_ref": run_ref, "task_id": task_id, "run_id": run_id, "status": _text(run_json.get("status")), "terminal": _text(run_json.get("terminal")), "completed_at": _text(run_json.get("completed_at")) or _text(run_json.get("updated_at")), "workflow_identity": workflow_id, "surface_manifest_id": surface, "topology_id": topology, "parameter_digest": val("parameter_digest", "workflow_parameter_digest"), "configuration_digest": val("configuration_digest", "config_digest"), "provider_policy_identity": val("provider_policy_identity", "provider_policy_id"), "case_identity": val("case_identity", "case_id", "case_mix_digest") or _text(workflow_input.get("case_id")) or _text(run_json.get("evaluation_case_id")), "provenance_state": "mixed" if mixed else ("known" if surface and topology else "unknown")}


def _attempts(events: Sequence[Mapping[str, Any]]) -> tuple[UsageAttempt, ...]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for i, event in enumerate(events):
        fallback = f"legacy:{_text(event.get('phase')) or _text(event.get('turn_kind')) or 'unknown'}:{_positive(event.get('attempt')) or 1}"
        groups[_text(event.get("dispatch_id")) or _text(event.get("provider_attempt_id")) or fallback].append(event)
    result = []
    for dispatch_id, life in sorted(groups.items()):
        final, first = next((e for e in reversed(life) if str(e.get("event_type", "")).endswith(("finished", "failed"))), life[-1]), life[0]
        usage = _map(final.get("token_usage")) or _map(final.get("usage"))
        availability, source, total, inp, out = _usage_values(usage)
        result.append(UsageAttempt(dispatch_id=dispatch_id, phase=_text(final.get("phase")) or _text(first.get("phase")) or "unknown", attempt=_positive(final.get("attempt")) or _positive(first.get("attempt")), provider=_text(final.get("provider")) or _text(first.get("provider")), model=_text(final.get("model")) or _text(first.get("model")), effort=_text(final.get("effort")) or _text(first.get("effort")), outcome=_text(final.get("outcome")), availability=availability, total_source=source, input_tokens=inp, output_tokens=out, total_tokens=total, cached_input_tokens=_nn(usage.get("cached_input_tokens")), reasoning_tokens=_nn(usage.get("reasoning_tokens")), elapsed_seconds=_elapsed(final)))
    return tuple(result)


def _legacy_attempts(record: Mapping[str, Any]) -> tuple[UsageAttempt, ...]:
    usage = _map(record.get("provider_usage")); result = []
    phases = [(k, v) for k, v in usage.items() if isinstance(v, Mapping)]
    for phase, value in phases or ([('legacy', usage)] if usage else []):
        availability, source, total, inp, out = _usage_values(value)
        result.append(UsageAttempt(dispatch_id=f"legacy:{record.get('sequence')}:{phase}", phase=str(phase), availability=availability, total_source=source, input_tokens=inp, output_tokens=out, total_tokens=total, cached_input_tokens=_nn(value.get("cached_input_tokens")), reasoning_tokens=_nn(value.get("reasoning_tokens"))))
    present = {str(phase) for phase, _ in phases}
    for phase, field in (("producer", "producer_attempted"), ("verifier", "verifier_attempted")):
        if record.get(field) is True and phase not in present:
            result.append(UsageAttempt(dispatch_id=f"legacy:{record.get('sequence')}:{phase}", phase=phase, availability="unknown", total_source="unavailable"))
    if not result and record.get("provider_attempted") is True:
        result.append(UsageAttempt(dispatch_id=f"legacy:{record.get('sequence')}:unknown", phase="legacy", availability="unknown", total_source="unavailable"))
    return tuple(result)


def _copy_raw(run_dir: Path, destination: Path, run_ref: str, role: str, value: Any, remaining: int, cache):
    if not isinstance(value, Mapping): return RawEvidenceReference(role=role, source_path=_text(value), verification="missing_metadata"), 0, 0
    path, digest, size = _text(value.get("path")), _text(value.get("sha256")), _nn(value.get("bytes")); base = {"role": role, "source_path": path, "recorded_sha256": digest, "recorded_bytes": size}
    if path is None or digest is None or size is None: return RawEvidenceReference(**base, verification="missing_metadata"), 0, 0
    relative = PurePosixPath(path)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts: return RawEvidenceReference(**base, verification="invalid_path"), 0, 0
    source = run_dir.joinpath(*relative.parts)
    try: resolved = source.resolve(strict=True)
    except FileNotFoundError: return RawEvidenceReference(**base, verification="missing"), 0, 0
    try: resolved.relative_to(run_dir)
    except ValueError: return RawEvidenceReference(**base, verification="symlink_escape"), 0, 0
    if source.is_symlink() or not resolved.is_file(): return RawEvidenceReference(**base, verification="not_regular"), 0, 0
    if resolved.stat().st_size != size: return RawEvidenceReference(**base, verification="byte_count_mismatch"), 0, 0
    if size > remaining: return RawEvidenceReference(**base, verification="budget_omitted"), 0, size
    actual = _sha(resolved)
    if actual != digest: return RawEvidenceReference(**base, verification="digest_mismatch"), 0, 0
    key = (resolved, actual, size)
    if key in cache: rel, saved_digest, saved_size = cache[key]; return RawEvidenceReference(**base, verification="verified", snapshot_path=rel, snapshot_sha256=saved_digest, snapshot_bytes=saved_size), 0, 0
    target = destination / "raw" / sha256(run_ref.encode()).hexdigest()[:16] / f"{actual}{Path(relative.name).suffix}"
    target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(resolved, target)
    if _sha(target) != actual: target.unlink(missing_ok=True); raise OSError("copied raw evidence failed digest verification")
    rel = target.relative_to(destination).as_posix(); cache[key] = (rel, actual, size)
    return RawEvidenceReference(**base, verification="verified", snapshot_path=rel, snapshot_sha256=actual, snapshot_bytes=size), size, 0


def _raw_order(captured: Sequence[_Captured]):
    values = [(item, draft) for item in captured for draft in item.drafts]
    focus: dict[str, list[int]] = defaultdict(list)
    for _, draft in values:
        o = draft.observation
        if o["focused"] and o["lane_id"]: focus[o["lane_id"]].append(o["sequence"])
    def key(pair):
        o = pair[1].observation
        if o["focused"]: tier, distance = 0, 0
        elif o["lane_id"] in focus: tier, distance = 1, min(abs(o["sequence"] - s) for s in focus[o["lane_id"]])
        else: tier, distance = 2, 0
        return tier, distance, o["run_ref"], o["sequence"], o["observation_id"]
    return sorted(values, key=key)


def _usage_values(usage):
    inp, out, total = _nn(usage.get("input_tokens")), _nn(usage.get("output_tokens")), _nn(usage.get("total_tokens"))
    if total is not None: return "known_total", "reported", total, inp, out
    if inp is not None and out is not None: return "known_total", "derived", inp + out, inp, out
    if inp is not None or out is not None or _nn(usage.get("cached_input_tokens")) is not None or _nn(usage.get("reasoning_tokens")) is not None: return "partial", "unavailable", None, inp, out
    return "unknown", "unavailable", None, None, None


def _usage(attempts):
    if not attempts: return "not_attempted", 0
    total = sum(a.total_tokens or 0 for a in attempts if a.availability == "known_total")
    if all(a.availability == "known_total" for a in attempts): return "known_total", total
    if any(a.availability in {"known_total", "partial"} for a in attempts): return "partial", total
    return "unknown", 0


def _events(events, record, identity, sequence):
    matched = [e for e in events if _text(e.get("step_execution_id")) == identity]
    return matched or [e for e in events if e.get("sequence") == sequence and e.get("step_name") == record.get("step_name")]


def _failure(record, route):
    if _text(record.get("runtime_control")) == "fail": return True
    semantics = (_text(record.get("route_semantics")) or _text(record.get("outcome_semantics")) or "").lower()
    if semantics in {"failure", "failed", "blocked", "rejection", "rework"}: return True
    return bool(route and (route_is_rework(route) or route.lower() in {"failed", "failure", "blocked"}))


def _legacy_sequential(graph):
    if not graph or not isinstance(graph.get("steps"), list) or not graph["steps"]: return False
    ambiguous = {"worklist", "parallel", "branch", "branch_group", "map"}
    return not any(isinstance(s, Mapping) and (str(s.get("kind", "")).lower() in ambiguous or any(k in s for k in ("scope", "worklist", "branches", "group_kind"))) for s in graph["steps"])


def _target(graph, step, route):
    if not graph or not route: return None
    target = _text(_map(_map(_map(graph.get("transitions")).get("steps")).get(step)).get(route))
    return None if target in {"FINISH", "FAIL", "AWAIT_INPUT"} else target


def _normalized_topology(graph):
    steps = [{k: s[k] for k in sorted(s) if k not in {"created_at", "updated_at", "path", "root"}} for s in graph.get("steps", []) if isinstance(s, Mapping)]
    return {"steps": sorted(steps, key=lambda s: str(s.get("name", ""))), "transitions": graph.get("transitions", {})}


def _route(record):
    for key in ("final_route", "candidate_route", "route"):
        if _text(record.get(key)): return _text(record.get(key))
    for key in ("outcome", "event"):
        if _text(_map(record.get(key)).get("tag")): return _text(_map(record.get(key)).get("tag"))
    control = _text(record.get("runtime_control")); return f"runtime_control:{control}" if control else None


def _outcome(record):
    value = record.get("outcome"); return _text(_map(value).get("tag")) if isinstance(value, Mapping) else _text(value)


def _elapsed(record):
    value = record.get("elapsed_seconds")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0: return float(value)
    value = record.get("elapsed_ms")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0: return float(value) / 1000
    start, end = _text(record.get("started_at")), _text(record.get("ended_at"))
    if start and end:
        try: return max(0.0, (datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds())
        except ValueError: pass
    return None


def _snapshot_digest(payload): copy = dict(payload); copy.pop("snapshot_id", None); return "evidence-" + _hash(copy)
def _hash(value): return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
def _read_json(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError(f"{path.name} must contain a JSON object")
    return value
def _read_jsonl(path):
    result = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip(): continue
        value = json.loads(line)
        if not isinstance(value, dict): raise ValueError(f"{path.name}:{number} must contain a JSON object")
        result.append(value)
    return result
def _watermark(path): s = path.stat(); return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns
def _sha(path):
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024): digest.update(chunk)
    return digest.hexdigest()
def _path_run_ref(run_dir): return f"{run_dir.parent.parent.parent.name}/{run_dir.name}"
def _map(value): return value if isinstance(value, Mapping) else {}
def _text(value): return value if isinstance(value, str) and value else None
def _required_text(value, field):
    result = _text(value)
    if result is None: raise ValueError(f"{field} entries must be non-empty strings")
    return result
def _nn(value): return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
def _positive(value): return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
def _first(source, names): return next((_text(source.get(name)) for name in names if _text(source.get(name))), None)
def _error_detail(exc):
    if isinstance(exc, json.JSONDecodeError): return f"JSONDecodeError at line {exc.lineno}, column {exc.colno}"
    if isinstance(exc, ValueError): return str(exc)
    return type(exc).__name__


__all__ = ["DEFAULT_MAX_EVIDENCE_BYTES", "EVIDENCE_SNAPSHOT_SCHEMA", "EvidenceBudget", "EvidenceGroup", "EvidenceIssue", "EvidenceSnapshot", "ExcludedRun", "Observation", "RawEvidenceReference", "ResourceBreakdown", "RunEvidence", "SelectionPolicy", "StepMetric", "StepRanking", "UsageAttempt", "capture_evidence_snapshot", "read_evidence_snapshot", "write_evidence_snapshot"]
