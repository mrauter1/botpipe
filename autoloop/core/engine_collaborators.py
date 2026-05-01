"""Focused engine collaborators extracted from the monolithic engine."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from .operations import OperationRuntime, bind_operation_runtime

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from pydantic import BaseModel

    from .compiler import CompiledStep
    from .context import Context
    from .engine import Engine
    from .primitives import PendingHandoff
    from .worklists import Selection, SelectionSnapshot


class StepDispatcher:
    """Dispatches one compiled step through the engine execution path."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def execute(
        self,
        step: "CompiledStep",
        context: "Context",
        state: "BaseModel",
        pending_handoffs: tuple["PendingHandoff", ...],
    ) -> Any:
        return self._engine._execute_step(step, context, state, pending_handoffs)


class RouteFinalizer:
    """Owns step finalization entrypoints."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def finalize(self, *args: Any, **kwargs: Any) -> Any:
        return self._engine._finalize_step_result(*args, **kwargs)


class HookRunner:
    """Owns hook execution entrypoints."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def run_after(self, *args: Any, **kwargs: Any) -> Any:
        return self._engine._run_after_hook(*args, **kwargs)

    def run_route(self, *args: Any, **kwargs: Any) -> Any:
        return self._engine._run_route_hook(*args, **kwargs)


class ArtifactGuard:
    """Owns artifact contract enforcement entrypoints."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def enforce(self, *args: Any, **kwargs: Any) -> None:
        self._engine._enforce_artifact_contracts(*args, **kwargs)


class StateRuntime:
    """Owns worklist selection state helpers."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def initialize_worklist_selections(self, context: "Context") -> dict[str, "Selection[Any]"]:
        return self._engine._initialize_worklist_selections(context)

    def restore_worklist_selections(
        self,
        context: "Context",
        snapshots: "Mapping[str, SelectionSnapshot]",
    ) -> dict[str, "Selection[Any]"]:
        return self._engine._restore_worklist_selections(context, snapshots)


class SessionRuntime:
    """Owns session-store state transitions."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def restore(self, snapshot: Any) -> None:
        self._engine.session_store.restore(snapshot)

    def snapshot(self) -> Any:
        return self._engine.session_store.snapshot()


class CheckpointManager:
    """Owns checkpoint persistence entrypoints."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def save(self, *args: Any, **kwargs: Any) -> Any:
        return self._engine._save_checkpoint(*args, **kwargs)


class OperationRecorder:
    """Owns operation-runtime binding for step execution."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    @contextmanager
    def bind_step(
        self,
        *,
        context: "Context",
        run_folder: "Path",
        step_name: str,
        step_visit: int,
    ):
        with bind_operation_runtime(
            OperationRuntime(
                provider=self._engine.provider,
                prompt_registry=self._engine.prompt_registry,
                context=context,
                run_folder=run_folder,
                workflow_name=self._engine.compiled.workflow_name,
                topology_hash=self._engine.compiled.topology_hash,
                source_hash=self._engine.compiled.source_hash,
                step_name=step_name,
                step_visit=step_visit,
                default_session_name=self._engine.compiled.default_session_name,
                replay_mismatch_behavior=self._engine.operation_replay_mismatch_behavior,
                event_sink=self._engine.runtime_event_sink,
            )
        ) as runtime:
            yield runtime


class WorkflowInvoker:
    """Owns child-workflow invocation entrypoints."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def run_child_step(self, step: "CompiledStep", context: "Context") -> Any:
        return self._engine._run_workflow_step(step, context)
