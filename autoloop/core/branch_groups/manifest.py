"""Branch-group evidence rendering helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def branch_group_paths(*, workflow_folder: Path, group_name: str) -> tuple[Path, Path, Path]:
    group_dir = workflow_folder / "_branch_groups" / group_name
    return group_dir, group_dir / "results.json", group_dir / "context.md"


def write_branch_group_evidence(
    *,
    results_path: Path,
    context_path: Path,
    manifest: Mapping[str, Any],
    context_text: str,
) -> None:
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(dict(manifest), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(context_text, encoding="utf-8")


def build_branch_manifest(
    *,
    spec: Any,
    started_at: str,
    finished_at: str,
    duration_ms: int,
    branches: list[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "autoloop.branch_results/v1",
        "kind": spec.kind,
        "name": spec.name,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "concurrency": spec.concurrency,
        "settle": spec.settle,
        "success_routes": list(spec.success_routes),
        "branches": list(branches),
    }


def render_branch_group_context(manifest: Mapping[str, Any]) -> str:
    branches = list(manifest.get("branches", []))
    counts = _status_counts(branches)
    failed_branches = [branch for branch in branches if branch.get("status") == "failed"]
    needs_input_branches = [branch for branch in branches if branch.get("status") == "needs_input"]
    cancelled_branches = [branch for branch in branches if branch.get("status") == "cancelled"]
    skipped_branches = [branch for branch in branches if branch.get("status") == "skipped"]
    lines = [
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
        "## Completion Summary",
        "",
        f"- Completed: {counts['completed']}",
        f"- Failed: {counts['failed']}",
        f"- Needs input: {counts['needs_input']}",
        f"- Cancelled: {counts['cancelled']}",
        f"- Skipped: {counts['skipped']}",
        "",
        "## Route Summary",
        "",
    ]
    route_counts: dict[str, int] = {}
    for branch in branches:
        route_name = branch.get("route")
        if isinstance(route_name, str) and route_name:
            route_counts[route_name] = route_counts.get(route_name, 0) + 1
    if route_counts:
        for route_name in sorted(route_counts):
            lines.append(f"- {route_name}: {route_counts[route_name]}")
    else:
        lines.append("- No branch route events were produced.")
    lines.extend(
        [
            "",
            "## Failure Summary",
            "",
            f"- Failed branches: {counts['failed']}",
            "",
            "## Needs Input Summary",
            "",
            f"- Branches awaiting input: {counts['needs_input']}",
            "",
            "## Cancellation Summary",
            "",
            f"- Cancelled branches: {counts['cancelled']}",
            f"- Skipped branches: {counts['skipped']}",
        ]
    )
    if failed_branches:
        for branch in failed_branches:
            lines.append(
                f"- {branch.get('name', '')}: {branch_error_summary(branch) or branch.get('reason') or '(no error summary)'}"
            )
    else:
        lines.append("- None.")
    lines.extend(["", "## Needs Input Details", ""])
    if needs_input_branches:
        for branch in needs_input_branches:
            lines.append(
                f"- {branch.get('name', '')}: {branch.get('question') or branch.get('reason') or 'Input required.'}"
            )
    else:
        lines.append("- None.")
    lines.extend(["", "## Cancellation Details", ""])
    if cancelled_branches or skipped_branches:
        for branch in (*cancelled_branches, *skipped_branches):
            lines.append(f"- {branch.get('name', '')}: {branch.get('reason') or branch.get('status', '')}")
    else:
        lines.append("- None.")
    for branch in branches:
        lines.extend(
            [
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
        )
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
    return "\n".join(lines) + "\n"


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
