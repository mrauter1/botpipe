"""Internal execution service protocols.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ArtifactService(Protocol):
    def resolve_artifacts(self, context: Any) -> Any:
        ...

    def ensure_required_artifacts(self, step: Any, artifacts: Any) -> None:
        ...

    def ensure_named_artifacts_exist(self, names: Any, artifacts: Any, *, step_name: str) -> None:
        ...

    def resolve_workspace_read_path(self, raw_path: str, *, context: Any) -> Any:
        ...

    def artifact_lookup_name(self, name: object) -> str:
        ...

    def artifact_schema_name(self, artifact: Any) -> str | None:
        ...

    def append_logs(self, step: Any, artifacts: Any, content: str) -> None:
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

    def validate_hook_event_override(self, step: Any, event: Any) -> Any:
        ...

    def build_hook_redirect_record(self, **kwargs: Any) -> Any:
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

    def matching_pending_handoffs(self, step: Any, context: Any, pending_handoffs: Any) -> Any:
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

    def event_from_outcome(self, step: Any, outcome: Any) -> Any:
        ...


class HookService(Protocol):
    def run_after(self, step: Any, context: Any, state: Any, *, artifacts: Any, subject: Any, candidate_event: Any, hook: Any = None, hook_phase: str = "after") -> Any:
        ...

    def run_route(self, step: Any, context: Any, state: Any, artifacts: Any, *, event: Any, hook: Any = None, hook_phase: str = "on_taken") -> Any:
        ...


class SessionService(Protocol):
    def resolve_session(self, step: Any, context: Any) -> Any:
        ...

    def resolve_pair_review_session(self, step: Any, context: Any, *, producer_session: Any) -> Any:
        ...

    def persist_session(self, binding: Any, *, context: Any | None = None) -> None:
        ...

    def restore(self, snapshot: Any) -> None:
        ...

    def snapshot(self) -> Any:
        ...


class CheckpointService(Protocol):
    def save(self, *args: Any, **kwargs: Any) -> Any:
        ...


class EventService(Protocol):
    def emit_runtime_event(self, event_type: str, **payload: Any) -> None:
        ...

    def emit_hook_event(self, event_type: str, *, step: Any | None = None, context: Any | None = None, **payload: Any) -> None:
        ...

    def emit_provider_attempt_event(self, event_type: str, *, step: Any, context: Any, turn_kind: str, attempt: int, token_usage: Any | None = None, failure_context: Any | None = None) -> None:
        ...

    def emit_provider_attempt_finished(self, *, step: Any, context: Any, turn_kind: str, attempt: int, token_usage: Any | None) -> None:
        ...

    def emit_provider_attempt_failed(self, *, step: Any, context: Any, turn_kind: str, attempt: int, exc: Exception) -> None:
        ...

    def annotate_execution_error(self, exc: Exception, **kwargs: Any) -> Exception:
        ...

    def failure_context_for_exception(self, exc: Exception) -> Any:
        ...

    def exception_failure_context_payload(self, exc: Exception) -> Any:
        ...

    def retry_kind_for_exception(self, exc: Exception) -> str | None:
        ...

    def serialize_exception(self, exc: Exception) -> dict[str, Any]:
        ...

    def next_retry_feedback(self, step: Any, exc: Exception, *, attempt: int) -> tuple[str | None, Exception]:
        ...


class ProviderService(Protocol):
    async def run_llm(self, request: Any) -> Any:
        ...

    async def run_producer(self, request: Any) -> Any:
        ...

    async def run_verifier(self, request: Any) -> Any:
        ...

    def resolve_prompt(self, prompt: Any, *, context: Any) -> Any:
        ...

    def validate_outcome(self, step: Any, outcome: Any) -> None:
        ...


class OperationService(Protocol):
    def bind_step(self, *, step: Any, context: Any, run_folder: Any, step_name: str, step_visit: int) -> Any:
        ...

    def set_provider_policy_resolver(self, resolver: Any) -> None:
        ...


class ChildWorkflowService(Protocol):
    def run_child_step(self, step: Any, context: Any) -> Any:
        ...

    def map_result(self, step: Any, child_result: Any) -> Any:
        ...


class StateService(Protocol):
    def clone_state(self, state: Any) -> Any:
        ...

    def step_runtime_visits(self, store: Any) -> int | None:
        ...

    def increment_step_runtime_state(self, store: Any) -> None:
        ...

    def update_final_step_runtime_state(self, step: Any, store: Any, event: Any) -> None:
        ...

    def update_final_item_runtime_state(self, store: Any, event: Any) -> None:
        ...

    def restore_worklist_selections(self, context: Any, snapshots: Any) -> Any:
        ...

    def ensure_worklist_selection(self, context: Any, worklist_name: str) -> Any:
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
