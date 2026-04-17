"""Deterministic workflow execution engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .artifacts import ArtifactHandle, ResolvedArtifacts, resolve_artifact_template
from .compiler import CompiledStep, CompiledWorkflow, compile_workflow
from .context import Context
from .errors import MissingArtifactError, ProviderExecutionError, WorkflowExecutionError
from .primitives import Checkpoint, Event, FAIL, Outcome, PAUSE, SUCCESS
from .prompts import Prompt, PromptRegistry, ResolvedPrompt
from .providers.models import LLMRequest, VerifierRequest, ProducerRequest
from .providers.protocols import LLMProvider
from .stores.protocols import CheckpointStore, SessionBinding, SessionSnapshot, SessionStore


@dataclass(frozen=True, slots=True)
class RunResult:
    """Final run outcome."""

    terminal: str
    state: BaseModel
    history: tuple[str, ...]
    checkpoint: Checkpoint | None = None
    last_event: Event | None = None
    last_outcome: Outcome | None = None


class Engine:
    """Strict workflow engine."""

    def __init__(
        self,
        workflow: type[Any] | CompiledWorkflow,
        *,
        provider: LLMProvider,
        session_store: SessionStore,
        checkpoint_store: CheckpointStore,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self.compiled = workflow if isinstance(workflow, CompiledWorkflow) else compile_workflow(workflow)
        self.provider = provider
        self.session_store = session_store
        self.checkpoint_store = checkpoint_store
        self.prompt_registry = prompt_registry

    def run(
        self,
        *,
        task_id: str,
        run_id: str,
        task_folder: Path,
        run_folder: Path,
        initial_state: BaseModel | None = None,
        resume: bool = False,
        answer: str | None = None,
        max_steps: int = 100,
    ) -> RunResult:
        workflow_instance = self.compiled.workflow_cls()
        history: list[str] = []
        current_step_name: str
        state: BaseModel
        current_answer: str | None

        if resume:
            checkpoint = self.checkpoint_store.load()
            if checkpoint is None:
                raise WorkflowExecutionError("resume requested but no checkpoint is available")
            self.session_store.restore(checkpoint.session_bindings)
            state = checkpoint.state
            current_step_name = checkpoint.stage
            current_answer = answer if answer is not None else checkpoint.pending_answer
        else:
            self.session_store.restore(SessionSnapshot(bindings=(), active_scopes={}))
            state = initial_state if initial_state is not None else self.compiled.new_state()
            context = Context(
                task_id=task_id,
                run_id=run_id,
                task_folder=task_folder,
                run_folder=run_folder,
                state=state,
                session_store=self.session_store,
                answer=None,
            )
            if self.compiled.has_start_hook:
                workflow_instance.on_start(context)
            state = context.state
            current_step_name = self.compiled.entry_step_name
            current_answer = None

        last_event: Event | None = None
        last_outcome: Outcome | None = None
        for _ in range(max_steps):
            context = Context(
                task_id=task_id,
                run_id=run_id,
                task_folder=task_folder,
                run_folder=run_folder,
                state=state,
                session_store=self.session_store,
                answer=current_answer,
            )
            step = self.compiled.steps[current_step_name]
            history.append(step.name)
            try:
                state, destination, last_event, last_outcome = self._execute_step(step, context, state)
            except Exception:
                self._save_checkpoint(
                    stage=current_step_name,
                    state=state,
                    pending_question=None,
                    pending_answer=current_answer,
                )
                raise

            current_answer = None
            if destination == SUCCESS:
                self.checkpoint_store.clear()
                return RunResult(
                    terminal=SUCCESS,
                    state=state,
                    history=tuple(history),
                    checkpoint=None,
                    last_event=last_event,
                    last_outcome=last_outcome,
                )
            if destination == PAUSE:
                checkpoint = self._save_checkpoint(
                    stage=current_step_name,
                    state=state,
                    pending_question=last_event.question if last_event is not None else None,
                    pending_answer=None,
                )
                return RunResult(
                    terminal=PAUSE,
                    state=state,
                    history=tuple(history),
                    checkpoint=checkpoint,
                    last_event=last_event,
                    last_outcome=last_outcome,
                )
            if destination == FAIL:
                checkpoint = self._save_checkpoint(
                    stage=current_step_name,
                    state=state,
                    pending_question=last_event.question if last_event is not None else None,
                    pending_answer=None,
                )
                return RunResult(
                    terminal=FAIL,
                    state=state,
                    history=tuple(history),
                    checkpoint=checkpoint,
                    last_event=last_event,
                    last_outcome=last_outcome,
                )
            current_step_name = destination
        raise WorkflowExecutionError(f"workflow exceeded max_steps={max_steps}")

    def resume(
        self,
        *,
        task_id: str,
        run_id: str,
        task_folder: Path,
        run_folder: Path,
        answer: str | None = None,
        max_steps: int = 100,
    ) -> RunResult:
        return self.run(
            task_id=task_id,
            run_id=run_id,
            task_folder=task_folder,
            run_folder=run_folder,
            resume=True,
            answer=answer,
            max_steps=max_steps,
        )

    def _execute_step(
        self,
        step: CompiledStep,
        context: Context,
        state: BaseModel,
    ) -> tuple[BaseModel, str, Event | None, Outcome | None]:
        context._set_state(state)
        artifacts = self._resolve_artifacts(context)
        self._ensure_required_artifacts(step, artifacts)
        session = self._resolve_session(step, context)
        if step.kind == "pair":
            raw_output, outcome = self._run_pair_step(step, context, artifacts, session)
            event = self._apply_outcome(step, context, artifacts, state, outcome)
            destination = self.compiled.route(step.name, event.tag if event is not None else outcome.tag)
            next_state = (
                state
                if event is not None
                else self._normalize_state(state, self._apply_outcome_handler(step, state, outcome, artifacts))
            )
            return next_state, destination, event or Event(outcome.tag, reason=outcome.reason, question=outcome.question), outcome
        if step.kind == "llm":
            outcome = self._run_llm_step(step, context, artifacts, session)
            event = self._apply_outcome(step, context, artifacts, state, outcome)
            destination = self.compiled.route(step.name, event.tag if event is not None else outcome.tag)
            next_state = (
                state
                if event is not None
                else self._normalize_state(state, self._apply_outcome_handler(step, state, outcome, artifacts))
            )
            return next_state, destination, event or Event(outcome.tag, reason=outcome.reason, question=outcome.question), outcome
        if step.kind == "system":
            if step.system_handler is None:
                raise WorkflowExecutionError(f"system step {step.name!r} has no compiled handler")
            next_state, event = step.system_handler(state, context)
            next_state = self._normalize_state(state, next_state)
            destination = self.compiled.route(step.name, event.tag)
            return next_state, destination, event, None
        raise WorkflowExecutionError(f"unsupported step kind {step.kind!r}")

    def _run_pair_step(
        self,
        step: CompiledStep,
        context: Context,
        artifacts: ResolvedArtifacts,
        session: SessionBinding | None,
    ) -> tuple[str, Outcome]:
        producer_prompt = self._resolve_prompt(step.producer_prompt)
        producer_response = self.provider.run_producer(
            ProducerRequest(
                step_name=step.name,
                prompt=producer_prompt,
                context=context,
                artifacts=artifacts,
                session=session,
            )
        )
        self._persist_session(producer_response.session)
        self._append_logs(step, artifacts, producer_response.raw_output)

        verifier_prompt = self._resolve_prompt(step.verifier_prompt)
        verifier_response = self.provider.run_verifier(
            VerifierRequest(
                step_name=step.name,
                prompt=verifier_prompt,
                raw_output=producer_response.raw_output,
                context=context,
                artifacts=artifacts,
                session=self._select_session(step, context),
            )
        )
        self._persist_session(verifier_response.session)
        self._validate_outcome(verifier_response.outcome)
        return producer_response.raw_output, verifier_response.outcome

    def _run_llm_step(
        self,
        step: CompiledStep,
        context: Context,
        artifacts: ResolvedArtifacts,
        session: SessionBinding | None,
    ) -> Outcome:
        prompt = self._resolve_prompt(step.producer_prompt)
        response = self.provider.run_llm(
            LLMRequest(
                step_name=step.name,
                prompt=prompt,
                context=context,
                artifacts=artifacts,
                session=session,
            )
        )
        self._persist_session(response.session)
        self._validate_outcome(response.outcome)
        self._append_logs(step, artifacts, response.outcome.raw_output)
        return response.outcome

    def _apply_outcome(
        self,
        step: CompiledStep,
        context: Context,
        artifacts: ResolvedArtifacts,
        state: BaseModel,
        outcome: Outcome,
    ) -> Event | None:
        if self.compiled.middleware is None:
            return None
        event = self.compiled.middleware(state, outcome)
        if event is not None and not isinstance(event, Event):
            raise ProviderExecutionError("middleware must return Event or None")
        return event

    def _apply_outcome_handler(
        self,
        step: CompiledStep,
        state: BaseModel,
        outcome: Outcome,
        artifacts: ResolvedArtifacts,
    ) -> BaseModel:
        if step.outcome_handler is None:
            return state
        next_state = step.outcome_handler(state, outcome, artifacts)
        if not isinstance(next_state, BaseModel):
            raise WorkflowExecutionError(f"handler for step {step.name!r} must return a pydantic model")
        return next_state

    def _resolve_session(self, step: CompiledStep, context: Context) -> SessionBinding | None:
        return self._select_session(step, context)

    def _select_session(self, step: CompiledStep, context: Context) -> SessionBinding | None:
        if step.session_name is None:
            return None
        binding = context.get_session(step.session_name)
        if binding is None:
            raise WorkflowExecutionError(
                f"session slot {step.session_name!r} is required by step {step.name!r} but was never opened"
            )
        return binding

    def _persist_session(self, binding: SessionBinding | None) -> None:
        if binding is not None:
            self.session_store.upsert(binding)

    def _append_logs(self, step: CompiledStep, artifacts: ResolvedArtifacts, content: str) -> None:
        for name in step.log_artifacts:
            artifacts[name].append(content)

    def _resolve_artifacts(self, context: Context) -> ResolvedArtifacts:
        handles = {
            name: ArtifactHandle(name=name, path=resolve_artifact_template(artifact.template, context))
            for name, artifact in self.compiled.artifacts.items()
        }
        return ResolvedArtifacts(handles)

    def _ensure_required_artifacts(self, step: CompiledStep, artifacts: ResolvedArtifacts) -> None:
        for name in step.requires:
            if not artifacts[name].exists():
                raise MissingArtifactError(f"required artifact {name!r} does not exist for step {step.name!r}")

    def _resolve_prompt(self, prompt: str | Prompt | None) -> ResolvedPrompt:
        if prompt is None:
            raise WorkflowExecutionError("missing prompt specification")
        if self.prompt_registry is not None:
            return self.prompt_registry.resolve(prompt)
        path = prompt.path if isinstance(prompt, Prompt) else prompt
        return ResolvedPrompt(path=path, text=None)

    def _validate_outcome(self, outcome: Outcome) -> None:
        if not isinstance(outcome, Outcome):
            raise ProviderExecutionError("provider must return Outcome instances")

    def _save_checkpoint(
        self,
        *,
        stage: str,
        state: BaseModel,
        pending_question: str | None,
        pending_answer: str | None,
    ) -> Checkpoint:
        checkpoint = Checkpoint(
            stage=stage,
            state=state,
            session_bindings=self.session_store.snapshot(),
            pending_question=pending_question,
            pending_answer=pending_answer,
        )
        self.checkpoint_store.save(checkpoint)
        return checkpoint

    def _normalize_state(self, current_state: BaseModel, next_state: BaseModel) -> BaseModel:
        expected_cls = type(current_state)
        if not isinstance(next_state, BaseModel):
            raise WorkflowExecutionError(
                f"handler returned {type(next_state)!r}; expected a pydantic model compatible with {expected_cls.__name__}"
            )
        if isinstance(next_state, expected_cls):
            return expected_cls.model_validate(next_state.model_dump(mode="python", warnings=False))
        return expected_cls.model_validate(next_state.model_dump(mode="python", warnings=False))
