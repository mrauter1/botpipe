"""Internal execution service protocols.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ArtifactService(Protocol):
    def resolve_artifacts(self, context: Any) -> Any:
        ...

    def collect_artifact_observations(self, context: Any, artifacts: Any) -> Any:
        ...

    def validate_required_writes(
        self,
        *,
        step: Any,
        route_tag: str,
        state: Any,
        artifacts: Any,
        error_cls: type[Exception],
        provider_attributable: bool,
    ) -> None:
        ...

    def enforce_artifact_contracts(
        self,
        step: Any,
        context: Any,
        artifacts: Any,
        *,
        route_tag: str,
        state: Any,
        error_cls: type[Exception],
        provider_attributable: bool,
    ) -> None:
        ...


class RouteService(Protocol):
    def route_for_step(self, step_name: str, route_tag: str) -> Any:
        ...

    def provider_visible_route_tags(
        self,
        step_name: str,
        *,
        mode: str,
    ) -> tuple[str, ...]:
        ...

    def validate_event(
        self,
        step: Any,
        event: Any,
        *,
        provider_attributable: bool,
        error_cls: type[Exception],
    ) -> None:
        ...

    def annotate_execution_error(self, exc: Exception, **kwargs: Any) -> Exception:
        ...

    def ensure_hook_redirect_limit(self, step: Any, *, candidate_route: str | None, redirects: Any) -> None:
        ...

    def normalize_direct_runtime_control(
        self,
        *,
        step: Any,
        context: Any,
        control: Any,
        hook_name: str,
        hook_phase: str,
    ) -> Any:
        ...

    def compiled_route_for_step(self, step: Any, route_tag: str) -> Any:
        ...

    def event_context_payload(self, event: Any) -> Any:
        ...

    def pending_input_from_event(self, *, source_step: str, event: Any) -> Any:
        ...

    def schedule_direct_control_handoffs(
        self,
        pending_handoffs: Any,
        *,
        control: Any,
        context: Any,
        source_step: str,
    ) -> Any:
        ...

    def schedule_route_handoffs(
        self,
        pending_handoffs: Any,
        *,
        route: Any,
        event: Any,
        destination: str,
        context: Any,
        source_step: str,
    ) -> Any:
        ...


class HookService(Protocol):
    def run_after(self, step: Any, context: Any, state: Any, *, artifacts: Any, subject: Any, candidate_event: Any, hook: Any = None, hook_phase: str = "after") -> Any:
        ...

    def run_route(self, step: Any, context: Any, state: Any, artifacts: Any, *, event: Any, hook: Any = None, hook_phase: str = "on_taken") -> Any:
        ...


class SessionService(Protocol): ...


class CheckpointService(Protocol): ...


class EventService(Protocol): ...


class ProviderService(Protocol): ...


class OperationService(Protocol): ...


class ChildWorkflowService(Protocol): ...


class StateService(Protocol):
    def initialize_step_state(self, step: Any, store: Any) -> Any:
        ...

    def initialize_item_state(self, store: Any) -> Any:
        ...

    def track_visit(self, step: Any, store: Any) -> None:
        ...

    def clone_state(self, state: Any) -> Any:
        ...

    def update_final_step_runtime_state(self, step: Any, store: Any, event: Any) -> None:
        ...

    def update_final_item_runtime_state(self, store: Any, event: Any) -> None:
        ...


@dataclass(frozen=True, slots=True)
class ExecutionServices:
    artifacts: ArtifactService | None = None
    routes: RouteService | None = None
    hooks: HookService | None = None
    sessions: SessionService | None = None
    checkpoints: CheckpointService | None = None
    events: EventService | None = None
    providers: ProviderService | None = None
    operations: OperationService | None = None
    child_workflows: ChildWorkflowService | None = None
    state: StateService | None = None
