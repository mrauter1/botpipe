"""Route-contract helpers and normalization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import WorkflowValidationError

DEFAULT_ADVANCE_EFFECT = "Advances the current work item along the declared workflow transition."
DEFAULT_REWORK_EFFECT = "Keeps the current work-item boundary intact and repeats the same step for local repair."
DEFAULT_REPLAN_EFFECT = "Changes the current work-item boundary materially and routes the workflow to replanning."


@dataclass(frozen=True, slots=True)
class RouteContract:
    """Typed authoring helper for step route contracts."""

    summary: str
    required_artifacts: tuple[str, ...] = ()
    work_item_effect: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", _normalize_text(self.summary, field_name="summary"))
        object.__setattr__(
            self,
            "required_artifacts",
            tuple(_normalize_required_artifacts(self.required_artifacts, step_name=None, route_name=None)),
        )
        if self.work_item_effect is not None:
            object.__setattr__(
                self,
                "work_item_effect",
                _normalize_text(self.work_item_effect, field_name="work_item_effect"),
            )


RouteContractSpec = RouteContract | Mapping[str, Any]


def normalize_route_contract(
    route_name: str,
    contract: RouteContractSpec,
    *,
    step_name: str,
    known_artifact_names: set[str] | None = None,
) -> dict[str, Any]:
    """Return the canonical runtime shape for one route contract."""

    if isinstance(contract, RouteContract):
        summary = contract.summary
        required_artifacts = list(contract.required_artifacts)
        work_item_effect = contract.work_item_effect
    elif isinstance(contract, Mapping):
        summary_value = contract.get("summary", contract.get("evidence"))
        summary = _normalize_text(summary_value, field_name="summary", step_name=step_name, route_name=route_name)
        required_artifacts = _normalize_required_artifacts(
            contract.get("required_artifacts", ()),
            step_name=step_name,
            route_name=route_name,
        )
        work_item_effect_value = contract.get("work_item_effect", contract.get("state_effect"))
        work_item_effect = (
            _normalize_text(
                work_item_effect_value,
                field_name="work_item_effect",
                step_name=step_name,
                route_name=route_name,
            )
            if work_item_effect_value is not None
            else None
        )
    else:
        raise WorkflowValidationError(
            f"step {step_name!r} route contract for {route_name!r} must be a mapping or RouteContract"
        )

    effect = work_item_effect or infer_work_item_effect(route_name)
    normalized = {
        "summary": summary,
        "required_artifacts": required_artifacts,
        "work_item_effect": effect,
    }
    if known_artifact_names is not None:
        _validate_required_artifact_names(
            normalized["required_artifacts"],
            known_artifact_names=known_artifact_names,
            step_name=step_name,
            route_name=route_name,
        )
    return normalized


def normalize_route_contracts(
    route_contracts: Mapping[str, RouteContractSpec] | None,
    *,
    step_name: str,
    known_artifact_names: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return the canonical runtime shape for a step's route contracts."""

    if not route_contracts:
        return {}
    artifact_names = set(known_artifact_names) if known_artifact_names is not None else None
    return {
        route_name: normalize_route_contract(
            route_name,
            contract,
            step_name=step_name,
            known_artifact_names=artifact_names,
        )
        for route_name, contract in route_contracts.items()
    }


def infer_work_item_effect(route_name: str) -> str:
    """Infer a default work-item effect from a conventional route name."""

    if route_name == "needs_rework":
        return DEFAULT_REWORK_EFFECT
    if route_name == "needs_replan":
        return DEFAULT_REPLAN_EFFECT
    return DEFAULT_ADVANCE_EFFECT


def _normalize_required_artifacts(
    raw: Any,
    *,
    step_name: str | None,
    route_name: str | None,
) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (str, Mapping)) or not isinstance(raw, Iterable):
        raise WorkflowValidationError(_field_error("required_artifacts", step_name=step_name, route_name=route_name))
    normalized: list[str] = []
    for item in raw:
        normalized.append(
            _normalize_text(
                item,
                field_name="required_artifact",
                step_name=step_name,
                route_name=route_name,
            )
        )
    return normalized


def _validate_required_artifact_names(
    required_artifacts: list[str],
    *,
    known_artifact_names: set[str],
    step_name: str,
    route_name: str,
) -> None:
    unknown = sorted(name for name in required_artifacts if name not in known_artifact_names)
    if unknown:
        raise WorkflowValidationError(
            f"step {step_name!r} route contract for {route_name!r} references unknown artifacts {unknown!r}"
        )


def _normalize_text(
    value: Any,
    *,
    field_name: str,
    step_name: str | None = None,
    route_name: str | None = None,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowValidationError(_field_error(field_name, step_name=step_name, route_name=route_name))
    return value.strip()


def _field_error(field_name: str, *, step_name: str | None, route_name: str | None) -> str:
    if step_name is None or route_name is None:
        return f"route contract {field_name} must be a non-empty string or sequence of non-empty strings"
    return (
        f"step {step_name!r} route contract for {route_name!r} has invalid {field_name}; "
        "expected non-empty strings"
    )


__all__ = [
    "DEFAULT_ADVANCE_EFFECT",
    "DEFAULT_REPLAN_EFFECT",
    "DEFAULT_REWORK_EFFECT",
    "RouteContract",
    "RouteContractSpec",
    "infer_work_item_effect",
    "normalize_route_contract",
    "normalize_route_contracts",
]
