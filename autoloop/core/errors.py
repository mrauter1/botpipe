"""Workflow core error types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel


RetryKind = Literal[
    "empty_operation_value",
    "invalid_operation_choice",
    "invalid_operation_value",
    "invalid_output_artifact",
    "invalid_payload",
    "illegal_route",
    "malformed_operation_value",
    "malformed_provider_output",
    "missing_required_output_artifact",
    "provider_transport_failure",
]


@dataclass(frozen=True, slots=True)
class FailureContext:
    kind: str
    step_name: str
    candidate_route: str | None = None
    final_route: str | None = None
    runtime_control: str | None = None
    provider_attributable: bool = False
    source_hook: str | None = None
    source_phase: str | None = None
    target_step: str | None = None
    pending_input_id: str | None = None
    details: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": self.kind,
            "step_name": self.step_name,
            "candidate_route": self.candidate_route,
            "final_route": self.final_route,
            "runtime_control": self.runtime_control,
            "provider_attributable": self.provider_attributable,
            "source_hook": self.source_hook,
            "source_phase": self.source_phase,
            "target_step": self.target_step,
            "pending_input_id": self.pending_input_id,
            "details": dict(self.details),
        }
        for key, value in self.details.items():
            payload.setdefault(key, value)
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "FailureContext":
        details = payload.get("details")
        normalized_details = dict(details) if isinstance(details, dict) else {}
        for key, value in payload.items():
            if key in {
                "kind",
                "step_name",
                "candidate_route",
                "final_route",
                "runtime_control",
                "provider_attributable",
                "source_hook",
                "source_phase",
                "target_step",
                "pending_input_id",
                "details",
            }:
                continue
            normalized_details.setdefault(key, value)
        legacy_step = payload.get("step")
        legacy_route = payload.get("route")
        if isinstance(legacy_step, str) and "step" not in normalized_details:
            normalized_details["step"] = legacy_step
        if isinstance(legacy_route, str) and "route" not in normalized_details:
            normalized_details["route"] = legacy_route
        step_name = payload.get("step_name")
        if not isinstance(step_name, str) or not step_name:
            step_name = legacy_step if isinstance(legacy_step, str) and legacy_step else "<unknown>"
        candidate_route = payload.get("candidate_route")
        if not isinstance(candidate_route, str) or not candidate_route:
            candidate_route = legacy_route if isinstance(legacy_route, str) and legacy_route else None
        return cls(
            kind=str(payload.get("kind") or "execution_error"),
            step_name=step_name,
            candidate_route=candidate_route,
            final_route=payload.get("final_route") if isinstance(payload.get("final_route"), str) else None,
            runtime_control=payload.get("runtime_control")
            if isinstance(payload.get("runtime_control"), str)
            else None,
            provider_attributable=bool(payload.get("provider_attributable")),
            source_hook=payload.get("source_hook") if isinstance(payload.get("source_hook"), str) else None,
            source_phase=payload.get("source_phase") if isinstance(payload.get("source_phase"), str) else None,
            target_step=payload.get("target_step") if isinstance(payload.get("target_step"), str) else None,
            pending_input_id=payload.get("pending_input_id")
            if isinstance(payload.get("pending_input_id"), str)
            else None,
            details=normalized_details,
        )


class WorkflowError(Exception):
    """Base exception for the strict workflow core."""


class WorkflowValidationError(WorkflowError):
    """Raised when a workflow definition is invalid."""


class WorkflowCompilationError(WorkflowError):
    """Raised when a validated workflow cannot be compiled."""


class WorkflowExecutionError(WorkflowError):
    """Raised when workflow execution fails."""

    checkpoint_state: BaseModel | None = None
    failure_context: FailureContext | None = None
    retry_kind: RetryKind | None = None


class StepExecutionError(WorkflowExecutionError):
    """Execution error carrying checkpoint and failure metadata."""

    def __init__(
        self,
        message: str,
        *,
        checkpoint_state: BaseModel | None = None,
        failure_context: FailureContext | None = None,
        retry_kind: RetryKind | None = None,
    ) -> None:
        super().__init__(message)
        self.checkpoint_state = checkpoint_state
        self.failure_context = failure_context
        self.retry_kind = retry_kind


class RoutingError(StepExecutionError):
    """Raised when no route exists for a produced tag."""


class ArtifactResolutionError(StepExecutionError):
    """Raised when artifacts cannot be resolved or required inputs are missing."""


class MissingArtifactError(ArtifactResolutionError):
    """Raised when a required artifact path does not exist at runtime."""


class CheckpointError(StepExecutionError):
    """Raised when checkpoint persistence fails."""


class ProviderExecutionError(StepExecutionError):
    """Raised when the provider contract is violated."""
