"""Small authoring helpers for workflow-local evaluation case manifests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from autoloop.runtime.inspection import resolve_workflow_reference
from autoloop.runtime.loader import coerce_workflow_parameter_mapping

from .adaptation import write_selected_workflow_capability_snapshot
from autoloop.stdlib.lifecycle import write_workflow_json
from autoloop.stdlib.validation import (
    read_json_object,
    require_mapping,
    require_non_empty_string,
    require_string_list,
    validate_selected_workflow_capability_snapshot,
)

_CASE_KIND_ORDER = {"benchmark": 0, "edge": 1, "adversarial": 2}


def write_validated_eval_case_manifest(
    ctx,
    workflow: str | type[Any],
    case_manifest: Mapping[str, Any],
    relative_path: str | Path = "validated_eval_case_manifest.json",
) -> Path:
    """Validate and canonicalize one workflow-local eval-case manifest."""

    repo_root = _repo_root_from_context(ctx)
    resolved = resolve_workflow_reference(repo_root, workflow)
    snapshot_path = write_selected_workflow_capability_snapshot(ctx, workflow)
    snapshot = read_json_object(snapshot_path)
    selected_workflow_name, capability = validate_selected_workflow_capability_snapshot(
        snapshot,
        expected_selected_workflow_name=resolved.reference.workflow_name,
        expected_label="the resolved workflow",
    )

    validated_cases = _validate_cases(
        case_manifest,
        parameters_cls=resolved.parameters_cls,
        known_artifacts=_workflow_artifact_surface(capability),
    )
    return write_workflow_json(
        ctx,
        relative_path,
        {
            "repo_root": str(repo_root),
            "run_id": ctx.run_id,
            "selected_workflow_name": selected_workflow_name,
            "task_id": ctx.task_id,
            "workflow_name": ctx.workflow_name,
            "case_count": len(validated_cases),
            "case_ids": [case["case_id"] for case in validated_cases],
            "case_kinds": _present_case_kinds(validated_cases),
            "validated_cases": list(validated_cases),
        },
    )


def _validate_cases(
    case_manifest: Mapping[str, Any],
    *,
    parameters_cls: type[Any] | None,
    known_artifacts: set[str],
) -> list[dict[str, Any]]:
    manifest = require_mapping(case_manifest, "eval case manifest must be a JSON object")
    raw_cases = manifest.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("eval case manifest must define cases as a JSON array")
    if not raw_cases:
        raise ValueError("eval case manifest must define at least one case")

    seen_ids: set[str] = set()
    validated_cases: list[dict[str, Any]] = []
    for index, raw_case in enumerate(raw_cases):
        case = require_mapping(raw_case, f"eval case at index {index} must be a JSON object")
        case_id = require_non_empty_string(
            case.get("case_id"),
            f"eval case at index {index} must define a non-empty case_id",
        )
        if case_id in seen_ids:
            raise ValueError(f"eval case manifest repeats case_id {case_id!r}")
        seen_ids.add(case_id)

        case_kind = require_non_empty_string(
            case.get("case_kind"),
            f"eval case {case_id!r} must define a non-empty case_kind",
        )
        if case_kind not in _CASE_KIND_ORDER:
            legal_kinds = ", ".join(sorted(_CASE_KIND_ORDER))
            raise ValueError(f"eval case {case_id!r} has unsupported case_kind {case_kind!r}; expected one of {legal_kinds}")

        prompt = require_non_empty_string(
            case.get("prompt"),
            f"eval case {case_id!r} must define a non-empty prompt",
        )
        expected_artifacts = _normalize_expected_artifacts(case_id, case.get("expected_artifacts"), known_artifacts)
        workflow_parameters = _normalize_workflow_parameters(case_id, case.get("workflow_parameters"), parameters_cls)
        validated_cases.append(
            {
                "case_id": case_id,
                "case_kind": case_kind,
                "expected_artifacts": expected_artifacts,
                "prompt": prompt,
                "workflow_parameters": workflow_parameters,
            }
        )

    return sorted(validated_cases, key=lambda case: (_CASE_KIND_ORDER[case["case_kind"]], case["case_id"]))


def _normalize_expected_artifacts(case_id: str, value: Any, known_artifacts: set[str]) -> list[str]:
    artifacts = require_string_list(
        value,
        f"eval case {case_id!r} must define expected_artifacts as a non-empty string list",
        dedupe=True,
        sort_output=True,
    )
    unknown = sorted(set(artifacts) - known_artifacts)
    if unknown:
        if len(unknown) == 1:
            raise ValueError(f"eval case {case_id!r} expects unknown artifact {unknown[0]!r}")
        names = ", ".join(repr(name) for name in unknown)
        raise ValueError(f"eval case {case_id!r} expects unknown artifacts: {names}")
    return artifacts


def _normalize_workflow_parameters(case_id: str, value: Any, parameters_cls: type[Any] | None) -> dict[str, Any]:
    if value in (None, {}):
        raw_parameters: Mapping[str, Any] = {}
    else:
        raw_parameters = require_mapping(
            value,
            f"eval case {case_id!r} workflow_parameters must be a JSON object",
        )
    return coerce_workflow_parameter_mapping(parameters_cls, raw_parameters)


def _workflow_artifact_surface(capability: Mapping[str, Any]) -> set[str]:
    artifact_entries = capability.get("artifacts")
    steps = capability.get("steps")
    artifacts: set[str] = set()
    if artifact_entries is not None:
        if not isinstance(artifact_entries, list):
            raise ValueError("selected_workflow_capability.json must define selected_workflow_capability.artifacts as a JSON array")
        for index, raw_artifact in enumerate(artifact_entries):
            artifact = require_mapping(
                raw_artifact,
                f"selected_workflow_capability.json artifacts[{index}] must be a JSON object",
            )
            artifact_name = artifact.get("name")
            if artifact_name is not None:
                artifacts.add(
                    require_non_empty_string(
                        artifact_name,
                        (
                            "selected_workflow_capability.json "
                            f"artifacts[{index}].name must be a non-empty string when present"
                        ),
                    )
                )
    if not isinstance(steps, list):
        raise ValueError("selected_workflow_capability.json must define selected_workflow_capability.steps as a JSON array")

    qualified_candidates: list[str] = []

    for index, raw_step in enumerate(steps):
        step = require_mapping(
            raw_step,
            f"selected_workflow_capability.json steps[{index}] must be a JSON object",
        )
        for key in ("requires", "writes", "log_artifacts"):
            names = _optional_string_list(step.get(key), key)
            artifacts.update(names)
            qualified_candidates.extend(name for name in names if "." in name)
        routes = step.get("routes")
        if routes is None:
            continue
        if not isinstance(routes, Mapping):
            raise ValueError(
                "selected_workflow_capability.json routes must be a JSON object when present"
            )
        for route_name, raw_route in routes.items():
            route = require_mapping(
                raw_route,
                f"selected_workflow_capability.json routes[{route_name!r}] must be a JSON object",
            )
            raw_required_writes = route.get("required_writes")
            if raw_required_writes is None:
                continue
            names = require_string_list(
                raw_required_writes,
                (
                    "selected_workflow_capability.json "
                    f"routes[{route_name!r}].required_writes must be a string list when present"
                ),
                min_length=0,
                dedupe=True,
                sort_output=True,
            )
            artifacts.update(names)
            qualified_candidates.extend(name for name in names if "." in name)

    unique_qualified_candidates = set(qualified_candidates)
    suffix_counts: dict[str, int] = {}
    for name in unique_qualified_candidates:
        suffix = name.rsplit(".", 1)[-1]
        suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
    for name in unique_qualified_candidates:
        suffix = name.rsplit(".", 1)[-1]
        if suffix_counts.get(suffix) == 1:
            artifacts.add(suffix)
    return artifacts


def _optional_string_list(value: Any, field_name: str) -> list[str]:
    if value in (None, []):
        return []
    return require_string_list(
        value,
        f"selected_workflow_capability.json must define {field_name} as a string list when present",
    )


def _present_case_kinds(validated_cases: Sequence[Mapping[str, Any]]) -> list[str]:
    present = {case["case_kind"] for case in validated_cases}
    return [kind for kind in _CASE_KIND_ORDER if kind in present]


def _repo_root_from_context(ctx) -> Path:
    return ctx.root.resolve()


__all__ = ["write_validated_eval_case_manifest"]
