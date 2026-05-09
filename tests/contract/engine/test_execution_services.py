from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from botlane.core import FINISH, Workflow
from botlane.core.context import Context, context_runtime
from botlane.core.engine import Engine
from botlane.core.engine_collaborators import (
    ArtifactGuard,
    HookExecutionResult,
    RouteFinalizer,
    StepFinalizationRequest,
)
from botlane.core.execution_services import ExecutionServices
from botlane.core.primitives import Event
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.steps import PythonStep
from botlane.core.stores import InMemoryCheckpointStore, InMemorySessionStore
from tests.contract.engine._shared import _workspace


@dataclass
class _ArtifactServiceStub:
    enforced: list[tuple[tuple[Any, ...], dict[str, Any]]]
    resolved: Any = None

    def resolve_artifacts(self, context: Any) -> Any:
        return self.resolved

    def enforce_artifact_contracts(self, *args: Any, **kwargs: Any) -> None:
        self.enforced.append((args, kwargs))


@dataclass
class _RouteServiceStub:
    compiled_route: Any
    validated: list[str]
    pending_input_calls: list[str]

    def validate_event(self, step: Any, event: Any, *, provider_attributable: bool, error_cls: type[Exception]) -> None:
        del step, provider_attributable, error_cls
        self.validated.append(event.tag)

    def annotate_execution_error(self, exc: Exception, **kwargs: Any) -> Exception:
        del kwargs
        return exc

    def ensure_hook_redirect_limit(self, step: Any, *, candidate_route: str | None, redirects: Any) -> None:
        del step, candidate_route, redirects

    def normalize_direct_runtime_control(self, **kwargs: Any) -> Any:
        raise AssertionError(f"unexpected direct control: {kwargs}")

    def compiled_route_for_step(self, step: Any, route_tag: str) -> Any:
        del step
        if route_tag != self.compiled_route.tag:
            raise AssertionError(route_tag)
        return self.compiled_route

    def event_context_payload(self, event: Any) -> dict[str, Any]:
        return {"tag": event.tag}

    def pending_input_from_event(self, *, source_step: str, event: Any) -> Any:
        self.pending_input_calls.append(f"{source_step}:{event.tag}")
        return None

    def schedule_direct_control_handoffs(self, pending_handoffs: Any, **kwargs: Any) -> Any:
        del kwargs
        return pending_handoffs

    def schedule_route_handoffs(self, pending_handoffs: Any, **kwargs: Any) -> Any:
        del kwargs
        return pending_handoffs


@dataclass
class _HookServiceStub:
    after_calls: list[str]

    def run_after(
        self,
        step: Any,
        context: Any,
        state: Any,
        *,
        artifacts: Any,
        subject: Any,
        candidate_event: Any,
        hook: Any = None,
        hook_phase: str = "after",
    ) -> HookExecutionResult:
        del context, artifacts, subject, candidate_event, hook, hook_phase
        self.after_calls.append(step.name)
        return HookExecutionResult(state=state)

    def run_route(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"unexpected route hook execution: {args} {kwargs}")


@dataclass
class _StateServiceStub:
    updates: list[tuple[str, str]]

    def clone_state(self, state: Any) -> Any:
        return state

    def update_final_step_runtime_state(self, step: Any, store: Any, event: Any) -> None:
        del store
        self.updates.append((step.name, event.tag))

    def update_final_item_runtime_state(self, store: Any, event: Any) -> None:
        del store
        self.updates.append(("item", event.tag))


def _build_step_context(engine: Engine, tmp_path: Path, *, step_name: str) -> tuple[Any, Context]:
    task_folder, run_folder = _workspace(tmp_path)
    workflow_folder = task_folder / f"wf_{engine.compiled.workflow_name}"
    package_folder = tmp_path / "package"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    package_folder.mkdir(parents=True, exist_ok=True)

    step = engine.compiled.steps[step_name]
    context = Context(
        root=tmp_path,
        task_id="task-execution-services",
        run_id="run-execution-services",
        workflow_name=engine.compiled.workflow_name,
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=engine.compiled.new_state(),
        session_store=engine.session_store,
        session_definitions=engine.compiled.sessions,
        worklists=engine.compiled.worklists,
        selections={},
        selection_snapshots={},
        step_name=step.name,
        default_session_name=engine.compiled.default_session_name,
        values={},
    )
    runtime = context_runtime(context)
    runtime.set_worklist_selection_resolver(lambda worklist_name: (_ for _ in ()).throw(AssertionError(worklist_name)))
    step_state_store = engine._ensure_step_state_store({}, step)
    engine._increment_step_runtime_state(step_state_store)
    runtime.set_step_state_store(step_state_store)
    runtime.set_values(context._values)
    runtime.set_meta({"step": {"name": step.name, "kind": step.kind, "visits": 1, "last_route": None}})
    return step, context


def test_artifact_guard_delegates_to_execution_services_artifact_service() -> None:
    artifact_service = _ArtifactServiceStub(enforced=[])
    guard = ArtifactGuard(ExecutionServices(artifacts=artifact_service))

    guard.enforce(
        "step",
        "context",
        "artifacts",
        route_tag="done",
        state="state",
        error_cls=RuntimeError,
        provider_attributable=False,
    )

    assert artifact_service.enforced == [
        (
            ("step", "context", "artifacts"),
            {
                "route_tag": "done",
                "state": "state",
                "error_cls": RuntimeError,
                "provider_attributable": False,
            },
        )
    ]


def test_route_finalizer_capture_runs_against_execution_services(tmp_path: Path) -> None:
    def _finishworkflow_on_finish(ctx: Any) -> Event:
        del ctx
        return Event("done")

    class FinishWorkflow(Workflow):
        class State(BaseModel):
            pass

        finish = PythonStep(name="finish", handler=_finishworkflow_on_finish)
        entry = finish
        transitions = {finish: {"done": FINISH}}

    engine = Engine(
        FinishWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )
    step, context = _build_step_context(engine, tmp_path, step_name="finish")
    route = engine.compiled.routes["finish"]["done"]
    artifact_service = _ArtifactServiceStub(enforced=[], resolved=engine._resolve_artifacts(context))
    route_service = _RouteServiceStub(compiled_route=route, validated=[], pending_input_calls=[])
    hook_service = _HookServiceStub(after_calls=[])
    state_service = _StateServiceStub(updates=[])
    services = ExecutionServices(
        artifacts=artifact_service,
        routes=route_service,
        hooks=hook_service,
        state=state_service,
    )
    finalizer = RouteFinalizer(
        services,
        artifact_inventory=engine.compiled.artifacts_by_qualified_name,
    )

    result = finalizer.capture(
        StepFinalizationRequest(
            step=step,
            context=context,
            state=context.state,
            artifacts=artifact_service.resolved,
            candidate_event=Event("done"),
            after_subject=None,
            pending_handoffs=(),
            error_cls=RuntimeError,
            provider_attributable=False,
        )
    )

    assert result.final_route == "done"
    assert result.destination == FINISH
    assert result.decision is not None
    assert type(result.decision.action).__name__ == "Finish"
    assert route_service.validated == ["done"]
    assert hook_service.after_calls == ["finish"]
    assert len(artifact_service.enforced) == 1
    assert state_service.updates == [("finish", "done"), ("finish", "done"), ("item", "done")]
    assert route_service.pending_input_calls == []
