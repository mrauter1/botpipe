"""Branch-group evidence rendering helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from .results import BranchArtifactObservation, BranchResult


@dataclass(frozen=True, slots=True)
class BranchManifest:
    schema: Literal["botlane.branch_results/v1"]
    kind: str
    name: str
    started_at: str
    finished_at: str
    duration_ms: int
    concurrency: int | None
    settle: str
    success_routes: tuple[str, ...]
    branches: tuple[BranchResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "kind": self.kind,
            "name": self.name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "concurrency": self.concurrency,
            "settle": self.settle,
            "success_routes": list(self.success_routes),
            "branches": [branch.to_manifest_dict() for branch in self.branches],
        }


def branch_group_paths(*, workflow_folder: Path, group_name: str) -> tuple[Path, Path, Path]:
    group_dir = workflow_folder / "_branch_groups" / group_name
    return group_dir, group_dir / "results.json", group_dir / "context.md"


def write_branch_group_evidence(
    *,
    results_path: Path,
    context_path: Path,
    manifest: BranchManifest | Mapping[str, Any],
    context_text: str,
) -> None:
    payload = manifest.to_dict() if isinstance(manifest, BranchManifest) else dict(manifest)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(context_text, encoding="utf-8")


def build_branch_manifest(
    *,
    spec: Any,
    started_at: str,
    finished_at: str,
    duration_ms: int,
    branches: list[object],
) -> BranchManifest:
    return BranchManifest(
        schema="botlane.branch_results/v1",
        kind=spec.kind,
        name=spec.name,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        concurrency=spec.concurrency,
        settle=spec.settle,
        success_routes=tuple(spec.success_routes),
        branches=tuple(_branch_result(branch) for branch in branches),
    )


def render_branch_group_context(manifest: BranchManifest | Mapping[str, Any]) -> str:
    manifest_payload = manifest.to_dict() if isinstance(manifest, BranchManifest) else dict(manifest)
    branches = [_branch_payload(branch) for branch in manifest_payload.get("branches", [])]
    sections = [
        _render_branch_group_header(manifest_payload, branches),
        _render_completion_summary(branches),
        _render_route_summary(branches),
        _render_failure_summary(branches),
        _render_needs_input_summary(branches),
        _render_cancellation_summary(branches),
        *(_render_branch_detail(branch) for branch in branches),
    ]
    return "\n".join(_flatten_sections(sections)) + "\n"


def _render_branch_group_header(manifest: Mapping[str, Any], branches: list[Mapping[str, Any]]) -> list[str]:
    return [
        f"# Branch Group: {manifest.get('name', '')}",
        "",
        f"- Kind: {manifest.get('kind', '')}",
        f"- Branch count: {len(branches)}",
        f"- Settlement policy: {manifest.get('settle', '')}",
        f"- Success routes: {', '.join(str(route) for route in manifest.get('success_routes', [])) or '(none)'}",
        f"- Started: {manifest.get('started_at', '')}",
        f"- Finished: {manifest.get('finished_at', '')}",
        f"- Duration ms: {manifest.get('duration_ms', 0)}",
        "",
    ]


def _render_completion_summary(branches: list[Mapping[str, Any]]) -> list[str]:
    counts = _status_counts(branches)
    return [
        "## Completion Summary",
        "",
        f"- Completed: {counts['completed']}",
        f"- Failed: {counts['failed']}",
        f"- Needs input: {counts['needs_input']}",
        f"- Cancelled: {counts['cancelled']}",
        f"- Skipped: {counts['skipped']}",
        "",
    ]


def _render_route_summary(branches: list[Mapping[str, Any]]) -> list[str]:
    lines = ["## Route Summary", ""]
    route_counts = _route_counts(branches)
    if route_counts:
        for route_name in sorted(route_counts):
            lines.append(f"- {route_name}: {route_counts[route_name]}")
    else:
        lines.append("- No branch route events were produced.")
    return lines


def _render_failure_summary(branches: list[Mapping[str, Any]]) -> list[str]:
    counts = _status_counts(branches)
    failed_branches = [branch for branch in branches if branch.get("status") == "failed"]
    return [
        "",
        "## Failure Summary",
        "",
        f"- Failed branches: {counts['failed']}",
        *_render_list_or_none(
            failed_branches,
            _render_failed_branch_summary,
        ),
    ]


def _render_needs_input_summary(branches: list[Mapping[str, Any]]) -> list[str]:
    counts = _status_counts(branches)
    needs_input_branches = [branch for branch in branches if branch.get("status") == "needs_input"]
    return [
        "",
        "## Needs Input Summary",
        "",
        f"- Branches awaiting input: {counts['needs_input']}",
        "",
        "## Needs Input Details",
        "",
        *_render_list_or_none(needs_input_branches, _render_needs_input_branch_summary),
    ]


def _render_cancellation_summary(branches: list[Mapping[str, Any]]) -> list[str]:
    counts = _status_counts(branches)
    cancelled_branches = [branch for branch in branches if branch.get("status") == "cancelled"]
    skipped_branches = [branch for branch in branches if branch.get("status") == "skipped"]
    return [
        "",
        "## Cancellation Summary",
        "",
        f"- Cancelled branches: {counts['cancelled']}",
        f"- Skipped branches: {counts['skipped']}",
        "",
        "## Cancellation Details",
        "",
        *_render_list_or_none(
            [*cancelled_branches, *skipped_branches],
            _render_cancelled_branch_summary,
        ),
    ]


def _render_branch_detail(branch: Mapping[str, Any]) -> list[str]:
    lines = [
        "",
        f"## Branch: {branch.get('name', '')}",
        "",
        f"- Index: {branch.get('index', '')}",
        f"- Step: {branch.get('step_name', '')}",
        f"- Input: `{json.dumps(branch.get('input'), ensure_ascii=False, sort_keys=True)}`",
        f"- Status: {branch.get('status', '')}",
        f"- Route: {branch.get('route') or '(none)'}",
        f"- Destination: {branch.get('destination') or '(none)'}",
        f"- Runtime control: {branch.get('runtime_control') or '(none)'}",
        f"- Reason: {branch.get('reason') or '(none)'}",
        f"- Question: {branch.get('question') or '(none)'}",
        f"- Provider session: {branch.get('provider_session') or '(none)'}",
        f"- Raw output path: {branch.get('raw_output_path') or '(none)'}",
    ]
    raw_output_paths = branch.get("raw_output_paths")
    if isinstance(raw_output_paths, Mapping) and raw_output_paths:
        lines.append("- Raw output files:")
        for label, value in sorted(raw_output_paths.items()):
            lines.append(f"  - {label}: {value}")
    artifacts = branch.get("artifacts") or []
    if artifacts:
        lines.append("- Artifacts:")
        for artifact in artifacts:
            lines.append(
                "  - "
                + f"{artifact.get('name', '')}: {artifact.get('path', '')} "
                + f"(kind={artifact.get('kind', '')}, exists={artifact.get('exists', False)}, "
                + f"validation={artifact.get('validation', '')})"
            )
    else:
        lines.append("- Artifacts: (none)")
    error = branch.get("error")
    if isinstance(error, Mapping):
        lines.append("- Error summary:")
        lines.append("  - " + (branch_error_summary(branch) or "(no error summary)"))
    else:
        lines.append("- Error summary: (none)")
    return lines


def _flatten_sections(sections: list[list[str]]) -> list[str]:
    return [line for section in sections for line in section]


def _route_counts(branches: list[Mapping[str, Any]]) -> dict[str, int]:
    route_counts: dict[str, int] = {}
    for branch in branches:
        route_name = branch.get("route")
        if isinstance(route_name, str) and route_name:
            route_counts[route_name] = route_counts.get(route_name, 0) + 1
    return route_counts


def _render_list_or_none(
    items: list[Mapping[str, Any]],
    render_item: Any,
) -> list[str]:
    if not items:
        return ["- None."]
    lines: list[str] = []
    for item in items:
        lines.extend(render_item(item))
    return lines


def _render_failed_branch_summary(branch: Mapping[str, Any]) -> list[str]:
    return [
        f"- {branch.get('name', '')}: {branch_error_summary(branch) or branch.get('reason') or '(no error summary)'}"
    ]


def _render_needs_input_branch_summary(branch: Mapping[str, Any]) -> list[str]:
    return [f"- {branch.get('name', '')}: {branch.get('question') or branch.get('reason') or 'Input required.'}"]


def _render_cancelled_branch_summary(branch: Mapping[str, Any]) -> list[str]:
    return [f"- {branch.get('name', '')}: {branch.get('reason') or branch.get('status', '')}"]


def _status_counts(branches: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"completed": 0, "failed": 0, "needs_input": 0, "cancelled": 0, "skipped": 0}
    for branch in branches:
        status = branch.get("status")
        if isinstance(status, str) and status in counts:
            counts[status] += 1
    return counts


def branch_error_summary(branch: Mapping[str, Any]) -> str | None:
    error = branch.get("error")
    if not isinstance(error, Mapping):
        return None
    error_type = error.get("type", "Error")
    message = error.get("message", "") or "(no message)"
    return f"{error_type}: {message}"


def _branch_payload(branch: object) -> dict[str, Any]:
    if isinstance(branch, Mapping):
        return dict(branch)
    to_manifest_dict = getattr(branch, "to_manifest_dict", None)
    if callable(to_manifest_dict):
        payload = to_manifest_dict()
        if isinstance(payload, Mapping):
            return dict(payload)
    raise TypeError(f"unsupported branch manifest entry {type(branch)!r}")


def _branch_result(branch: object) -> BranchResult:
    if isinstance(branch, BranchResult):
        return branch
    if isinstance(branch, Mapping):
        artifact_payloads = branch.get("artifacts") or ()
        return BranchResult(
            name=str(branch["name"]),
            index=int(branch["index"]),
            input=branch.get("input"),
            step_name=str(branch["step_name"]),
            status=branch["status"],
            route=branch.get("route"),
            destination=branch.get("destination"),
            runtime_control=branch.get("runtime_control"),
            reason=branch.get("reason"),
            question=branch.get("question"),
            artifacts=tuple(
                BranchArtifactObservation(
                    name=str(artifact.get("name", "")),
                    path=str(artifact.get("path", "")),
                    kind=artifact.get("kind"),
                    exists=bool(artifact.get("exists", False)),
                    validation=str(artifact.get("validation", "")),
                    validation_errors=tuple(str(error) for error in artifact.get("validation_errors", ())),
                )
                for artifact in artifact_payloads
                if isinstance(artifact, Mapping)
            ),
            raw_output_path=branch.get("raw_output_path"),
            raw_output_paths=dict(branch.get("raw_output_paths") or {}),
            provider_session=branch.get("provider_session"),
            provider_sessions=dict(branch.get("provider_sessions") or {}),
            error=None if branch.get("error") is None else dict(branch["error"]),
            started_at=str(branch["started_at"]),
            finished_at=str(branch["finished_at"]),
            duration_ms=int(branch["duration_ms"]),
            usage=dict(branch.get("usage") or {}),
            cancellation_requested=bool(branch.get("cancellation_requested", False)),
            cancellation_completed=bool(branch.get("cancellation_completed", False)),
            cancellation_supported=bool(branch.get("cancellation_supported", True)),
        )
    raise TypeError(f"branch manifest branch must be BranchResult or mapping, got {type(branch)!r}")
