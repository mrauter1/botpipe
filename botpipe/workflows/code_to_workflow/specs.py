"""Deterministic capture and publication helpers for code_to_workflow."""

from __future__ import annotations

import json
import re
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any


SOURCE_MANIFEST_SCHEMA = "botpipe.code_to_workflow.source_manifest/v1"
TRACE_CORPUS_SCHEMA = "botpipe.code_to_workflow.trace_corpus/v1"
PUBLICATION_RECEIPT_SCHEMA = "botpipe.code_to_workflow.publication_receipt/v1"

_DEFAULT_EXCLUDED_DIRS = {
    ".autoloop",
    ".botpipe",
    ".cache",
    ".git",
    ".hg",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
_EXCLUDED_PREFIXES = (".venv",)
_MAX_MANIFEST_FILES = 5000
_MAX_TRACE_RUNS = 25
_MAX_TRACE_EVENTS_PER_RUN = 80
_MAX_ERROR_EXCERPTS = 8
_MAX_TEXT_EXCERPT = 320
_HANDLED_COVERAGE_STATUSES = {"covered", "generated", "implemented", "validated"}


def derive_generated_workflow_name(root: Path, requested: str | None) -> str:
    """Return the explicit workflow name or a sanitized repo-derived default."""

    if requested is not None and requested.strip():
        return requested.strip()
    candidate = _sanitize_identifier(root.resolve().name)
    return candidate or "generated_workflow"


def capture_source_manifest(root: Path, *, generated_workflow_name: str) -> dict[str, Any]:
    """Return a bounded source manifest for the workspace."""

    workspace = root.resolve()
    generated_output = (workspace / ".botpipe" / "workflows" / generated_workflow_name).resolve()
    entries: list[dict[str, Any]] = []
    skipped = Counter()

    for path in sorted(workspace.rglob("*")):
        if path == generated_output or _is_relative_to(path, generated_output):
            skipped["generated_output"] += 1
            continue
        if should_exclude_source_path(path, root=workspace):
            if path.is_file():
                skipped["excluded_path"] += 1
            continue
        if not path.is_file():
            continue
        if path.is_symlink():
            skipped["symlink"] += 1
            continue
        if len(entries) >= _MAX_MANIFEST_FILES:
            skipped["max_files"] += 1
            continue
        try:
            data = path.read_bytes()
        except OSError:
            skipped["unreadable"] += 1
            continue
        relative = path.relative_to(workspace).as_posix()
        entries.append(
            {
                "path": relative,
                "size_bytes": len(data),
                "sha256": sha256(data).hexdigest(),
            }
        )

    return {
        "schema": SOURCE_MANIFEST_SCHEMA,
        "root": str(workspace),
        "generated_workflow_name": generated_workflow_name,
        "generated_output": ".botpipe/workflows/" + generated_workflow_name,
        "excluded_dirs": sorted(_DEFAULT_EXCLUDED_DIRS),
        "file_count": len(entries),
        "skipped": dict(sorted(skipped.items())),
        "files": entries,
    }


def should_exclude_source_path(path: Path, *, root: Path) -> bool:
    """Return whether a path should be excluded from source behavior capture."""

    try:
        parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return True
    for part in parts:
        if part in _DEFAULT_EXCLUDED_DIRS:
            return True
        if any(part.startswith(prefix) for prefix in _EXCLUDED_PREFIXES):
            return True
    return False


def collect_trace_corpus(root: Path, *, exclude_run_dir: Path | None = None) -> dict[str, Any]:
    """Return bounded repository-local trace evidence."""

    workspace = root.resolve()
    excluded = exclude_run_dir.resolve() if exclude_run_dir is not None else None
    botpipe_runs = _collect_botpipe_runs(workspace, excluded)
    legacy_runs = _collect_legacy_autoloop_runs(workspace)
    codex_rollouts = _collect_nested_codex_rollouts(workspace, excluded)
    return {
        "schema": TRACE_CORPUS_SCHEMA,
        "root": str(workspace),
        "limits": {
            "max_trace_runs": _MAX_TRACE_RUNS,
            "max_trace_events_per_run": _MAX_TRACE_EVENTS_PER_RUN,
            "max_error_excerpts": _MAX_ERROR_EXCERPTS,
        },
        "botpipe_runs": botpipe_runs,
        "legacy_autoloop_runs": legacy_runs,
        "codex_rollout_refs": codex_rollouts,
    }


def validate_publication_inputs(
    *,
    root: Path,
    workflow_folder: Path,
    generated_workflow_name: str,
) -> dict[str, Any]:
    """Validate generated output and coverage artifacts before publication."""

    generated_root = root.resolve() / ".botpipe" / "workflows" / generated_workflow_name
    required_paths = {
        "generated_root": generated_root,
        "generated_flow": generated_root / "flow.py",
        "generated_manifest": generated_root / "workflow.toml",
        "generated_layout": workflow_folder / "generated_layout.json",
        "validation_report": workflow_folder / "validation_report.md",
        "coverage_map": workflow_folder / "coverage_map.json",
        "behavior_inventory": workflow_folder / "behavior_inventory.json",
    }
    missing = [name for name, path in required_paths.items() if not path.exists()]
    if missing:
        raise FileNotFoundError("missing required publication artifacts: " + ", ".join(sorted(missing)))

    behavior_inventory = _read_json_object(required_paths["behavior_inventory"])
    coverage_map = _read_json_object(required_paths["coverage_map"])
    coverage_summary = validate_coverage_map(behavior_inventory=behavior_inventory, coverage_map=coverage_map)
    discovery_summary = validate_generated_workflow_discovery(
        root=root,
        generated_workflow_name=generated_workflow_name,
    )
    return {
        "schema": PUBLICATION_RECEIPT_SCHEMA,
        "published": True,
        "generated_workflow_name": generated_workflow_name,
        "generated_workflow_root": str(generated_root),
        "generated_flow": str(generated_root / "flow.py"),
        "generated_manifest": str(generated_root / "workflow.toml"),
        "generated_layout": str(required_paths["generated_layout"]),
        "validation_report": str(required_paths["validation_report"]),
        "coverage_summary": coverage_summary,
        "discovery_summary": discovery_summary,
    }


def validate_generated_workflow_discovery(*, root: Path, generated_workflow_name: str) -> dict[str, Any]:
    """Validate that Botpipe can discover and compile the generated workflow."""

    try:
        from botpipe.core.workflow_capabilities import inspect_workflow_reference

        entry = inspect_workflow_reference(root, generated_workflow_name)
    except Exception as exc:
        raise ValueError(
            f"generated workflow {generated_workflow_name!r} is not discoverable and compilable by Botpipe: {exc}"
        ) from exc

    if entry.workflow_name != generated_workflow_name:
        raise ValueError(
            f"generated workflow reference {generated_workflow_name!r} resolved to {entry.workflow_name!r}"
        )
    if not entry.steps:
        raise ValueError(f"generated workflow {generated_workflow_name!r} must define at least one step")

    return {
        "workflow_name": entry.workflow_name,
        "workflow_class": entry.workflow_class,
        "authoring_shape": str(entry.authoring_shape),
        "step_count": len(entry.steps),
        "artifact_count": len(entry.artifacts),
        "parameter_names": [field.name for field in entry.parameters],
    }


def validate_coverage_map(*, behavior_inventory: dict[str, Any], coverage_map: dict[str, Any]) -> dict[str, Any]:
    """Validate that required behavior ids are handled by the coverage map."""

    behaviors = behavior_inventory.get("behaviors")
    if not isinstance(behaviors, list) or not behaviors:
        raise ValueError("behavior_inventory.json must contain a non-empty behaviors list")
    coverage_entries = coverage_map.get("coverage")
    if not isinstance(coverage_entries, list):
        raise ValueError("coverage_map.json must contain a coverage list")

    required_behavior_ids: list[str] = []
    for behavior in behaviors:
        if not isinstance(behavior, dict):
            raise ValueError("behavior_inventory.json behaviors entries must be objects")
        behavior_id = str(behavior.get("id") or "").strip()
        if not behavior_id:
            raise ValueError("behavior_inventory.json behavior entries must include non-empty id")
        if bool(behavior.get("required", True)):
            required_behavior_ids.append(behavior_id)

    coverage_by_id: dict[str, dict[str, Any]] = {}
    for entry in coverage_entries:
        if not isinstance(entry, dict):
            raise ValueError("coverage_map.json coverage entries must be objects")
        behavior_id = str(entry.get("behavior_id") or entry.get("id") or "").strip()
        if not behavior_id:
            raise ValueError("coverage_map.json coverage entries must include behavior_id")
        coverage_by_id[behavior_id] = entry

    unhandled: list[str] = []
    unsupported: list[str] = []
    for behavior_id in required_behavior_ids:
        entry = coverage_by_id.get(behavior_id)
        if entry is None:
            unhandled.append(behavior_id)
            continue
        status = str(entry.get("status") or "").strip().lower()
        if status in {"", "todo", "missing", "unknown", "unhandled"}:
            unhandled.append(behavior_id)
            continue
        if status == "unsupported":
            reason = str(entry.get("reason") or entry.get("rationale") or "").strip()
            if not reason:
                unhandled.append(behavior_id)
            else:
                unsupported.append(behavior_id)
            continue
        if status not in _HANDLED_COVERAGE_STATUSES:
            unhandled.append(behavior_id)

    if unhandled:
        raise ValueError("coverage_map.json has unhandled required behaviors: " + ", ".join(sorted(unhandled)))
    return {
        "required_behavior_count": len(required_behavior_ids),
        "coverage_entry_count": len(coverage_entries),
        "unsupported_required_behavior_ids": sorted(unsupported),
    }


def _collect_botpipe_runs(workspace: Path, excluded: Path | None) -> list[dict[str, Any]]:
    runs_root = workspace / ".botpipe" / "tasks"
    candidates = sorted(runs_root.glob("*/wf_*/runs/*"), key=_mtime_sort_key, reverse=True)
    runs: list[dict[str, Any]] = []
    for run_dir in candidates:
        if len(runs) >= _MAX_TRACE_RUNS:
            break
        if not run_dir.is_dir():
            continue
        if excluded is not None and (run_dir.resolve() == excluded or _is_relative_to(run_dir.resolve(), excluded)):
            continue
        run_json = _try_read_json_object(run_dir / "run.json")
        trace_records = _read_jsonl_objects(run_dir / "trace.jsonl", limit=_MAX_TRACE_EVENTS_PER_RUN)
        if run_json is None and not trace_records:
            continue
        event_counts = Counter(str(record.get("event") or record.get("type") or "unknown") for record in trace_records)
        step_outcomes = [
            {
                "step": record.get("step") or record.get("step_name"),
                "event": record.get("event") or record.get("type"),
                "outcome": _outcome_tag(record),
                "target_step": record.get("target_step"),
            }
            for record in trace_records
            if record.get("step") or record.get("step_name") or _outcome_tag(record)
        ]
        runs.append(
            {
                "run_dir": _relative_or_absolute(run_dir, workspace),
                "task_id": run_dir.parents[2].name if len(run_dir.parents) >= 3 else None,
                "workflow_name": _workflow_name_from_run_dir(run_dir),
                "run_id": run_dir.name,
                "status": _json_field(run_json, "status"),
                "terminal": _json_field(run_json, "terminal"),
                "event_counts": dict(sorted(event_counts.items())),
                "step_outcomes": step_outcomes[:_MAX_TRACE_EVENTS_PER_RUN],
                "errors": _error_excerpts(trace_records),
                "raw_output_refs": _raw_output_refs(trace_records),
            }
        )
    return runs


def _collect_legacy_autoloop_runs(workspace: Path) -> list[dict[str, Any]]:
    runs_root = workspace / ".autoloop" / "tasks"
    candidates = sorted(runs_root.glob("*/runs/*"), key=_mtime_sort_key, reverse=True)
    runs: list[dict[str, Any]] = []
    for run_dir in candidates[:_MAX_TRACE_RUNS]:
        events = _read_jsonl_objects(run_dir / "events.jsonl", limit=_MAX_TRACE_EVENTS_PER_RUN)
        if not events:
            continue
        event_counts = Counter(str(event.get("event") or event.get("type") or "unknown") for event in events)
        runs.append(
            {
                "run_dir": _relative_or_absolute(run_dir, workspace),
                "task_id": run_dir.parents[1].name if len(run_dir.parents) >= 2 else None,
                "run_id": run_dir.name,
                "event_counts": dict(sorted(event_counts.items())),
                "errors": _error_excerpts(events),
            }
        )
    return runs


def _collect_nested_codex_rollouts(workspace: Path, excluded: Path | None) -> list[dict[str, Any]]:
    raw_root = workspace / ".botpipe" / "tasks"
    rollouts: list[dict[str, Any]] = []
    for path in sorted(raw_root.glob("**/raw/**/rollout-*.jsonl"), key=_mtime_sort_key, reverse=True):
        if len(rollouts) >= _MAX_TRACE_RUNS:
            break
        resolved = path.resolve()
        if excluded is not None and _is_relative_to(resolved, excluded):
            continue
        records = _read_jsonl_objects(path, limit=20)
        event_counts = Counter(str(record.get("type") or record.get("event") or "unknown") for record in records)
        rollouts.append(
            {
                "path": _relative_or_absolute(path, workspace),
                "record_count_sampled": len(records),
                "event_counts": dict(sorted(event_counts.items())),
                "errors": _error_excerpts(records),
            }
        )
    return rollouts


def _sanitize_identifier(value: str) -> str:
    normalized = re.sub(r"\W+", "_", value.strip().lower()).strip("_")
    if normalized and normalized[0].isdigit():
        normalized = "workflow_" + normalized
    return normalized


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _try_read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file():
            return None
        return _read_json_object(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _read_jsonl_objects(path: Path, *, limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if len(records) >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    records.append(value)
    except OSError:
        return []
    return records


def _outcome_tag(record: dict[str, Any]) -> str | None:
    outcome = record.get("outcome")
    if isinstance(outcome, dict):
        tag = outcome.get("tag")
        return str(tag) if tag is not None else None
    tag = record.get("route") or record.get("final_route") or record.get("candidate_route")
    if isinstance(tag, dict):
        value = tag.get("tag")
        return str(value) if value is not None else None
    return str(tag) if tag is not None else None


def _error_excerpts(records: list[dict[str, Any]]) -> list[str]:
    excerpts: list[str] = []
    for record in records:
        for key in ("error", "exception", "message", "reason"):
            value = record.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            lowered = value.lower()
            if key in {"message", "reason"} and not any(token in lowered for token in ("error", "fail", "exception")):
                continue
            excerpts.append(_truncate(value.strip()))
            break
        if len(excerpts) >= _MAX_ERROR_EXCERPTS:
            break
    return excerpts


def _raw_output_refs(records: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for record in records:
        raw_refs = record.get("raw_output_refs")
        if isinstance(raw_refs, list):
            refs.extend(str(ref) for ref in raw_refs if isinstance(ref, str))
        if len(refs) >= _MAX_ERROR_EXCERPTS:
            break
    return refs[:_MAX_ERROR_EXCERPTS]


def _json_field(payload: dict[str, Any] | None, field: str) -> Any:
    if payload is None:
        return None
    return payload.get(field)


def _workflow_name_from_run_dir(run_dir: Path) -> str:
    workflow_dir = run_dir.parent.parent
    name = workflow_dir.name
    return name[3:] if name.startswith("wf_") else name


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _truncate(value: str) -> str:
    return value if len(value) <= _MAX_TEXT_EXCERPT else value[: _MAX_TEXT_EXCERPT - 3] + "..."


def _mtime_sort_key(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


__all__ = [
    "PUBLICATION_RECEIPT_SCHEMA",
    "SOURCE_MANIFEST_SCHEMA",
    "TRACE_CORPUS_SCHEMA",
    "capture_source_manifest",
    "collect_trace_corpus",
    "derive_generated_workflow_name",
    "should_exclude_source_path",
    "validate_coverage_map",
    "validate_publication_inputs",
]
