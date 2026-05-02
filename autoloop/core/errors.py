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

    def __init__(
        self,
        message: str,
        *,
        checkpoint_state: BaseModel | None = None,
        failure_context: FailureContext | None = None,
        retry_kind: RetryKind | None = None,
        pending_handoffs: tuple[object, ...] = (),
    ) -> None:
        super().__init__(message)
        self.checkpoint_state = checkpoint_state
        self.failure_context = failure_context
        self.retry_kind = retry_kind
        self.pending_handoffs = tuple(pending_handoffs)


class StepExecutionError(WorkflowExecutionError):
    """Execution error carrying checkpoint and failure metadata."""

    def __init__(
        self,
        message: str,
        *,
        checkpoint_state: BaseModel | None = None,
        failure_context: FailureContext | None = None,
        retry_kind: RetryKind | None = None,
        pending_handoffs: tuple[object, ...] = (),
    ) -> None:
        super().__init__(
            message,
            checkpoint_state=checkpoint_state,
            failure_context=failure_context,
            retry_kind=retry_kind,
            pending_handoffs=pending_handoffs,
        )


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


_UNSET = object()


def exception_checkpoint_state(
    exc: BaseException,
    *,
    current_state: BaseModel | None = None,
) -> BaseModel | None:
    if isinstance(exc, WorkflowExecutionError) and isinstance(exc.checkpoint_state, BaseModel):
        return exc.checkpoint_state
    return current_state


def exception_failure_context(exc: BaseException) -> FailureContext | None:
    if not isinstance(exc, WorkflowExecutionError):
        return None
    if not isinstance(exc.failure_context, FailureContext):
        return None
    return FailureContext.from_payload(exc.failure_context.to_payload())


def exception_failure_context_payload(exc: BaseException) -> dict[str, Any]:
    failure_context = exception_failure_context(exc)
    if failure_context is not None:
        return failure_context.to_payload()
    return {
        "error": str(exc),
        "error_type": type(exc).__name__,
    }


def exception_retry_kind(exc: BaseException) -> RetryKind | None:
    if not isinstance(exc, WorkflowExecutionError):
        return None
    return exc.retry_kind


def exception_pending_handoffs(
    exc: BaseException,
    *,
    default: tuple[Any, ...] = (),
) -> tuple[Any, ...]:
    if isinstance(exc, WorkflowExecutionError) and exc.pending_handoffs:
        return exc.pending_handoffs
    return default


def replace_execution_error(
    exc: WorkflowExecutionError,
    *,
    checkpoint_state: BaseModel | None | object = _UNSET,
    failure_context: FailureContext | None | object = _UNSET,
    retry_kind: RetryKind | None | object = _UNSET,
    pending_handoffs: tuple[Any, ...] | object = _UNSET,
) -> WorkflowExecutionError:
    resolved_checkpoint_state = exc.checkpoint_state if checkpoint_state is _UNSET else checkpoint_state
    resolved_failure_context = exc.failure_context if failure_context is _UNSET else failure_context
    resolved_retry_kind = exc.retry_kind if retry_kind is _UNSET else retry_kind
    resolved_pending_handoffs = exc.pending_handoffs if pending_handoffs is _UNSET else pending_handoffs
    return type(exc)(
        str(exc),
        checkpoint_state=resolved_checkpoint_state,
        failure_context=resolved_failure_context,
        retry_kind=resolved_retry_kind,
        pending_handoffs=tuple(resolved_pending_handoffs or ()),
    )


def enrich_execution_error(
    exc: BaseException,
    *,
    checkpoint_state: BaseModel | None = None,
    failure_context: FailureContext | None = None,
    retry_kind: RetryKind | None = None,
    pending_handoffs: tuple[Any, ...] | None = None,
) -> WorkflowExecutionError:
    if isinstance(exc, WorkflowExecutionError):
        resolved_checkpoint_state = exc.checkpoint_state or checkpoint_state
        resolved_failure_context = exc.failure_context or failure_context
        resolved_retry_kind = exc.retry_kind or retry_kind
        resolved_pending_handoffs = exc.pending_handoffs or tuple(pending_handoffs or ())
        if (
            resolved_checkpoint_state is exc.checkpoint_state
            and resolved_failure_context is exc.failure_context
            and resolved_retry_kind == exc.retry_kind
            and resolved_pending_handoffs == exc.pending_handoffs
        ):
            return exc
        return replace_execution_error(
            exc,
            checkpoint_state=resolved_checkpoint_state,
            failure_context=resolved_failure_context,
            retry_kind=resolved_retry_kind,
            pending_handoffs=resolved_pending_handoffs,
        )
    message = str(exc).strip() or f"{type(exc).__name__} raised during workflow execution"
    return WorkflowExecutionError(
        message,
        checkpoint_state=checkpoint_state,
        failure_context=failure_context,
        retry_kind=retry_kind,
        pending_handoffs=tuple(pending_handoffs or ()),
    )
