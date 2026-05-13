"""Branch-group evidence rendering helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from .results import BranchArtifactObservation, BranchResult


@dataclass(frozen=True, slots=True)
class BranchManifest:
    schema: Literal["botpipe.branch_results/v1"]
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
    payload = branch_manifest_payload(manifest)
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
        schema="botpipe.branch_results/v1",
        kind=spec.kind,
        name=spec.name,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        concurrency=spec.concurrency,
        settle=spec.settle,
        success_routes=tuple(spec.success_routes),
        branches=tuple(_coerce_branch_result(branch) for branch in branches),
    )


def render_branch_group_context(manifest: BranchManifest | Mapping[str, Any]) -> str:
    typed_manifest = coerce_branch_manifest(manifest)
    branches = list(typed_manifest.branches)
    sections = [
        _render_branch_group_header(typed_manifest, branches),
        _render_completion_summary(branches),
        _render_route_summary(branches),
        _render_failure_summary(branches),
        _render_needs_input_summary(branches),
        _render_cancellation_summary(branches),
        *(_render_branch_detail(branch) for branch in branches),
    ]
    return "\n".join(_flatten_sections(sections)) + "\n"


def _render_branch_group_header(manifest: BranchManifest, branches: list[BranchResult]) -> list[str]:
    return [
        f"# Branch Group: {manifest.name}",
        "",
        f"- Kind: {manifest.kind}",
        f"- Branch count: {len(branches)}",
        f"- Settlement policy: {manifest.settle}",
        f"- Success routes: {', '.join(str(route) for route in manifest.success_routes) or '(none)'}",
        f"- Started: {manifest.started_at}",
        f"- Finished: {manifest.finished_at}",
        f"- Duration ms: {manifest.duration_ms}",
        "",
    ]


def _render_completion_summary(branches: list[BranchResult]) -> list[str]:
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


def _render_route_summary(branches: list[BranchResult]) -> list[str]:
    lines = ["## Route Summary", ""]
    route_counts = _route_counts(branches)
    if route_counts:
        for route_name in sorted(route_counts):
            lines.append(f"- {route_name}: {route_counts[route_name]}")
    else:
        lines.append("- No branch route events were produced.")
    return lines


def _render_failure_summary(branches: list[BranchResult]) -> list[str]:
    counts = _status_counts(branches)
    failed_branches = [branch for branch in branches if branch.status == "failed"]
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


def _render_needs_input_summary(branches: list[BranchResult]) -> list[str]:
    counts = _status_counts(branches)
    needs_input_branches = [branch for branch in branches if branch.status == "needs_input"]
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


def _render_cancellation_summary(branches: list[BranchResult]) -> list[str]:
    counts = _status_counts(branches)
    cancelled_branches = [branch for branch in branches if branch.status == "cancelled"]
    skipped_branches = [branch for branch in branches if branch.status == "skipped"]
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


def _render_branch_detail(branch: BranchResult) -> list[str]:
    lines = [
        "",
        f"## Branch: {branch.name}",
        "",
        f"- Index: {branch.index}",
        f"- Step: {branch.step_name}",
        f"- Input: `{json.dumps(branch.input, ensure_ascii=False, sort_keys=True)}`",
        f"- Status: {branch.status}",
        f"- Route: {branch.route or '(none)'}",
        f"- Destination: {branch.destination or '(none)'}",
        f"- Runtime control: {branch.runtime_control or '(none)'}",
        f"- Reason: {branch.reason or '(none)'}",
        f"- Question: {branch.question or '(none)'}",
        f"- Provider session: {branch.provider_session or '(none)'}",
        f"- Raw output path: {branch.raw_output_path or '(none)'}",
    ]
    raw_output_paths = branch.raw_output_paths
    if raw_output_paths:
        lines.append("- Raw output files:")
        for label, value in sorted(raw_output_paths.items()):
            lines.append(f"  - {label}: {value}")
    artifacts = branch.artifacts
    if artifacts:
        lines.append("- Artifacts:")
        for artifact in artifacts:
            lines.append(
                "  - "
                + f"{artifact.name}: {artifact.path} "
                + f"(kind={artifact.kind}, exists={artifact.exists}, "
                + f"validation={artifact.validation})"
            )
    else:
        lines.append("- Artifacts: (none)")
    if isinstance(branch.error, Mapping):
        lines.append("- Error summary:")
        lines.append("  - " + (branch_error_summary(branch) or "(no error summary)"))
    else:
        lines.append("- Error summary: (none)")
    return lines


def _flatten_sections(sections: list[list[str]]) -> list[str]:
    return [line for section in sections for line in section]


def _route_counts(branches: list[BranchResult]) -> dict[str, int]:
    route_counts: dict[str, int] = {}
    for branch in branches:
        route_name = branch.route
        if route_name:
            route_counts[route_name] = route_counts.get(route_name, 0) + 1
    return route_counts


def _render_list_or_none(
    items: list[BranchResult],
    render_item: Any,
) -> list[str]:
    if not items:
        return ["- None."]
    lines: list[str] = []
    for item in items:
        lines.extend(render_item(item))
    return lines


def _render_failed_branch_summary(branch: BranchResult) -> list[str]:
    return [f"- {branch.name}: {branch_error_summary(branch) or branch.reason or '(no error summary)'}"]


def _render_needs_input_branch_summary(branch: BranchResult) -> list[str]:
    return [f"- {branch.name}: {branch.question or branch.reason or 'Input required.'}"]


def _render_cancelled_branch_summary(branch: BranchResult) -> list[str]:
    return [f"- {branch.name}: {branch.reason or branch.status}"]


def _status_counts(branches: list[BranchResult]) -> dict[str, int]:
    counts = {"completed": 0, "failed": 0, "needs_input": 0, "cancelled": 0, "skipped": 0}
    for branch in branches:
        if branch.status in counts:
            counts[branch.status] += 1
    return counts


def branch_error_summary(branch: BranchResult | Mapping[str, Any]) -> str | None:
    error = branch.error if isinstance(branch, BranchResult) else branch.get("error")
    if not isinstance(error, Mapping):
        return None
    error_type = error.get("type", "Error")
    message = error.get("message", "") or "(no message)"
    return f"{error_type}: {message}"


def _coerce_branch_result(branch: object) -> BranchResult:
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


def coerce_branch_manifest(manifest: BranchManifest | Mapping[str, Any]) -> BranchManifest:
    if isinstance(manifest, BranchManifest):
        return manifest
    branches = manifest.get("branches", ())
    return BranchManifest(
        schema=str(manifest.get("schema", "botpipe.branch_results/v1")),
        kind=str(manifest.get("kind", "")),
        name=str(manifest.get("name", "")),
        started_at=str(manifest.get("started_at", "")),
        finished_at=str(manifest.get("finished_at", "")),
        duration_ms=int(manifest.get("duration_ms", 0)),
        concurrency=_coerce_optional_int(manifest.get("concurrency")),
        settle=str(manifest.get("settle", "")),
        success_routes=tuple(str(route) for route in manifest.get("success_routes", ())),
        branches=tuple(_coerce_branch_result(branch) for branch in branches),
    )


def branch_manifest_payload(manifest: BranchManifest | Mapping[str, Any]) -> dict[str, Any]:
    return manifest.to_dict() if isinstance(manifest, BranchManifest) else dict(manifest)


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)
