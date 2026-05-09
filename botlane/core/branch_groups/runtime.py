"""Composite runtime execution for explicit branch groups."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..artifacts import validate_artifact_handle
from ..engine_collaborators import StepExecutionResult, StepFinalizationRequest, run_awaitable_sync
from ..errors import ProviderExecutionError, WorkflowExecutionError
from ..primitives import Event
from .context import BranchMetadata, FanInMetadata, create_branch_context, create_fan_in_context
from .manifest import (
    BranchManifest,
    branch_group_paths,
    branch_manifest_payload,
    build_branch_manifest,
    render_branch_group_context,
    write_branch_group_evidence,
)
from .outcomes import select_branch_group_outcome
from .results import BranchArtifactObservation, BranchResult
from .sessions import BranchSessionStoreView

if TYPE_CHECKING:
    from ..context import Context
    from ..engine import Engine
    from ..primitives import PendingHandoff
    from ..step_plans import StepPlan


class BranchGroupRuntime:
    """Runs one compiled branch-group step as a composite barrier."""

    def __init__(self, engine: "Engine") -> None:
        self._engine = engine

    def run(
        self,
        step: "StepPlan",
        context: "Context",
        state: BaseModel,
        pending_handoffs: tuple["PendingHandoff", ...],
    ) -> StepExecutionResult:
        # Public sync compatibility only. All branch execution remains on run_async()
        # so provider-backed branch/fan-in execution stays async-native.
        return run_awaitable_sync(
            lambda: self.run_async(step, context, state, pending_handoffs),
            active_loop_error="Synchronous branch-group execution cannot bridge async execution inside an active event loop.",
        )

    async def run_async(
        self,
        step: "StepPlan",
        context: "Context",
        state: BaseModel,
        pending_handoffs: tuple["PendingHandoff", ...],
    ) -> StepExecutionResult:
        spec = step.branch_group
        if spec is None:
            raise WorkflowExecutionError(f"branch-group step {step.name!r} is missing compiled branch metadata")
        context._emit_runtime_event(
            "branch_group_started",
            step_name=step.name,
            execution_id=getattr(context, "_step_execution_id", None),
            group_name=spec.name,
            group_kind=spec.kind,
            branch_count=len(spec.branches),
            concurrency=spec.concurrency,
            settle=spec.settle,
        )

        context._set_values(context._values)
        started_at = _utc_now()
        branch_results = await self._run_branches(spec, context=context, state=state)
        finished_at = _utc_now()
        duration_ms = _duration_ms(started_at, finished_at)
        ordered_results = [branch_results[index] for index in range(len(spec.branches))]
        manifest = build_branch_manifest(
            spec=spec,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_ms=duration_ms,
            branches=ordered_results,
        )
        _, results_path, context_path = branch_group_paths(workflow_folder=context.workflow_folder, group_name=spec.name)
        context_text = render_branch_group_context(manifest)
        write_branch_group_evidence(
            results_path=results_path,
            context_path=context_path,
            manifest=manifest,
            context_text=context_text,
        )
        context._emit_runtime_event(
            "branch_manifest_written",
            step_name=step.name,
            execution_id=getattr(context, "_step_execution_id", None),
            group_name=spec.name,
            group_kind=spec.kind,
            results_path=_relative_to_root(results_path, context=context),
            context_path=_relative_to_root(context_path, context=context),
            artifact_paths=[
                _relative_to_root(results_path, context=context),
                _relative_to_root(context_path, context=context),
            ],
        )

        if spec.fan_in_step is not None:
            step_result = await self._run_fan_in(
                composite_step=step,
                spec=spec,
                context=context,
                manifest=manifest,
                results_path=results_path,
                context_path=context_path,
                context_text=context_text,
                pending_handoffs=pending_handoffs,
            )
        else:
            step_result = self._run_mechanical_outcome(
                composite_step=step,
                spec=spec,
                context=context,
                manifest=manifest,
                pending_handoffs=pending_handoffs,
            )

        final_route = None if step_result.transition is None else step_result.transition.final_route
        context._emit_runtime_event(
            "branch_group_completed",
            step_name=step.name,
            execution_id=getattr(context, "_step_execution_id", None),
            group_name=spec.name,
            group_kind=spec.kind,
            route=final_route,
            destination=step_result.destination,
            status=_composite_status(step_result),
            artifact_paths=[
                _relative_to_root(results_path, context=context),
                _relative_to_root(context_path, context=context),
            ],
        )
        return step_result

    async def _run_branches(
        self,
        spec: Any,
        *,
        context: "Context",
        state: BaseModel,
    ) -> dict[int, dict[str, Any]]:
        del state
        results: dict[int, dict[str, Any]] = {}
        branches = tuple(spec.branches)
        concurrency = len(branches) if spec.concurrency is None else max(1, min(spec.concurrency, len(branches)))
        semaphore = asyncio.Semaphore(concurrency)
        completion_queue: asyncio.Queue[tuple[int, dict[str, Any]]] = asyncio.Queue()
        active_tasks: dict[int, asyncio.Task[None]] = {}
        next_branch_index = 0
        stop_launches = False
        async def run_branch_task(branch: Any) -> None:
            try:
                async with semaphore:
                    result = await self._execute_branch(spec, branch, context)
            except asyncio.CancelledError:
                result = _cancelled_branch_result(spec=spec, branch=branch, context=context)
                self._emit_branch_result_event(
                    context=context,
                    spec=spec,
                    branch=branch,
                    result=result,
                    execution_id=None,
                )
            except Exception as exc:  # pragma: no cover - defensive fallback
                result = _unexpected_branch_failure_result(self._engine, spec=spec, branch=branch, exc=exc)
                self._emit_branch_result_event(
                    context=context,
                    spec=spec,
                    branch=branch,
                    result=result,
                    execution_id=None,
                )
            await completion_queue.put((branch.index, result))

        def launch(branch: Any) -> None:
            context._emit_runtime_event(
                "branch_scheduled",
                execution_id=getattr(context, "_step_execution_id", None),
                group_name=spec.name,
                group_kind=spec.kind,
                branch_name=branch.name,
                branch_index=branch.index,
                step_name=branch.step.name,
            )
            active_tasks[branch.index] = asyncio.create_task(
                run_branch_task(branch),
                name=f"branch-group:{spec.name}:{branch.name}",
            )

        while next_branch_index < len(branches) or active_tasks:
            while next_branch_index < len(branches) and not stop_launches and len(active_tasks) < concurrency:
                launch(branches[next_branch_index])
                next_branch_index += 1
            if not active_tasks:
                break

            branch_index, result = await completion_queue.get()
            task = active_tasks.pop(branch_index, None)
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)
            results[branch_index] = result
            if spec.settle == "fail_fast" and result["status"] == "failed" and not stop_launches:
                stop_launches = True
                for active_branch_index, active_task in active_tasks.items():
                    if active_branch_index != branch_index:
                        active_task.cancel()

        if stop_launches:
            for branch in branches[next_branch_index:]:
                skipped_result = _skipped_branch_result(spec=spec, branch=branch, context=context)
                results[branch.index] = skipped_result
                self._emit_branch_result_event(
                    context=context,
                    spec=spec,
                    branch=branch,
                    result=skipped_result,
                    execution_id=None,
                )
        return results

    async def _execute_branch(self, spec: Any, branch: Any, parent_context: "Context") -> dict[str, Any]:
        compiled_step = branch.step
        branch_meta = BranchMetadata(
            name=branch.name,
            index=branch.index,
            group=spec.name,
            input=branch.input,
            count=len(spec.branches),
        )
        session_store = BranchSessionStoreView(
            parent_context._session_store,
            namespace=f"{spec.name}:{branch.name}:{branch.index}",
        )
        step_state_store = compiled_step.step_state_model()
        branch_context = create_branch_context(
            parent_context,
            step_name=compiled_step.name,
            branch=branch_meta,
            session_store=session_store,
            step_state_store=step_state_store,
        )
        branch_context._set_values(parent_context._values)
        self._engine._increment_step_runtime_state(step_state_store)
        branch_context._set_step_state(step_state_store)
        if compiled_step.scope_name is not None:
            raise AssertionError(
                f"branch-group runtime does not support scoped branch step {compiled_step.name!r}; "
                "compile-time validation should have rejected it."
            )
        branch_context._set_meta(
            {
                "step": {
                    "name": compiled_step.name,
                    "kind": compiled_step.kind,
                    "visits": self._engine._step_runtime_visits(step_state_store),
                    "last_route": getattr(step_state_store, "last_route", None),
                }
            }
        )
        execution_id = _branch_execution_id(branch_context)
        branch_context._emit_runtime_event(
            "branch_started",
            group_name=spec.name,
            group_kind=spec.kind,
            branch_name=branch.name,
            branch_index=branch.index,
            step_name=compiled_step.name,
            execution_id=execution_id,
        )
        branch_dir = parent_context.workflow_folder / "_branch_groups" / spec.name / "branches" / branch.name
        started_at = _utc_now()
        try:
            with self._engine.operation_recorder.bind_step(
                step=compiled_step,
                context=branch_context,
                run_folder=branch_context.run_folder,
                step_name=compiled_step.name,
                step_visit=self._engine._step_runtime_visits(step_state_store),
            ):
                step_result = await self._engine.step_dispatcher.execute_async(
                    compiled_step,
                    branch_context,
                    branch_context.state,
                    (),
                    route_mode="capture",
                )
            result = self._branch_result_from_step_result(
                spec=spec,
                branch=branch,
                compiled_step=compiled_step,
                branch_context=branch_context,
                step_result=step_result,
                branch_dir=branch_dir,
                started_at=started_at,
            )
            self._emit_branch_result_event(
                context=branch_context,
                spec=spec,
                branch=branch,
                result=result,
                execution_id=execution_id,
            )
            return result
        except asyncio.CancelledError:
            cancelled_result = _cancelled_branch_result(
                spec=spec,
                branch=branch,
                context=branch_context,
                started_at=started_at,
            )
            self._emit_branch_result_event(
                context=branch_context,
                spec=spec,
                branch=branch,
                result=cancelled_result,
                execution_id=execution_id,
            )
            return cancelled_result
        except Exception as exc:
            failed_result = self._failed_branch_result(
                spec=spec,
                branch=branch,
                compiled_step=compiled_step,
                branch_context=branch_context,
                branch_dir=branch_dir,
                started_at=started_at,
                exc=exc,
            )
            self._emit_branch_result_event(
                context=branch_context,
                spec=spec,
                branch=branch,
                result=failed_result,
                execution_id=execution_id,
            )
            return failed_result

    def _emit_branch_result_event(
        self,
        *,
        context: "Context",
        spec: Any,
        branch: Any,
        result: Mapping[str, Any],
        execution_id: str | None,
    ) -> None:
        event_type = {
            "completed": "branch_completed",
            "failed": "branch_failed",
            "needs_input": "branch_needs_input",
            "cancelled": "branch_cancelled",
            "skipped": "branch_skipped",
        }.get(result["status"], "branch_completed")
        context._emit_runtime_event(
            event_type,
            group_name=spec.name,
            group_kind=spec.kind,
            branch_name=branch.name,
            branch_index=branch.index,
            step_name=branch.step.name,
            execution_id=execution_id,
            route=result.get("route"),
            destination=result.get("destination"),
            status=result["status"],
            reason=result.get("reason"),
            error=result.get("error"),
            artifact_paths=[artifact["path"] for artifact in result.get("artifacts", ())],
        )

    def _branch_result_from_step_result(
        self,
        *,
        spec: Any,
        branch: Any,
        compiled_step: "StepPlan",
        branch_context: "Context",
        step_result: StepExecutionResult,
        branch_dir: Path,
        started_at: datetime,
    ) -> dict[str, Any]:
        finished_at = _utc_now()
        status = "completed"
        route = None if step_result.transition is None else step_result.transition.final_route
        destination = step_result.destination
        runtime_control = None if step_result.transition is None else step_result.transition.runtime_control
        question = None
        reason = None
        error = None
        if runtime_control == "request_input":
            status = "needs_input"
            pending_input = step_result.pending_input
            question = None if pending_input is None else pending_input.question
            reason = None if pending_input is None else pending_input.reason
        elif runtime_control == "fail":
            status = "failed"
            error = {
                "type": "Fail",
                "message": "Branch returned Fail control.",
                "failure_context": None,
                "retry_kind": None,
                "retry_exhausted": False,
            }
        elif step_result.event is not None and step_result.event.tag == "question":
            status = "needs_input"
            question = step_result.event.question
            reason = step_result.event.reason
        elif step_result.event is not None:
            question = step_result.event.question
            reason = step_result.event.reason
        raw_output_path, raw_output_paths = self._write_branch_raw_outputs(
            step_result=step_result,
            branch_dir=branch_dir,
            context=branch_context,
        )
        artifacts = self._collect_branch_artifacts(compiled_step, branch_context)
        provider_session, provider_sessions = self._provider_session_snapshot(compiled_step, branch_context)
        return BranchResult(
            name=branch.name,
            index=branch.index,
            input=branch.input,
            step_name=compiled_step.name,
            status=status,
            route=route,
            destination=destination,
            runtime_control=runtime_control,
            reason=reason,
            question=question,
            artifacts=artifacts,
            raw_output_path=raw_output_path,
            raw_output_paths=raw_output_paths,
            provider_session=provider_session,
            provider_sessions=provider_sessions,
            error=error,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_ms=_duration_ms(started_at, finished_at),
            usage=_serialize_usage(step_result.provider_usage),
        ).to_manifest_dict()

    def _failed_branch_result(
        self,
        *,
        spec: Any,
        branch: Any,
        compiled_step: "StepPlan",
        branch_context: "Context",
        branch_dir: Path,
        started_at: datetime,
        exc: Exception,
    ) -> dict[str, Any]:
        finished_at = _utc_now()
        raw_output_path, raw_output_paths = self._write_branch_raw_outputs(
            step_result=None,
            branch_dir=branch_dir,
            context=branch_context,
        )
        provider_session, provider_sessions = self._provider_session_snapshot(compiled_step, branch_context)
        return BranchResult(
            name=branch.name,
            index=branch.index,
            input=branch.input,
            step_name=compiled_step.name,
            status="failed",
            route=None,
            destination=None,
            runtime_control=None,
            reason=str(exc),
            question=None,
            artifacts=self._collect_branch_artifacts(compiled_step, branch_context),
            raw_output_path=raw_output_path,
            raw_output_paths=raw_output_paths,
            provider_session=provider_session,
            provider_sessions=provider_sessions,
            error=_serialize_exception(self._engine, exc),
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_ms=_duration_ms(started_at, finished_at),
            usage={},
        ).to_manifest_dict()

    def _write_branch_raw_outputs(
        self,
        *,
        step_result: StepExecutionResult | None,
        branch_dir: Path,
        context: "Context",
    ) -> tuple[str | None, dict[str, str]]:
        if step_result is None:
            return None, {}
        raw_paths: dict[str, str] = {}
        primary_path: str | None = None
        if step_result.producer_raw_output is not None:
            producer_path = branch_dir / "producer.txt"
            producer_path.parent.mkdir(parents=True, exist_ok=True)
            producer_path.write_text(step_result.producer_raw_output, encoding="utf-8")
            primary_path = _relative_to_root(producer_path, context=context)
            raw_paths["producer"] = primary_path
        if step_result.verifier_raw_output is not None:
            verifier_path = branch_dir / "verifier.txt"
            verifier_path.parent.mkdir(parents=True, exist_ok=True)
            verifier_path.write_text(step_result.verifier_raw_output, encoding="utf-8")
            relative = _relative_to_root(verifier_path, context=context)
            raw_paths["verifier"] = relative
            if primary_path is None:
                primary_path = relative
        return primary_path, raw_paths

    def _collect_branch_artifacts(self, step: "StepPlan", context: "Context") -> tuple[BranchArtifactObservation, ...]:
        artifacts = self._engine._resolve_artifacts(context)
        branch_artifacts: list[BranchArtifactObservation] = []
        for name in step.writes:
            handle = artifacts[name]
            validation = validate_artifact_handle(handle)
            branch_artifacts.append(
                BranchArtifactObservation(
                    name=handle.name,
                    path=_relative_to_root(handle.path, context=context),
                    kind=None if handle.artifact is None else handle.artifact.kind,
                    exists=handle.exists(),
                    validation="ok" if validation.ok else "failed",
                    validation_errors=tuple(validation.errors),
                )
            )
        return tuple(branch_artifacts)

    def _provider_session_snapshot(self, step: "StepPlan", context: "Context") -> tuple[str | None, dict[str, str]]:
        sessions: dict[str, str] = {}
        if step.session_name is not None:
            binding = context._session_store.get(step.session_name)
            if binding is not None and binding.session_id:
                sessions["producer"] = binding.session_id
        if step.verifier_session_name is not None:
            binding = context._session_store.get(step.verifier_session_name)
            if binding is not None and binding.session_id:
                sessions["verifier"] = binding.session_id
        provider_session = next(iter(sessions.values()), None)
        return provider_session, sessions

    async def _run_fan_in(
        self,
        *,
        composite_step: "StepPlan",
        spec: Any,
        context: "Context",
        manifest: BranchManifest | Mapping[str, Any],
        results_path: Path,
        context_path: Path,
        context_text: str,
        pending_handoffs: tuple["PendingHandoff", ...],
    ) -> StepExecutionResult:
        fan_in_step = spec.fan_in_step
        if fan_in_step is None:
            raise WorkflowExecutionError(f"branch group {spec.name!r} is missing its compiled fan-in step")
        manifest_payload = branch_manifest_payload(manifest)
        manifest_branches = tuple(manifest_payload.get("branches", ()))
        metadata = FanInMetadata(
            results=manifest_payload,
            results_path=results_path,
            context_path=context_path,
            context_text=context_text,
            branch_count=len(manifest_branches),
            completed_count=sum(1 for branch in manifest_branches if branch.get("status") == "completed"),
            failed_count=sum(1 for branch in manifest_branches if branch.get("status") == "failed"),
            needs_input_count=sum(1 for branch in manifest_branches if branch.get("status") == "needs_input"),
            cancelled_count=sum(1 for branch in manifest_branches if branch.get("status") == "cancelled"),
        )
        fan_in_context = create_fan_in_context(
            context,
            step_name=fan_in_step.name,
            fan_in=metadata,
            session_store=context._session_store,
            step_state_store=fan_in_step.step_state_model(),
        )
        fan_in_context._set_values(context._values)
        self._engine._increment_step_runtime_state(fan_in_context._step_state)
        fan_in_context._set_step_state(fan_in_context._step_state)
        fan_in_context._emit_runtime_event(
            "fan_in_started",
            group_name=spec.name,
            group_kind=spec.kind,
            composite_step_name=composite_step.name,
            step_name=fan_in_step.name,
            results_path=_relative_to_root(results_path, context=context),
            context_path=_relative_to_root(context_path, context=context),
            artifact_paths=[
                _relative_to_root(results_path, context=context),
                _relative_to_root(context_path, context=context),
            ],
        )
        with self._engine.operation_recorder.bind_step(
            step=fan_in_step,
            context=fan_in_context,
            run_folder=fan_in_context.run_folder,
            step_name=fan_in_step.name,
            step_visit=self._engine._step_runtime_visits(fan_in_context._step_state),
        ):
            step_result = await self._engine.step_dispatcher.execute_async(
                fan_in_step,
                fan_in_context,
                fan_in_context.state,
                (),
                route_mode="capture",
            )
        fan_in_context._emit_runtime_event(
            "fan_in_completed",
            group_name=spec.name,
            group_kind=spec.kind,
            composite_step_name=composite_step.name,
            step_name=fan_in_step.name,
            route=None if step_result.transition is None else step_result.transition.final_route,
            destination=step_result.destination,
            status=_composite_status(step_result),
            artifact_paths=[
                _relative_to_root(results_path, context=context),
                _relative_to_root(context_path, context=context),
            ],
        )
        return self._map_nested_result_to_composite(
            composite_step=composite_step,
            nested_step=fan_in_step,
            context=context,
            pending_handoffs=pending_handoffs,
            nested_result=step_result,
        )

    def _run_mechanical_outcome(
        self,
        *,
        composite_step: "StepPlan",
        spec: Any,
        context: "Context",
        manifest: BranchManifest | Mapping[str, Any],
        pending_handoffs: tuple["PendingHandoff", ...],
    ) -> StepExecutionResult:
        event = select_branch_group_outcome(spec, manifest, context)
        finalization = self._engine.route_finalizer.finalize_result(
            StepFinalizationRequest(
                step=composite_step,
                context=context,
                state=context.state,
                artifacts=self._engine._resolve_artifacts(context),
                candidate_event=event,
                candidate_route=event.tag,
                candidate_route_present=True,
                after_subject=event,
                pending_handoffs=pending_handoffs,
                error_cls=WorkflowExecutionError,
                provider_attributable=False,
            )
        )
        return self._engine._step_result_from_route_finalization(
            step=composite_step,
            route_finalization=finalization,
        )

    def _map_nested_result_to_composite(
        self,
        *,
        composite_step: "StepPlan",
        nested_step: "StepPlan",
        context: "Context",
        pending_handoffs: tuple["PendingHandoff", ...],
        nested_result: StepExecutionResult,
    ) -> StepExecutionResult:
        finalization = nested_result.transition
        runtime_control = None if finalization is None else finalization.runtime_control
        if runtime_control is not None:
            from ..engine import _RouteControl

            control = _RouteControl(
                control=runtime_control,
                destination=nested_result.destination,
                pending_input=nested_result.pending_input,
                target_step=None if finalization is None else finalization.target_step,
                terminal=None if finalization is None else finalization.terminal,
                source_hook=None if finalization is None else finalization.source_hook,
                source_phase=None if finalization is None else finalization.source_phase,
            )
            return self._engine._step_result_from_direct_control(
                step=composite_step,
                state=nested_result.state,
                control=control,
                pending_handoffs=pending_handoffs,
                producer_raw_output=nested_result.producer_raw_output,
                verifier_raw_output=nested_result.verifier_raw_output,
                provider_usage=nested_result.provider_usage,
            )
        if nested_result.event is None:
            raise WorkflowExecutionError(
                f"fan-in step {nested_step.name!r} completed without a route event or direct runtime control"
            )
        route_finalization = self._engine.route_finalizer.finalize_result(
            StepFinalizationRequest(
                step=composite_step,
                context=context,
                state=nested_result.state,
                artifacts=self._engine._resolve_artifacts(context),
                candidate_event=nested_result.event,
                candidate_route=nested_result.event.tag,
                candidate_route_present=True,
                after_subject=nested_result.outcome or nested_result.event,
                pending_handoffs=pending_handoffs,
                error_cls=ProviderExecutionError
                if finalization is not None and finalization.provider_attributable
                else WorkflowExecutionError,
                provider_attributable=False if finalization is None else finalization.provider_attributable,
                source_hook=None if finalization is None else finalization.source_hook,
                source_phase=None if finalization is None else finalization.source_phase,
            )
        )
        return self._engine._step_result_from_route_finalization(
            step=composite_step,
            route_finalization=route_finalization,
            outcome=nested_result.outcome,
            producer_raw_output=nested_result.producer_raw_output,
            verifier_raw_output=nested_result.verifier_raw_output,
            provider_usage=nested_result.provider_usage,
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _relative_to_root(path: Path, *, context: "Context") -> str:
    try:
        return str(path.resolve().relative_to(context.root.resolve()))
    except ValueError:
        return str(path.resolve())


def _serialize_usage(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    if hasattr(usage, "__dataclass_fields__"):
        return {
            key: value
            for key, value in asdict(usage).items()
            if value is not None
        }
    if isinstance(usage, Mapping):
        return dict(usage)
    return {"value": usage}


def _serialize_exception(engine: "Engine", exc: Exception) -> dict[str, Any]:
    failure_context = engine._failure_context_for_exception(exc)
    retry_kind = engine._retry_kind_for_exception(exc)
    retry_exhausted = False
    if failure_context is not None:
        retry_exhausted = bool(failure_context.details.get("retry_exhausted"))
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "failure_context": None if failure_context is None else failure_context.to_payload(),
        "retry_kind": retry_kind,
        "retry_exhausted": retry_exhausted,
    }


def _branch_execution_id(context: "Context") -> str | None:
    visit = context._step_state.get("visits") if isinstance(context._step_state, dict) else getattr(context._step_state, "visits", None)
    return getattr(context, "_step_execution_id", None) if visit is None else f"{context._step_execution_id.rsplit(':', 1)[0]}:{visit}"


def _cancelled_branch_result(
    *,
    spec: Any,
    branch: Any,
    context: "Context",
    started_at: datetime | None = None,
) -> dict[str, Any]:
    started = _utc_now() if started_at is None else started_at
    finished = _utc_now()
    return BranchResult(
        name=branch.name,
        index=branch.index,
        input=branch.input,
        step_name=branch.step.name,
        status="cancelled",
        route=None,
        destination=None,
        runtime_control=None,
        reason="Cancellation requested after fail_fast.",
        question=None,
        artifacts=(),
        raw_output_path=None,
        raw_output_paths={},
        provider_session=None,
        provider_sessions={},
        error={
            "type": "Cancelled",
            "message": "Branch execution was cancelled before completion.",
            "failure_context": None,
            "retry_kind": None,
            "retry_exhausted": False,
        },
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        duration_ms=_duration_ms(started, finished),
        usage={},
        cancellation_requested=True,
        cancellation_completed=True,
        cancellation_supported=True,
    ).to_manifest_dict()


def _unexpected_branch_failure_result(engine: "Engine", *, spec: Any, branch: Any, exc: Exception) -> dict[str, Any]:
    now = _utc_now().isoformat()
    return BranchResult(
        name=branch.name,
        index=branch.index,
        input=branch.input,
        step_name=branch.step.name,
        status="failed",
        route=None,
        destination=None,
        runtime_control=None,
        reason=str(exc),
        question=None,
        artifacts=(),
        raw_output_path=None,
        raw_output_paths={},
        provider_session=None,
        provider_sessions={},
        error=_serialize_exception(engine, exc),
        started_at=now,
        finished_at=now,
        duration_ms=0,
        usage={},
    ).to_manifest_dict()


def _skipped_branch_result(*, spec: Any, branch: Any, context: "Context") -> dict[str, Any]:
    now = _utc_now().isoformat()
    return BranchResult(
        name=branch.name,
        index=branch.index,
        input=branch.input,
        step_name=branch.step.name,
        status="skipped",
        route=None,
        destination=None,
        runtime_control=None,
        reason="Branch was not scheduled because fail_fast stopped new branch launches.",
        question=None,
        artifacts=(),
        raw_output_path=None,
        raw_output_paths={},
        provider_session=None,
        provider_sessions={},
        error=None,
        started_at=now,
        finished_at=now,
        duration_ms=0,
        usage={},
        cancellation_requested=False,
        cancellation_completed=False,
        cancellation_supported=True,
    ).to_manifest_dict()


def _composite_status(step_result: StepExecutionResult) -> str:
    if step_result.transition is None:
        return "completed"
    if step_result.transition.runtime_control == "request_input":
        return "needs_input"
    if step_result.transition.runtime_control == "fail":
        return "failed"
    if step_result.event is not None and step_result.event.tag == "question":
        return "needs_input"
    return "completed"
