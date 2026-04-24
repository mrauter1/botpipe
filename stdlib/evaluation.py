"""Small authoring helpers for workflow-local evaluation case manifests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..runtime.loader import coerce_workflow_parameter_mapping, resolve_workflow_reference
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from runtime.loader import coerce_workflow_parameter_mapping, resolve_workflow_reference

from .adaptation import write_selected_workflow_capability_snapshot
from .lifecycle import write_workflow_json

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
    snapshot = _read_json(snapshot_path)
    selected_workflow_name = _require_text(
        snapshot.get("selected_workflow_name"),
        "selected_workflow_capability.json must define a non-empty selected_workflow_name",
    )
    capability = _require_mapping(
        snapshot.get("selected_workflow_capability"),
        "selected_workflow_capability.json must define selected_workflow_capability as a JSON object",
    )
    capability_workflow_name = _require_text(
        capability.get("workflow_name"),
        "selected_workflow_capability.json must define selected_workflow_capability.workflow_name",
    )
    if capability_workflow_name != selected_workflow_name:
        raise ValueError("selected_workflow_capability.json workflow_name must match selected_workflow_name")
    if selected_workflow_name != resolved.package.workflow_name:
        raise ValueError("selected_workflow_capability.json selected_workflow_name must match the resolved workflow")

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
    manifest = _require_mapping(case_manifest, "eval case manifest must be a JSON object")
    raw_cases = manifest.get("cases")
    if not isinstance(raw_cases, Sequence) or isinstance(raw_cases, (str, bytes, bytearray)):
        raise ValueError("eval case manifest must define cases as a JSON array")
    if not raw_cases:
        raise ValueError("eval case manifest must define at least one case")

    seen_ids: set[str] = set()
    validated_cases: list[dict[str, Any]] = []
    for index, raw_case in enumerate(raw_cases):
        case = _require_mapping(raw_case, f"eval case at index {index} must be a JSON object")
        case_id = _require_text(case.get("case_id"), f"eval case at index {index} must define a non-empty case_id")
        if case_id in seen_ids:
            raise ValueError(f"eval case manifest repeats case_id {case_id!r}")
        seen_ids.add(case_id)

        case_kind = _require_text(
            case.get("case_kind"),
            f"eval case {case_id!r} must define a non-empty case_kind",
        )
        if case_kind not in _CASE_KIND_ORDER:
            legal_kinds = ", ".join(sorted(_CASE_KIND_ORDER))
            raise ValueError(f"eval case {case_id!r} has unsupported case_kind {case_kind!r}; expected one of {legal_kinds}")

        prompt = _require_text(case.get("prompt"), f"eval case {case_id!r} must define a non-empty prompt")
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
    artifacts = _require_string_list(
        value,
        f"eval case {case_id!r} must define expected_artifacts as a non-empty string list",
    )
    unique_artifacts = sorted(set(artifacts))
    unknown = sorted(set(unique_artifacts) - known_artifacts)
    if unknown:
        if len(unknown) == 1:
            raise ValueError(f"eval case {case_id!r} expects unknown artifact {unknown[0]!r}")
        names = ", ".join(repr(name) for name in unknown)
        raise ValueError(f"eval case {case_id!r} expects unknown artifacts: {names}")
    return unique_artifacts


def _normalize_workflow_parameters(case_id: str, value: Any, parameters_cls: type[Any] | None) -> dict[str, Any]:
    if value in (None, {}):
        raw_parameters: Mapping[str, Any] = {}
    else:
        raw_parameters = _require_mapping(
            value,
            f"eval case {case_id!r} workflow_parameters must be a JSON object",
        )
    return coerce_workflow_parameter_mapping(parameters_cls, raw_parameters)


def _workflow_artifact_surface(capability: Mapping[str, Any]) -> set[str]:
    steps = capability.get("steps")
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes, bytearray)):
        raise ValueError("selected_workflow_capability.json must define selected_workflow_capability.steps as a JSON array")

    artifacts: set[str] = set()
    for index, raw_step in enumerate(steps):
        step = _require_mapping(
            raw_step,
            f"selected_workflow_capability.json steps[{index}] must be a JSON object",
        )
        for key in ("requires", "produces", "log_artifacts"):
            artifacts.update(_optional_string_list(step.get(key), key))
        route_contracts = step.get("route_contracts")
        if route_contracts is None:
            continue
        if not isinstance(route_contracts, Mapping):
            raise ValueError(
                "selected_workflow_capability.json route_contracts must be a JSON object when present"
            )
        for route_name, raw_contract in route_contracts.items():
            contract = _require_mapping(
                raw_contract,
                f"selected_workflow_capability.json route_contracts[{route_name!r}] must be a JSON object",
            )
            artifacts.update(_optional_string_list(contract.get("required_artifacts"), "required_artifacts"))
    return artifacts


def _optional_string_list(value: Any, field_name: str) -> list[str]:
    if value in (None, []):
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"selected_workflow_capability.json must define {field_name} as a string list when present")
    result: list[str] = []
    for item in value:
        result.append(_require_text(item, f"selected_workflow_capability.json {field_name} entries must be non-empty strings"))
    return result


def _require_mapping(value: Any, message: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(message)
    return value


def _require_string_list(value: Any, message: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(message)
    values = [_require_text(item, message) for item in value]
    if not values:
        raise ValueError(message)
    return values


def _require_text(value: Any, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(message)
    return value.strip()


def _present_case_kinds(validated_cases: Sequence[Mapping[str, Any]]) -> list[str]:
    present = {case["case_kind"] for case in validated_cases}
    return [kind for kind in _CASE_KIND_ORDER if kind in present]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _repo_root_from_context(ctx) -> Path:
    return ctx.root.resolve()


__all__ = ["write_validated_eval_case_manifest"]
