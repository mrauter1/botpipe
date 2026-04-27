"""Deterministic optimizer helpers for run-trace ingestion and publication seams."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..core.workflow_capabilities import inspect_workflow_reference, selected_workflow_authoring_surface_payload
    from ..runtime.loader import resolve_workflow_reference
    from ..runtime.workspace import list_run_records
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from core.workflow_capabilities import inspect_workflow_reference, selected_workflow_authoring_surface_payload
    from runtime.loader import resolve_workflow_reference
    from runtime.workspace import list_run_records

from .lifecycle import write_workflow_json
from .validation import require_non_empty_string, require_positive_int, require_string_list

TRACE_CORPUS_SCHEMA = "autoloop.workflow_optimization.trace_corpus/v1"
SOURCE_MANIFEST_SCHEMA = "autoloop.workflow_optimization.source_manifest/v1"
EXCLUDED_RUN_REPORT_SCHEMA = "autoloop.workflow_optimization.excluded_run_report/v1"
REFINEMENT_EVIDENCE_SCHEMA = "autoloop.workflow_refinement_evidence/v1"
STEP_TRACE_METRICS_SCHEMA = "autoloop.workflow_optimization.step_trace_metrics/v1"
STEP_PRIORITY_REPORT_SCHEMA = "autoloop.workflow_optimization.step_priority_report/v1"
FAILURE_SCENARIO_SEEDS_SCHEMA = "autoloop.workflow_optimization.failure_scenario_seeds/v1"

_ELIGIBLE_STATUS_LABELS = frozenset({"failed", "paused", "blocked"})
_PROMPT_SURFACE_SUFFIXES = ("_producer.md", "_verifier.md", ".md")


@dataclass(frozen=True, slots=True)
class RunObservabilityBundle:
    """Loaded runtime-owned observability files for one run directory."""

    run_dir: Path
    task_id: str
    run_id: str
    run_ref: str
    expected_workflow_name: str
    run_json_path: Path
    trace_jsonl_path: Path
    git_tracking_jsonl_path: Path
    static_step_graph_path: Path
    raw_dir: Path
    run_json: dict[str, Any] | None = None
    trace_records: tuple[dict[str, Any], ...] | None = None
    git_tracking_records: tuple[dict[str, Any], ...] | None = None
    static_step_graph: dict[str, Any] | None = None
    load_error: str | None = None


def parse_run_ref(run_ref: str) -> tuple[str, str]:
    """Return ``(task_id, run_id)`` from ``<task_id>/<run_id>``."""

    normalized = require_non_empty_string(run_ref, error_message="run_refs entries must be non-empty strings")
    if normalized.count("/") != 1:
        raise ValueError("run_refs entries must contain exactly one '/' separator")
    task_id, run_id = normalized.split("/", 1)
    if not task_id or not run_id:
        raise ValueError("run_refs entries must contain non-empty task_id and run_id components")
    return task_id, run_id


def list_selected_workflow_runs(
    root: Path,
    selected_workflow: str,
    *,
    run_refs: Sequence[str],
    run_statuses: Sequence[str],
    history_limit: int,
) -> list[Path]:
    """Return selected run directories for one workflow."""

    repo_root = root.resolve()
    workflow_name = require_non_empty_string(selected_workflow, error_message="selected_workflow must be non-empty")
    require_positive_int(history_limit, field_name="history_limit", error_message="history_limit must be positive")

    if run_refs:
        seen: set[str] = set()
        selected_paths: list[Path] = []
        for raw_ref in run_refs:
            task_id, run_id = parse_run_ref(raw_ref)
            run_ref = f"{task_id}/{run_id}"
            if run_ref in seen:
                raise ValueError("run_refs entries must be unique")
            seen.add(run_ref)
            run_dir = repo_root / ".autoloop" / "tasks" / task_id / f"wf_{workflow_name}" / "runs" / run_id
            if not run_dir.is_dir():
                raise FileNotFoundError(f"run_ref does not resolve to an existing run directory: {run_ref}")
            selected_paths.append(run_dir)
        return selected_paths

    normalized_statuses = require_string_list(
        list(run_statuses),
        field_name="run_statuses",
        error_message="run_statuses must be a list of non-empty strings",
        dedupe=True,
        sort_output=False,
    )
    records = list_run_records(repo_root, workflow_name=workflow_name)
    allowed_statuses = set(normalized_statuses)
    selected = [
        record.run_dir
        for record in records
        if record.status is not None and record.status in allowed_statuses
    ]
    return selected[:history_limit]


def load_run_observability_bundle(run_dir: Path) -> RunObservabilityBundle:
    """Load one run's observability bundle without mutating runtime state."""

    resolved_run_dir = run_dir.resolve()
    workflow_dir = resolved_run_dir.parent.parent
    workflow_name = workflow_dir.name[3:] if workflow_dir.name.startswith("wf_") else workflow_dir.name
    task_dir = workflow_dir.parent
    task_id = task_dir.name
    run_id = resolved_run_dir.name
    run_json_path = resolved_run_dir / "run.json"
    trace_jsonl_path = resolved_run_dir / "trace.jsonl"
    git_tracking_jsonl_path = resolved_run_dir / "git_tracking.jsonl"
    static_step_graph_path = resolved_run_dir / "static_step_graph.json"
    raw_dir = resolved_run_dir / "raw"

    try:
        run_json = _read_json_object(run_json_path) if run_json_path.is_file() else None
        trace_records = _read_jsonl_objects(trace_jsonl_path) if trace_jsonl_path.is_file() else None
        git_tracking_records = (
            _read_jsonl_objects(git_tracking_jsonl_path) if git_tracking_jsonl_path.is_file() else None
        )
        static_step_graph = _read_json_object(static_step_graph_path) if static_step_graph_path.is_file() else None
        load_error = None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        run_json = None
        trace_records = None
        git_tracking_records = None
        static_step_graph = None
        load_error = str(exc)

    return RunObservabilityBundle(
        run_dir=resolved_run_dir,
        task_id=task_id,
        run_id=run_id,
        run_ref=f"{task_id}/{run_id}",
        expected_workflow_name=workflow_name,
        run_json_path=run_json_path,
        trace_jsonl_path=trace_jsonl_path,
        git_tracking_jsonl_path=git_tracking_jsonl_path,
        static_step_graph_path=static_step_graph_path,
        raw_dir=raw_dir,
        run_json=run_json,
        trace_records=None if trace_records is None else tuple(trace_records),
        git_tracking_records=None if git_tracking_records is None else tuple(git_tracking_records),
        static_step_graph=static_step_graph,
        load_error=load_error,
    )


def validate_observability_bundle(bundle: RunObservabilityBundle) -> tuple[bool, str | None]:
    """Validate Plan-1 observability presence and basic workflow identity alignment."""

    if not bundle.run_json_path.is_file():
        return False, "missing_run_json"
    if not bundle.trace_jsonl_path.is_file():
        return False, "missing_trace_jsonl"
    if not bundle.git_tracking_jsonl_path.is_file():
        return False, "missing_git_tracking_jsonl"
    if not bundle.static_step_graph_path.is_file():
        return False, "missing_static_step_graph"
    if not bundle.raw_dir.is_dir():
        return False, "missing_raw_dir"
    if bundle.load_error is not None:
        if "decode" in bundle.load_error.lower() or "json" in bundle.load_error.lower():
            return False, "malformed_observability_files"
        return False, "unreadable_observability_files"
    if not isinstance(bundle.run_json, dict):
        return False, "malformed_observability_files"
    workflow_name = bundle.run_json.get("workflow_name")
    if isinstance(workflow_name, str) and workflow_name and workflow_name != bundle.expected_workflow_name:
        return False, "wrong_selected_workflow"
    return True, None


def normalize_trace_corpus(
    *,
    selected_workflow: str,
    run_dirs: Sequence[Path],
    route_tags: Sequence[str],
) -> dict[str, Any]:
    """Normalize selected run bundles into one optimization-ready trace corpus."""

    workflow_name = require_non_empty_string(
        selected_workflow,
        error_message="selected_workflow must be non-empty",
    )
    route_filter = set(
        require_string_list(
            list(route_tags),
            field_name="route_tags",
            error_message="route_tags must be a list of non-empty strings",
            dedupe=True,
            sort_output=False,
        )
    )
    bundle_records: list[RunObservabilityBundle] = [load_run_observability_bundle(path) for path in run_dirs]

    excluded_runs: list[dict[str, str]] = []
    runs: list[dict[str, Any]] = []
    step_observations: list[dict[str, Any]] = []

    for bundle in bundle_records:
        valid, reason = validate_observability_bundle(bundle)
        if not valid:
            excluded_runs.append(
                {
                    "task_id": bundle.task_id,
                    "run_id": bundle.run_id,
                    "run_ref": bundle.run_ref,
                    "reason": reason or "unreadable_observability_files",
                }
            )
            continue
        assert bundle.run_json is not None
        assert bundle.trace_records is not None
        assert bundle.git_tracking_records is not None
        assert bundle.static_step_graph is not None

        git_index = _git_tracking_index(bundle.git_tracking_records)
        run_git = _require_mapping_or_empty(bundle.run_json.get("git_tracking"))
        run_entry = {
            "run_ref": bundle.run_ref,
            "run_id": bundle.run_id,
            "task_id": bundle.task_id,
            "workflow": workflow_name,
            "run_dir": _repo_relative_if_possible(bundle.run_dir, bundle.run_dir.parents[5]),
            "run_json_path": str(bundle.run_json_path),
            "trace_jsonl_path": str(bundle.trace_jsonl_path),
            "git_tracking_jsonl_path": str(bundle.git_tracking_jsonl_path),
            "static_step_graph_path": str(bundle.static_step_graph_path),
            "terminal": _optional_text(bundle.run_json.get("terminal")),
            "status": _optional_text(bundle.run_json.get("status")),
            "commit_before_run": _optional_text(run_git.get("commit_before_run")),
            "commit_after_run": _optional_text(run_git.get("commit_after_run")),
            "eligible_for_optimization": True,
        }
        runs.append(run_entry)

        filtered_step_events = [
            record
            for record in bundle.trace_records
            if record.get("event_type") == "step_finished"
            and isinstance(record.get("step_name"), str)
            and isinstance(record.get("sequence"), int)
        ]
        for index, record in enumerate(filtered_step_events):
            sequence = int(record["sequence"])
            step_name = str(record["step_name"])
            route = _extract_route_tag(record)
            if route_filter and route not in route_filter:
                continue
            raw_output_refs = _normalize_raw_output_refs(record.get("raw_output_refs"))
            provider_usage = _normalize_provider_usage(record.get("provider_usage"))
            git_step = git_index.get(sequence, {})
            local_outcome = _local_outcome_from_route(route)
            downstream_outcome = _downstream_outcome(filtered_step_events[index + 1 :], run_entry["terminal"])
            step_observations.append(
                {
                    "observation_id": f"{bundle.run_ref}:{sequence:06d}:{step_name}",
                    "run_ref": bundle.run_ref,
                    "run_id": bundle.run_id,
                    "task_id": bundle.task_id,
                    "sequence": sequence,
                    "step_name": step_name,
                    "step_kind": _optional_text(record.get("step_kind")) or "unknown",
                    "route": route,
                    "raw_output_refs": raw_output_refs,
                    "usage": provider_usage,
                    "commit_before_step": _optional_text(git_step.get("commit_before_step"))
                    or _optional_text(_require_mapping_or_empty(record.get("git")).get("commit_before_step")),
                    "commit_after_step": _optional_text(git_step.get("commit_after_step")),
                    "local_outcome": local_outcome,
                    "downstream_outcome": downstream_outcome,
                }
            )

    return {
        "schema": TRACE_CORPUS_SCHEMA,
        "selected_workflow": workflow_name,
        "candidate_run_count": len(run_dirs),
        "eligible_run_count": len(runs),
        "excluded_run_count": len(excluded_runs),
        "excluded_run_report_path": "excluded_run_report.json",
        "step_observation_count": len(step_observations),
        "runs": runs,
        "step_observations": step_observations,
        "excluded_runs": excluded_runs,
        "static_step_graphs": [
            bundle.static_step_graph
            for bundle in bundle_records
            if validate_observability_bundle(bundle)[0] and isinstance(bundle.static_step_graph, dict)
        ],
    }


def resolve_selected_workflow_name(root: Path, selected_workflow: str) -> str:
    """Resolve one selected-workflow reference to its canonical workflow name."""

    repo_root = root.resolve()
    workflow_reference = require_non_empty_string(
        selected_workflow,
        error_message="selected_workflow must be non-empty",
    )
    capability = inspect_workflow_reference(repo_root, workflow_reference)
    return capability.workflow_name


def build_step_trace_metrics(
    trace_corpus: Mapping[str, Any],
    static_step_graphs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build deterministic step metrics for optimization ranking."""

    selected_workflow = require_non_empty_string(
        trace_corpus.get("selected_workflow"),
        error_message="trace_corpus.selected_workflow must be non-empty",
    )
    observations = _require_mapping_list(
        trace_corpus.get("step_observations"),
        "trace_corpus.step_observations must be a list of objects",
    )
    total_tokens = 0
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in observations:
        step_name = require_non_empty_string(
            observation.get("step_name"),
            error_message="step observations must define step_name",
        )
        grouped[step_name].append(observation)
        usage = _require_mapping_or_empty(observation.get("usage"))
        total_tokens += int(usage.get("total_tokens") or 0)

    centrality_by_step: dict[str, list[float]] = defaultdict(list)
    for graph in static_step_graphs:
        for step_name, score in compute_static_step_centrality(graph).items():
            centrality_by_step[step_name].append(score)

    step_entries: list[dict[str, Any]] = []
    for step_name, step_observations in grouped.items():
        route_counts = Counter(
            _optional_text(observation.get("route")) or "unknown" for observation in step_observations
        )
        observed_count = len(step_observations)
        estimated_token_total = sum(int(_require_mapping_or_empty(obs.get("usage")).get("total_tokens") or 0) for obs in step_observations)
        token_share = 0.0 if total_tokens <= 0 else round(estimated_token_total / total_tokens, 4)
        centrality_values = centrality_by_step.get(step_name, [])
        artifact_centrality = round(sum(centrality_values) / len(centrality_values), 4) if centrality_values else 0.0
        route_criticality = round(
            min(
                1.0,
                (
                    route_counts.get("failed", 0)
                    + route_counts.get("blocked", 0)
                    + route_counts.get("needs_rework", 0)
                    + route_counts.get("needs_replan", 0)
                )
                / max(1, observed_count),
            ),
            4,
        )
        step_entries.append(
            {
                "step_name": step_name,
                "step_kind": _optional_text(step_observations[0].get("step_kind")) or "unknown",
                "observed_count": observed_count,
                "route_counts": dict(sorted(route_counts.items())),
                "producer_failed_verifier_count": route_counts.get("needs_rework", 0),
                "blocked_count": route_counts.get("blocked", 0),
                "failed_count": route_counts.get("failed", 0),
                "needs_rework_count": route_counts.get("needs_rework", 0),
                "needs_replan_count": route_counts.get("needs_replan", 0),
                "estimated_token_total": estimated_token_total,
                "token_share": token_share,
                "downstream_failure_after_pass_count": sum(
                    1 for obs in step_observations if _optional_text(obs.get("downstream_outcome")) == "terminal_failure_after_local_pass"
                ),
                "artifact_centrality": artifact_centrality,
                "route_criticality": route_criticality,
            }
        )

    step_entries.sort(key=lambda entry: (-entry["observed_count"], entry["step_name"]))
    return {
        "schema": STEP_TRACE_METRICS_SCHEMA,
        "selected_workflow": selected_workflow,
        "steps": step_entries,
    }


def compute_static_step_centrality(
    static_step_graph: Mapping[str, Any],
) -> dict[str, float]:
    """Compute simple degree centrality from one static workflow graph."""

    steps = _require_mapping_list(
        static_step_graph.get("steps"),
        "static_step_graph.steps must be a list of objects",
    )
    transitions = _require_mapping_or_empty(static_step_graph.get("transitions"))
    step_routes = _require_mapping_or_empty(transitions.get("steps"))
    counts: Counter[str] = Counter()
    for step in steps:
        name = _optional_text(step.get("name"))
        if name:
            counts[name] += 0
    for source, routes in step_routes.items():
        if isinstance(source, str):
            counts[source] += 0
        if not isinstance(routes, Mapping):
            continue
        counts[str(source)] += len(routes)
        for target in routes.values():
            if isinstance(target, str) and target not in {"SUCCESS", "PAUSE", "FAIL"}:
                counts[target] += 1
    max_count = max(counts.values(), default=0)
    if max_count <= 0:
        return {name: 0.0 for name in counts}
    return {name: round(value / max_count, 4) for name, value in counts.items()}


def rank_optimization_targets(
    *,
    step_metrics: Mapping[str, Any],
    static_centrality: Mapping[str, float],
    top_k: int,
) -> dict[str, Any]:
    """Rank highest-leverage optimization targets with a deterministic score."""

    require_positive_int(top_k, field_name="top_k", error_message="top_k must be positive")
    selected_workflow = require_non_empty_string(
        step_metrics.get("selected_workflow"),
        error_message="step_metrics.selected_workflow must be non-empty",
    )
    steps = _require_mapping_list(step_metrics.get("steps"), "step_metrics.steps must be a list of objects")

    ranked_entries: list[dict[str, Any]] = []
    for step in steps:
        step_name = require_non_empty_string(step.get("step_name"), error_message="step metrics must define step_name")
        observed_count = int(step.get("observed_count") or 0)
        failed_count = int(step.get("failed_count") or 0)
        blocked_count = int(step.get("blocked_count") or 0)
        needs_rework_count = int(step.get("needs_rework_count") or 0)
        downstream_failures = int(step.get("downstream_failure_after_pass_count") or 0)
        token_share = float(step.get("token_share") or 0.0)
        route_criticality = float(step.get("route_criticality") or 0.0)
        artifact_centrality = float(step.get("artifact_centrality") or static_centrality.get(step_name, 0.0))

        direct_failure_rate = min(1.0, (failed_count + blocked_count + needs_rework_count) / max(1, observed_count))
        downstream_blast_radius = min(1.0, downstream_failures / max(1, observed_count))
        rework_loop_cost = min(1.0, needs_rework_count / max(1, observed_count))
        sample_support = min(1.0, observed_count / 5.0)
        score = (
            0.25 * direct_failure_rate
            + 0.20 * downstream_blast_radius
            + 0.15 * rework_loop_cost
            + 0.15 * artifact_centrality
            + 0.10 * route_criticality
            + 0.10 * token_share
            + 0.05 * sample_support
        )
        if observed_count < 2:
            score -= 0.10
        if token_share <= 0.0:
            score -= 0.05
        if not _has_prompt_surface(step_name):
            score -= 0.05
        if failed_count == 0 and downstream_failures > 0:
            score -= 0.05
        evidence_strength = "high" if observed_count >= 5 else "medium" if observed_count >= 2 else "low"
        ranked_entries.append(
            {
                "step_name": step_name,
                "priority_score": round(max(0.0, min(1.0, score)), 4),
                "confidence": round(min(1.0, 0.45 + 0.1 * observed_count), 4),
                "evidence_strength": evidence_strength,
                "recommended_first_pass": _recommended_first_pass(step),
                "secondary_passes": _secondary_passes(step),
                "why_high_leverage": _why_high_leverage(step),
                "likely_failure_surfaces": _likely_failure_surfaces(step),
            }
        )

    ranked_entries.sort(key=lambda entry: (-entry["priority_score"], entry["step_name"]))
    top_ranked = ranked_entries[:top_k]
    for index, entry in enumerate(top_ranked, start=1):
        entry["rank"] = index
    not_selected = [
        {
            "step_name": entry["step_name"],
            "reason": "Lower deterministic leverage score than the selected target set.",
        }
        for entry in ranked_entries[top_k:]
    ]
    return {
        "schema": STEP_PRIORITY_REPORT_SCHEMA,
        "selected_workflow": selected_workflow,
        "ranking_method": "static_graph_plus_trace_metrics_plus_llm_attribution",
        "top_k_steps": top_k,
        "ranked_steps": top_ranked,
        "not_selected": not_selected,
    }


def extract_failure_scenario_seeds(
    *,
    trace_corpus: Mapping[str, Any],
    priority_report: Mapping[str, Any],
    max_scenarios: int,
) -> dict[str, Any]:
    """Extract deterministic failure-scenario seeds for later LLM diagnosis."""

    require_positive_int(
        max_scenarios,
        field_name="max_failure_scenarios",
        error_message="max_failure_scenarios must be positive",
    )
    selected_workflow = require_non_empty_string(
        trace_corpus.get("selected_workflow"),
        error_message="trace_corpus.selected_workflow must be non-empty",
    )
    observations = _require_mapping_list(
        trace_corpus.get("step_observations"),
        "trace_corpus.step_observations must be a list of objects",
    )
    ranked_steps = {
        require_non_empty_string(entry.get("step_name"), error_message="priority report ranked steps need step_name")
        for entry in _require_mapping_list(priority_report.get("ranked_steps"), "priority_report.ranked_steps must be a list of objects")
    }

    seeds: list[dict[str, Any]] = []
    for observation in observations:
        step_name = _optional_text(observation.get("step_name"))
        if step_name not in ranked_steps:
            continue
        route = _optional_text(observation.get("route")) or "unknown"
        total_tokens = int(_require_mapping_or_empty(observation.get("usage")).get("total_tokens") or 0)
        reasons: list[str] = []
        if route in {"needs_rework", "needs_replan", "blocked", "failed"}:
            reasons.append(f"route:{route}")
        if total_tokens >= 1500 and route not in {"ready", "success"}:
            reasons.append("high_token_usage_without_success")
        if not _require_mapping_or_empty(observation.get("raw_output_refs")):
            reasons.append("missing_raw_output_reference")
        if not _require_mapping_or_empty(observation.get("usage")):
            reasons.append("missing_usage_data")
        if _optional_text(observation.get("downstream_outcome")) == "terminal_failure_after_local_pass":
            reasons.append("terminal_failure_after_local_pass")
        if not reasons:
            continue
        seeds.append(
            {
                "observation_id": _optional_text(observation.get("observation_id")),
                "step_name": step_name,
                "route": route,
                "seed_reasons": reasons,
            }
        )
        if len(seeds) >= max_scenarios:
            break

    return {
        "schema": FAILURE_SCENARIO_SEEDS_SCHEMA,
        "selected_workflow": selected_workflow,
        "failure_scenario_seeds": seeds,
    }


def write_selected_workflow_source_manifest(
    *,
    ctx,
    selected_workflow: str,
    relative_path: str,
) -> Path:
    """Write a stable source-surface manifest for one selected workflow."""

    repo_root = ctx.root.resolve()
    capability = inspect_workflow_reference(repo_root, selected_workflow)
    surface = selected_workflow_authoring_surface_payload(capability)
    editable_paths = [
        Path(path).resolve()
        for path in require_string_list(
            surface.get("editable_paths"),
            error_message="selected workflow authoring surface must define editable_paths",
            field_name="editable_paths",
            dedupe=True,
            sort_output=True,
        )
    ]
    package_dir = Path(surface["package_dir"]).resolve()
    files: list[dict[str, object]] = []
    for path in editable_paths:
        if not path.is_file():
            continue
        payload = path.read_bytes()
        files.append(
            {
                "path": _repo_relative_if_possible(path, repo_root),
                "sha256": sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        )
    manifest = {
        "schema": SOURCE_MANIFEST_SCHEMA,
        "selected_workflow": capability.workflow_name,
        "package_dir": _repo_relative_if_possible(package_dir, repo_root),
        "files": sorted(files, key=lambda entry: str(entry["path"])),
    }
    return write_workflow_json(ctx, relative_path, manifest)


def validate_selected_workflow_source_unchanged(
    *,
    ctx,
    selected_workflow: str,
    manifest_path: Path,
) -> tuple[bool, str]:
    """Recompute and compare the selected workflow source manifest."""

    current_manifest_path = write_selected_workflow_source_manifest(
        ctx=ctx,
        selected_workflow=selected_workflow,
        relative_path="_source_manifest_validation.json",
    )
    recorded = _read_json_object(manifest_path)
    current = _read_json_object(current_manifest_path)
    try:
        current_manifest_path.unlink()
    except FileNotFoundError:  # pragma: no cover - defensive cleanup
        pass

    if recorded == current:
        return True, "Selected workflow source manifest unchanged."
    return False, "Selected workflow source manifest changed during optimization publication."


def write_optimization_refinement_evidence(
    *,
    ctx,
    selected_workflow: str,
    evidence_entries: Sequence[Mapping[str, Any]],
) -> Path:
    """Write optimization evidence in the shared refinement-evidence envelope."""

    payload = {
        "schema": REFINEMENT_EVIDENCE_SCHEMA,
        "source_path": None,
        "target_workflow_id": require_non_empty_string(
            selected_workflow,
            error_message="selected_workflow must be non-empty",
        ),
        "evidence_entries": [dict(entry) for entry in evidence_entries],
    }
    return write_workflow_json(ctx, "workflow_refinement_evidence.json", payload)


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must decode to a JSON object")
    return payload


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path} line {index} must decode to a JSON object")
        entries.append(payload)
    return entries


def _git_tracking_index(records: Sequence[Mapping[str, Any]]) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for record in records:
        sequence = record.get("sequence")
        if isinstance(sequence, int):
            indexed[sequence] = dict(record)
    return indexed


def _normalize_raw_output_refs(value: Any) -> dict[str, str]:
    raw_refs = _require_mapping_or_empty(value)
    normalized: dict[str, str] = {}
    for role, payload in raw_refs.items():
        if not isinstance(role, str) or not isinstance(payload, Mapping):
            continue
        path = payload.get("path")
        if isinstance(path, str) and path:
            normalized[role] = path
    return normalized


def _normalize_provider_usage(value: Any) -> dict[str, int]:
    usage = _require_mapping_or_empty(value)
    normalized = {
        "producer_input_tokens": 0,
        "producer_output_tokens": 0,
        "verifier_input_tokens": 0,
        "verifier_output_tokens": 0,
        "total_tokens": 0,
    }
    producer = _require_mapping_or_empty(usage.get("producer"))
    verifier = _require_mapping_or_empty(usage.get("verifier"))
    llm = _require_mapping_or_empty(usage.get("llm"))
    if producer:
        normalized["producer_input_tokens"] = int(producer.get("input_tokens") or 0)
        normalized["producer_output_tokens"] = int(producer.get("output_tokens") or 0)
        normalized["total_tokens"] += int(producer.get("total_tokens") or 0)
    if verifier:
        normalized["verifier_input_tokens"] = int(verifier.get("input_tokens") or 0)
        normalized["verifier_output_tokens"] = int(verifier.get("output_tokens") or 0)
        normalized["total_tokens"] += int(verifier.get("total_tokens") or 0)
    if llm:
        normalized["producer_input_tokens"] = int(llm.get("input_tokens") or 0)
        normalized["producer_output_tokens"] = int(llm.get("output_tokens") or 0)
        normalized["total_tokens"] = int(llm.get("total_tokens") or 0)
    return normalized


def _extract_route_tag(record: Mapping[str, Any]) -> str:
    outcome = _require_mapping_or_empty(record.get("outcome"))
    event = _require_mapping_or_empty(record.get("event"))
    return _optional_text(outcome.get("tag")) or _optional_text(event.get("tag")) or "unknown"


def _local_outcome_from_route(route: str) -> str:
    if route == "needs_rework":
        return "rejected_by_verifier"
    if route == "needs_replan":
        return "requires_replan"
    if route == "blocked":
        return "blocked"
    if route == "failed":
        return "failed"
    return "locally_accepted"


def _downstream_outcome(next_records: Sequence[Mapping[str, Any]], terminal: Any) -> str:
    terminal_value = _optional_text(terminal)
    for record in next_records:
        route = _extract_route_tag(record)
        if route in {"needs_rework", "needs_replan", "blocked", "failed"}:
            return f"next_step_{route}"
    if terminal_value == "FAIL":
        return "terminal_failure_after_local_pass"
    return "unknown"


def _require_mapping_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _require_mapping_list(value: Any, error_message: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(error_message)
    normalized: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            raise ValueError(error_message)
        normalized.append({str(key): item for key, item in entry.items()})
    return normalized


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _repo_relative_if_possible(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _has_prompt_surface(step_name: str) -> bool:
    return not step_name.startswith("publish") and step_name != "bootstrap"


def _recommended_first_pass(step: Mapping[str, Any]) -> str:
    if int(step.get("needs_rework_count") or 0) > int(step.get("failed_count") or 0):
        return "verifier_rubric_local_optimization"
    if float(step.get("token_share") or 0.0) >= 0.35:
        return "token_optimization"
    return "producer_local_optimization"


def _secondary_passes(step: Mapping[str, Any]) -> list[str]:
    passes = ["producer_local_optimization", "verifier_rubric_local_optimization", "token_optimization"]
    first = _recommended_first_pass(step)
    return [candidate for candidate in passes if candidate != first]


def _why_high_leverage(step: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if int(step.get("needs_rework_count") or 0) > 0:
        reasons.append("high needs_rework loop rate")
    if float(step.get("token_share") or 0.0) >= 0.20:
        reasons.append("large token share")
    if int(step.get("downstream_failure_after_pass_count") or 0) > 0:
        reasons.append("downstream failures after local acceptance")
    if not reasons:
        reasons.append("largest deterministic leverage score among observed steps")
    return reasons


def _likely_failure_surfaces(step: Mapping[str, Any]) -> list[dict[str, object]]:
    surfaces: list[dict[str, object]] = []
    if int(step.get("needs_rework_count") or 0) > 0:
        surfaces.append(
            {
                "surface": "verifier_rubric",
                "probability": 0.48,
                "rationale": "Repeated rework loops suggest acceptance-boundary or feedback-discipline pressure.",
            }
        )
    if int(step.get("failed_count") or 0) > 0 or float(step.get("token_share") or 0.0) > 0.25:
        surfaces.append(
            {
                "surface": "producer_prompt",
                "probability": 0.34,
                "rationale": "Observed failures and prompt cost suggest upstream instruction or evidence-discipline issues.",
            }
        )
    if not surfaces:
        surfaces.append(
            {
                "surface": "insufficient_evidence",
                "probability": 0.2,
                "rationale": "Deterministic evidence is thin, so later LLM attribution should stay conservative.",
            }
        )
    return surfaces


__all__ = [
    "EXCLUDED_RUN_REPORT_SCHEMA",
    "FAILURE_SCENARIO_SEEDS_SCHEMA",
    "REFINEMENT_EVIDENCE_SCHEMA",
    "RunObservabilityBundle",
    "SOURCE_MANIFEST_SCHEMA",
    "STEP_PRIORITY_REPORT_SCHEMA",
    "STEP_TRACE_METRICS_SCHEMA",
    "TRACE_CORPUS_SCHEMA",
    "build_step_trace_metrics",
    "compute_static_step_centrality",
    "extract_failure_scenario_seeds",
    "list_selected_workflow_runs",
    "load_run_observability_bundle",
    "normalize_trace_corpus",
    "parse_run_ref",
    "rank_optimization_targets",
    "resolve_selected_workflow_name",
    "validate_observability_bundle",
    "validate_selected_workflow_source_unchanged",
    "write_optimization_refinement_evidence",
    "write_selected_workflow_source_manifest",
]
