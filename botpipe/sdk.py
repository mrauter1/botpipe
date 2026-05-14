"""Public SDK facade over the filesystem workflow runtime."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
from contextlib import suppress
from collections.abc import AsyncIterator, Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ValidationError, create_model

import botpipe.simple as simple
from botpipe.policy import (
    ModelEffort,
    ModelVerbosity,
    NetworkMode,
    PermissionMode,
    Policy,
    PolicyInput,
    ProviderName,
    ReasoningSummary,
    SandboxMode,
)
from botpipe.core import Workflow as CoreWorkflow
from botpipe.core.artifact_plan import ArtifactSpec
from botpipe.core.artifacts import Artifact, resolve_artifact_template
from botpipe.core.compiler import (
    _compile_single_step_execution_plan,
    _single_step_workflow_name,
    compile_workflow,
    runtime_workflow_validation_message,
)
from botpipe.core.context import Context
from botpipe.core.errors import WorkflowCompilationError, WorkflowExecutionError, WorkflowValidationError, exception_failure_context
from botpipe.core.operations import classify_call, llm_call
from botpipe.core.provider_policy import ProviderPolicy, ProviderPolicyOverride
from botpipe.core.primitives import AWAIT_INPUT, FAIL, FINISH, SELF, Event, Outcome
from botpipe.core.prompts import Prompt
from botpipe.core.providers.protocols import LLMProvider, validate_llm_provider
from botpipe.core.providers.retries import ProviderRetryPolicy
from botpipe.core.schema_registry import CHECKPOINT_SCHEMA
from botpipe.core.steps import BranchGroupStep, ChildWorkflowStep, ProduceVerifyStep, PromptStep, PythonStep, Session, Step
from botpipe.core.step_plans import SingleStepPlan
from botpipe.core.stores.protocols import SessionSnapshot
from botpipe.core.stores.session_store import InMemorySessionStore
from botpipe.core.template_refs import ROOT_STABLE_ARTIFACT_TEMPLATE_BLOCKING_ROOTS
from botpipe.core.workflow_plan import WorkflowPlan
from botpipe.runtime.config import (
    ClaudeProviderConfig,
    CodexProviderConfig,
    ConfigError,
    ProviderConfig,
    ProviderPolicyRuntimeConfig,
    ResolvedRuntimeConfig,
    RuntimeConfig,
    resolve_runtime_config,
)
from botpipe.runtime.loader import (
    WorkflowDiscoveryError,
    WorkflowParameterError as RuntimeWorkflowParameterError,
    WorkflowReference,
    coerce_workflow_parameter_mapping,
    materialize_workflow_params,
    resolve_workflow_reference,
)
from botpipe.runtime.provider_backends import resolve_provider_backend
from botpipe.runtime.provider_policy_resolver import create_provider_policy_resolver
from botpipe.runtime.runner import RunExecution, RunnerOptions, execute_workflow_package, execute_workflow_plan
from botpipe.runtime.stores.filesystem import FilesystemCheckpointStore
from botpipe.runtime.task_ids import TaskIdGenerationError, generate_task_id
from botpipe.runtime.workspace import (
    RunRecord,
    TaskRecord,
    list_run_records,
    list_task_records,
    primary_state_root,
    resolve_run_record,
    resolve_task_workspace,
)


InputResponse = str | BaseModel | Mapping[str, Any] | Sequence[Any] | int | float | bool | None
InputHandler = Callable[["InputRequest"], InputResponse]
_ACTIVE_LOOP_HINT = "Use an async SDK entrypoint instead."
SDK_TASK_SENTINEL_FILENAME = ".botpipe-sdk-task.json"


@dataclass(frozen=True, slots=True)
class RunOptions:
    record_task_message: bool = True


RetentionMode = Literal["keep_all", "delete_task_scratch", "delete_all_sdk_managed"]


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    mode: RetentionMode = "delete_task_scratch"
    keep_declared_writes: bool = True
    keep_workspace_writes: bool = True
    keep_on_failure: bool = True
    keep_on_input_required: bool = True
    keep_on_too_many_pauses: bool = True
    promote_task_writes: bool = True
    promoted_writes_dir: Path | None = None

    @classmethod
    def sdk_default(cls) -> "RetentionPolicy":
        return cls(mode="delete_task_scratch")

    @classmethod
    def keep_all(cls) -> "RetentionPolicy":
        return cls(mode="keep_all")

    @classmethod
    def ephemeral(cls) -> "RetentionPolicy":
        return cls(
            mode="delete_all_sdk_managed",
            keep_declared_writes=False,
            keep_workspace_writes=True,
            keep_on_failure=False,
            keep_on_input_required=False,
            keep_on_too_many_pauses=False,
        )


@dataclass(frozen=True, slots=True)
class ResultArtifact:
    name: str
    path: Path
    kind: str
    schema: type[BaseModel] | dict[str, object] | None = None
    source_path: Path | None = None
    promoted: bool = False
    required: bool = False
    qualified_name: str | None = None

    def exists(self) -> bool:
        return self.path.exists()

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()

    def read_text(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def read_json(self) -> object:
        return json.loads(self.read_text())

    def read_model(self) -> BaseModel:
        if self.schema is None:
            raise TypeError("artifact has no schema")
        if not isinstance(self.schema, type) or not issubclass(self.schema, BaseModel):
            raise TypeError("read_model only supports Pydantic BaseModel schemas")
        return self.schema.model_validate(self.read_json())

    def materialize(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.read_bytes())
        return target


@dataclass(frozen=True, slots=True)
class DeclaredWriteArtifact:
    name: str
    path: Path
    kind: str
    schema: type[BaseModel] | dict[str, object] | None
    required: bool
    qualified_name: str | None


@dataclass(frozen=True, slots=True)
class RetentionInfo:
    policy: RetentionPolicy
    task_scratch_retained: bool
    task_scratch_deleted: bool
    promoted_artifacts: tuple[str, ...]
    retained_task_dir: Path | None


@dataclass(frozen=True, slots=True)
class CleanupResult:
    deleted: tuple[Path, ...]
    skipped: tuple[Path, ...]
    errors: Mapping[Path, str]
    dry_run: bool


class BotpipeSDKError(Exception):
    """Base exception for the public SDK facade."""

    def __init__(self, message: str, *, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class WorkflowInputError(BotpipeSDKError):
    """Raised when SDK workflow input is invalid."""


class WorkflowParameterError(BotpipeSDKError):
    """Raised when SDK workflow params are invalid."""


class SDKExecutionError(BotpipeSDKError):
    """Raised when the SDK cannot execute the requested operation."""

    def __init__(
        self,
        message: str,
        *,
        original_error: Exception | None = None,
        task_dir: Path | None = None,
    ) -> None:
        super().__init__(message, original_error=original_error)
        self.task_dir = task_dir


class InputRequired(BotpipeSDKError):
    """Raised when a workflow pauses and no input handler is configured."""

    def __init__(self, *, request: InputRequest, partial: WorkflowResult) -> None:
        self.request = request
        self.partial = partial
        super().__init__(f"workflow paused awaiting input: {request.question}")


class TooManyPauses(BotpipeSDKError):
    """Raised when the SDK exceeds the configured pause budget."""

    def __init__(self, *, max_pauses: int, partial: WorkflowResult | None) -> None:
        self.max_pauses = max_pauses
        self.partial = partial
        super().__init__(f"workflow exceeded max_pauses={max_pauses}")


class InputResponseValidationError(BotpipeSDKError):
    """Raised when a handler response cannot be serialized or validated on resume."""

    def __init__(
        self,
        *,
        request: InputRequest,
        response: object,
        original_error: Exception,
    ) -> None:
        self.request = request
        self.response = response
        super().__init__(f"input response for {request.question!r} was invalid: {original_error}", original_error=original_error)


@dataclass(frozen=True, slots=True)
class SDKDebugInfo:
    task_id: str
    run_id: str
    task_dir: Path
    workflow_dir: Path
    run_dir: Path
    events_file: Path
    trace_file: Path | None
    checkpoint_file: Path | None


@dataclass(frozen=True, slots=True)
class HandledInput:
    request: InputRequest
    response: object


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    ok: bool
    status: Literal["completed", "failed", "awaiting_input"]
    terminal: str
    state: BaseModel
    output: Any | None
    output_validation_error: str | None
    artifacts: ArtifactMap
    history: tuple[str, ...]
    last_event: Event | None
    last_outcome: Outcome | None
    handled_inputs: tuple[HandledInput, ...]
    debug: SDKDebugInfo
    retention: RetentionInfo | None = None

    @classmethod
    def from_execution(
        cls,
        execution: RunExecution,
        *,
        message: str | None,
        handled_inputs: tuple[HandledInput, ...],
    ) -> WorkflowResult:
        status, ok = _terminal_status(execution.result.terminal)
        return cls(
            ok=ok,
            status=status,
            terminal=execution.result.terminal,
            state=execution.result.state,
            output=execution.result.output,
            output_validation_error=execution.result.output_validation_error,
            artifacts=ArtifactMap(_sdk_result_artifacts(execution, message=message)),
            history=tuple(execution.result.history),
            last_event=execution.result.last_event,
            last_outcome=execution.result.last_outcome,
            handled_inputs=handled_inputs,
            debug=_sdk_debug_info(execution),
            retention=None,
        )

    def artifact(self, name: str) -> ResultArtifact:
        return self.artifacts.require(name)


@dataclass(frozen=True, slots=True)
class InputRequest:
    pending_input_id: str | None
    question: str
    reason: str | None
    best_supposition: str | None
    source_step: str | None
    source_hook: str | None
    source_phase: str | None
    input_schema: dict[str, Any] | None
    input_schema_model: str | None
    pause_index: int
    partial: WorkflowResult

    @classmethod
    def from_execution(
        cls,
        execution: RunExecution,
        *,
        pause_index: int,
        partial: WorkflowResult,
    ) -> InputRequest:
        pending_input = getattr(execution.result.checkpoint, "pending_input", None)
        if pending_input is not None:
            return cls(
                pending_input_id=pending_input.pending_input_id,
                question=pending_input.question,
                reason=pending_input.reason,
                best_supposition=pending_input.best_supposition,
                source_step=pending_input.source_step,
                source_hook=pending_input.source_hook,
                source_phase=pending_input.source_phase,
                input_schema=None if pending_input.input_schema is None else dict(pending_input.input_schema),
                input_schema_model=pending_input.input_schema_model,
                pause_index=pause_index,
                partial=partial,
            )

        last_event = execution.result.last_event
        question = last_event.question if isinstance(last_event, Event) else None
        if not isinstance(question, str) or not question.strip():
            raise SDKExecutionError(
                f"workflow {execution.compiled.workflow_name!r} paused without pending-input metadata or a question event"
            )
        last_transition = execution.result.last_transition
        return cls(
            pending_input_id=None if last_transition is None else last_transition.pending_input_id,
            question=question,
            reason=None if last_event.reason is None else str(last_event.reason),
            best_supposition=None,
            source_step=execution.result.history[-1] if execution.result.history else execution.compiled.entry_step_name,
            source_hook=None if last_transition is None else last_transition.source_hook,
            source_phase=(
                None
                if last_transition is None
                else last_transition.source_phase or ("provider" if last_event.tag == "question" else "route")
            ),
            input_schema=None,
            input_schema_model=None,
            pause_index=pause_index,
            partial=partial,
        )


@dataclass(frozen=True, slots=True)
class StepResult:
    ok: bool
    status: Literal["completed", "failed", "awaiting_input"]
    route: str | None
    value: Any | None
    state: BaseModel
    artifacts: ArtifactMap
    workflow_result: WorkflowResult


class ArtifactMap(Mapping[str, ResultArtifact]):
    """Declared public result artifacts for one SDK workflow result."""

    def __init__(self, handles: Mapping[str, ResultArtifact]) -> None:
        self._handles = dict(handles)

    def __getitem__(self, key: str) -> ResultArtifact:
        return self._handles[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._handles)

    def __len__(self) -> int:
        return len(self._handles)

    def __getattr__(self, name: str) -> ResultArtifact:
        try:
            return self._handles[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def require(self, name: str) -> ResultArtifact:
        return self._handles[name]


class StaticInput:
    def __init__(self, value: InputResponse) -> None:
        self._value = value

    def __call__(self, request: InputRequest) -> InputResponse:
        del request
        return self._value


class BestSuppositionInput:
    def __call__(self, request: InputRequest) -> str:
        if request.best_supposition:
            return request.best_supposition
        raise InputRequired(request=request, partial=request.partial)


class MappingInput:
    def __init__(self, mapping: Mapping[str, InputResponse]) -> None:
        self._mapping = dict(mapping)

    def __call__(self, request: InputRequest) -> InputResponse:
        for key in (request.pending_input_id, request.source_step, request.question):
            if isinstance(key, str) and key in self._mapping:
                return self._mapping[key]
        raise InputRequired(request=request, partial=request.partial)


class ConsoleInput:
    def __call__(self, request: InputRequest) -> str:
        print(request.question)
        if request.reason:
            print(f"Reason: {request.reason}")
        if request.best_supposition:
            print(f"Best supposition: {request.best_supposition}")
        return input("> ")


class Botpipe:
    def __init__(
        self,
        *,
        workspace: str | Path = ".",
        default_policy: PolicyInput = None,
        provider: str | LLMProvider | None = None,
        model: str | None = None,
        model_effort: str | None = None,
        runtime_config: RuntimeConfig | None = None,
        provider_policy_config: ProviderPolicyRuntimeConfig | None = None,
        state_dir: str | Path | None = None,
        retention: RetentionPolicy | None = None,
    ) -> None:
        """Initialize an SDK client rooted at a workspace.

        `workspace` is the actual project or repository working directory, not the
        internal `.botpipe` state directory. `default_policy` is an SDK client-level
        policy layer; unset values inherit from runtime config defaults and system
        defaults at resolution time. Like other public `Policy(...)` layers, it is
        not a hard security cap.
        """

        self.workspace = Path(workspace).resolve()
        self.root = self.workspace
        self.default_policy = _normalize_sdk_policy_input(default_policy, field_name="default_policy")
        resolved_config = resolve_runtime_config(self.root, argparse.Namespace())
        self.runtime_config = runtime_config or resolved_config.runtime
        self.provider_policy_config = provider_policy_config or resolved_config.provider_policy
        self.state_dir = primary_state_root(self.root) if state_dir is None else Path(state_dir).resolve()
        self.retention = retention or RetentionPolicy.sdk_default()
        self._provider_config = _provider_config_with_overrides(
            resolved_config.provider,
            provider=provider,
            model=model,
            model_effort=model_effort,
        )
        self._provider = _resolve_sdk_provider(
            provider=provider,
            provider_config=self._provider_config,
            runtime_config=self.runtime_config,
            provider_policy_config=self.provider_policy_config,
        )
        self.runs = RunsClient(self)
        self.tasks = TasksClient(self)

    def run(
        self,
        workflow: type[object] | str,
        message: str | None = None,
        *,
        policy: PolicyInput = None,
        input: BaseModel | Mapping[str, Any] | None = None,
        params: BaseModel | Mapping[str, Any] | None = None,
        on_input: InputHandler | None = None,
        max_pauses: int = 8,
        max_steps: int | None = None,
        provider_questions: bool | None = None,
        options: RunOptions | None = None,
        retention: RetentionPolicy | None = None,
        on_event: Callable[[Mapping[str, object]], None] | None = None,
    ) -> WorkflowResult:
        """Run one workflow.

        `message` is the task or run request. `input` is typed workflow input, and
        `params` are workflow parameters. `policy` is a per-run policy layer whose
        unset values inherit from SDK client defaults, workflow policy, runtime
        config policy, and system defaults. `provider_questions` is an SDK/runtime
        behavior option for provider-driven pauses; it is distinct from simple
        workflow authoring `control_routes`. `on_event`, when provided, receives
        best-effort copies of the JSONL runtime events after they are durably
        written. `policy` is not a hard security cap.
        """

        if message is not None and not isinstance(message, str):
            raise WorkflowInputError(f"message must be str | None; received {type(message).__name__}")
        if isinstance(max_pauses, bool) or not isinstance(max_pauses, int) or max_pauses < 0:
            raise SDKExecutionError(f"max_pauses must be an integer >= 0; received {max_pauses!r}")
        if options is not None and not isinstance(options, RunOptions):
            raise SDKExecutionError(f"options must be RunOptions | None; received {type(options).__name__}")
        normalized_policy = _normalize_sdk_policy_input(policy)

        resolved, compiled = _resolve_and_compile_workflow(self.root, workflow)
        structured_input = _coerce_sdk_input(compiled, input)
        structured_params = _coerce_sdk_params(resolved.parameters_cls, params, workflow_name=compiled.workflow_name)
        return self._run_compiled_plan(
            compiled,
            reference=resolved.reference,
            message=message,
            structured_input=structured_input,
            structured_params=structured_params,
            on_input=on_input,
            max_pauses=max_pauses,
            max_steps=max_steps,
            provider_questions=provider_questions,
            options=options,
            retention=retention,
            normalized_policy=normalized_policy,
            on_event=on_event,
        )

    def _run_compiled_plan(
        self,
        compiled: WorkflowPlan,
        *,
        reference: WorkflowReference,
        message: str | None,
        structured_input: dict[str, Any] | None,
        structured_params: dict[str, Any],
        on_input: InputHandler | None,
        max_pauses: int,
        max_steps: int | None,
        provider_questions: bool | None,
        options: RunOptions | None,
        retention: RetentionPolicy | None,
        normalized_policy: PolicyInput,
        on_event: Callable[[Mapping[str, object]], None] | None = None,
    ) -> WorkflowResult:
        effective_provider_questions = provider_questions if provider_questions is not None else on_input is not None
        effective_retention = retention or self.retention
        runtime_config = _sdk_runtime_config_with_provider_questions(
            self.runtime_config,
            allow_provider_questions=effective_provider_questions,
        )
        task_id = _generate_sdk_task_id(
            compiled.workflow_name,
            root=self.root,
            state_dir=self.state_dir,
        )
        task_workspace = resolve_task_workspace(self.root, task_id, state_dir=self.state_dir)
        _write_sdk_task_sentinel(
            task_dir=task_workspace.task_dir,
            task_id=task_id,
            policy=effective_retention,
        )
        run_id: str | None = None
        resume = False
        answer: str | None = None
        handled_inputs: list[HandledInput] = []
        last_request: InputRequest | None = None
        result: WorkflowResult | None = None

        for pause_index in range(max_pauses + 1):
            try:
                execution = execute_workflow_plan(
                    compiled,
                    reference=reference,
                    provider=self._provider,
                    options=RunnerOptions(
                        root=self.root,
                        task_id=task_id,
                        run_id=run_id,
                        message=message,
                        resume=resume,
                        answer=answer,
                        state_dir=self.state_dir,
                        max_steps=max_steps,
                        workflow_params=structured_params,
                        workflow_input=structured_input,
                        record_task_message=options.record_task_message if options is not None else True,
                        runtime_config=runtime_config,
                        provider_policy_config=self.provider_policy_config,
                        sdk_default_policy=self.default_policy,
                        run_policy=normalized_policy,
                        event_callback=on_event,
                    ),
                )
            except Exception as exc:
                if resume and last_request is not None and _is_resume_input_validation_error(exc):
                    raise InputResponseValidationError(
                        request=last_request,
                        response=handled_inputs[-1].response,
                        original_error=exc if isinstance(exc, Exception) else Exception(str(exc)),
                    ) from exc
                raise _wrap_sdk_execution_error(
                    exc,
                    workflow_name=compiled.workflow_name,
                    task_dir=task_workspace.task_dir,
                ) from exc

            result = WorkflowResult.from_execution(
                execution,
                message=message,
                handled_inputs=tuple(handled_inputs),
            )
            if result.terminal != AWAIT_INPUT:
                return _apply_retention(
                    execution=execution,
                    result=result,
                    policy=effective_retention,
                    message=message,
                )

            draft_request = InputRequest.from_execution(
                execution,
                pause_index=pause_index,
                partial=result,
            )
            if on_input is None:
                retained_partial = _apply_retention(
                    execution=execution,
                    result=result,
                    policy=effective_retention,
                    message=message,
                )
                request = replace(draft_request, partial=retained_partial)
                raise InputRequired(request=request, partial=retained_partial)

            response = on_input(draft_request)
            try:
                answer = serialize_input_response(response)
            except Exception as exc:
                if isinstance(exc, InputResponseValidationError):
                    raise
                raise InputResponseValidationError(
                    request=draft_request,
                    response=response,
                    original_error=exc if isinstance(exc, Exception) else Exception(str(exc)),
                ) from exc

            handled_inputs.append(HandledInput(request=draft_request, response=response))
            last_request = draft_request
            run_id = execution.run_workspace.run_id
            resume = True

        if result is None:
            raise TooManyPauses(max_pauses=max_pauses, partial=None)
        retained_partial = _apply_retention(
            execution=execution,
            result=result,
            policy=effective_retention,
            message=message,
            too_many_pauses=True,
        )
        raise TooManyPauses(max_pauses=max_pauses, partial=retained_partial)

    def llm(
        self,
        prompt: str | Path | Prompt,
        *,
        returns: Any = str,
        retry: int = 3,
        policy: PolicyInput = None,
    ) -> Any:
        """Run one direct LLM operation.

        `prompt` is the provider instruction for the operation. `policy` is an
        explicit operation policy layer resolved after runtime config defaults and
        the SDK client default policy.
        """
        try:
            return llm_call(
                prompt if isinstance(prompt, Prompt) else prompt,
                returns=returns,
                retry=retry,
                provider=self._provider,
                run_folder=_sdk_operation_dir(self.root, self.state_dir, kind="llm"),
                policy=policy,
                provider_policy_resolver=self._direct_operation_policy_resolver(),
            )
        except Exception as exc:
            raise _wrap_sdk_execution_error(exc, operation_name="llm") from exc

    def classify(
        self,
        prompt: str | Path | Prompt,
        *,
        choices: Sequence[str],
        retry: int = 3,
        policy: PolicyInput = None,
    ) -> str:
        """Run one direct classification operation.

        `prompt` is the provider instruction for the operation. `policy` is an
        explicit operation policy layer resolved after runtime config defaults and
        the SDK client default policy.
        """
        try:
            return classify_call(
                prompt if isinstance(prompt, Prompt) else prompt,
                choices=choices,
                retry=retry,
                provider=self._provider,
                run_folder=_sdk_operation_dir(self.root, self.state_dir, kind="classify"),
                policy=policy,
                provider_policy_resolver=self._direct_operation_policy_resolver(),
            )
        except Exception as exc:
            raise _wrap_sdk_execution_error(exc, operation_name="classify") from exc

    def step(
        self,
        step_def: Step | object,
        message: str | None = None,
        *,
        policy: PolicyInput = None,
        input: BaseModel | Mapping[str, Any] | None = None,
        params: BaseModel | Mapping[str, Any] | None = None,
        routes: Mapping[str, Any] | None = None,
        on_input: InputHandler | None = None,
        max_pauses: int = 8,
        max_steps: int | None = None,
        provider_questions: bool | None = None,
        retention: RetentionPolicy | None = None,
    ) -> StepResult:
        """Run one step through the canonical single-step execution path.

        `policy` applies only to this SDK step invocation. The supplied step object
        is not mutated. `message` is the task or run request. `input` is typed input
        for the single-step invocation when applicable, and `params` are workflow
        parameters for that single-step invocation. `provider_questions` is an
        SDK/runtime behavior option and remains distinct from simple authoring
        `control_routes` on the step definition.
        """

        invocation_policy = _normalize_sdk_policy_input(policy)
        effective_step, workflow_policy = _sdk_step_invocation_layer(step_def, invocation_policy)
        try:
            single_step_plan, workflow_plan = _build_single_step_execution_plan(
                self.root,
                effective_step,
                input,
                params,
                routes=routes,
                workflow_policy=workflow_policy,
            )
            structured_input = _coerce_sdk_input(workflow_plan, input)
            structured_params = _coerce_sdk_params(
                single_step_plan.params_model,
                params,
                workflow_name=workflow_plan.workflow_name,
            )
            workflow_result = self._run_compiled_plan(
                workflow_plan,
                reference=_single_step_workflow_reference(self.root, workflow_plan),
                message=message,
                structured_input=structured_input,
                structured_params=structured_params,
                on_input=on_input,
                max_pauses=max_pauses,
                max_steps=max_steps,
                provider_questions=provider_questions,
                options=None,
                retention=retention,
                normalized_policy=None,
            )
        except Exception as exc:
            if isinstance(exc, WorkflowValidationError):
                message = runtime_workflow_validation_message(exc)
                if message is not None:
                    exc = WorkflowExecutionError(message)
            if isinstance(exc, BotpipeSDKError):
                raise
            raise _wrap_sdk_execution_error(exc, workflow_name=_single_step_workflow_name(effective_step)) from exc

        return StepResult(
            ok=workflow_result.ok,
            status=workflow_result.status,
            route=_step_result_route(workflow_result),
            value=None,
            state=workflow_result.state,
            artifacts=workflow_result.artifacts,
            workflow_result=workflow_result,
        )

    def prompt_step(
        self,
        prompt: str | Prompt,
        message: str | None = None,
        *,
        input: BaseModel | Mapping[str, Any] | None = None,
        name: str = "prompt",
        writes: Sequence[Artifact | simple.ArtifactSpec] = (),
        reads: Sequence[Artifact | str | Path] = (),
        requires: Sequence[Artifact | str | Path] = (),
        routes: Mapping[str, Any] | None = None,
        session: Session | None = None,
        retry: int | ProviderRetryPolicy | None = None,
        policy: PolicyInput = None,
        on_input: InputHandler | None = None,
        max_pauses: int = 8,
        max_steps: int | None = None,
        provider_questions: bool | None = None,
        retention: RetentionPolicy | None = None,
    ) -> StepResult:
        """Build and run one prompt step.

        `prompt` is the provider instruction for the step, while `message` is the
        task or run request. `policy` attaches to the constructed step as its
        authored policy before invocation-local layering.
        """
        step_def = PromptStep(
            name=name,
            producer=_normalize_prompt(prompt),
            writes=_normalize_sdk_writes(name, writes),
            reads=reads,
            requires=requires,
            route_metadata=None,
            session=session,
            retry_policy=_normalize_retry_policy(retry),
            provider_policy=_normalize_sdk_policy_input(policy),
        )
        return self.step(
            step_def,
            message=message,
            routes=routes,
            on_input=on_input,
            max_pauses=max_pauses,
            max_steps=max_steps,
            provider_questions=provider_questions,
            retention=retention,
            input=input,
        )

    def produce_verify_step(
        self,
        *,
        producer: str | Prompt,
        verifier: str | Prompt,
        message: str | None = None,
        input: BaseModel | Mapping[str, Any] | None = None,
        name: str = "produce_verify",
        writes: Sequence[Artifact | simple.ArtifactSpec] = (),
        verifier_writes: Sequence[Artifact | simple.ArtifactSpec] = (),
        reads: Sequence[Artifact | str | Path] = (),
        requires: Sequence[Artifact | str | Path] = (),
        verifier_requires: Sequence[Artifact | str | Path] = (),
        routes: Mapping[str, Any] | None = None,
        session: Session | None = None,
        verifier_session: Session | None = None,
        retry: int | ProviderRetryPolicy | None = None,
        policy: PolicyInput = None,
        on_input: InputHandler | None = None,
        max_pauses: int = 8,
        max_steps: int | None = None,
        provider_questions: bool | None = None,
        retention: RetentionPolicy | None = None,
    ) -> StepResult:
        """Build and run one produce/verify step.

        `producer` and `verifier` are provider instructions, while `message` is the
        task or run request. `policy` attaches to the constructed step as its
        authored policy before invocation-local layering.
        """
        step_def = ProduceVerifyStep(
            name=name,
            producer=_normalize_prompt(producer),
            verifier=_normalize_prompt(verifier),
            producer_writes=_normalize_sdk_writes(name, writes),
            verifier_writes=_normalize_sdk_writes(name, verifier_writes),
            reads=reads,
            requires=requires,
            verifier_requires=verifier_requires,
            session=session,
            verifier_session=verifier_session,
            retry_policy=_normalize_retry_policy(retry),
            provider_policy=_normalize_sdk_policy_input(policy),
        )
        return self.step(
            step_def,
            message=message,
            routes=routes,
            on_input=on_input,
            max_pauses=max_pauses,
            max_steps=max_steps,
            provider_questions=provider_questions,
            retention=retention,
            input=input,
        )

    def python_step(
        self,
        handler: Callable[..., Any],
        message: str | None = None,
        *,
        input: BaseModel | Mapping[str, Any] | None = None,
        name: str = "python",
        writes: Sequence[Artifact | simple.ArtifactSpec] = (),
        reads: Sequence[Artifact | str | Path] = (),
        requires: Sequence[Artifact | str | Path] = (),
        routes: Mapping[str, Any] | None = None,
        policy: PolicyInput = None,
        on_input: InputHandler | None = None,
        max_pauses: int = 8,
        max_steps: int | None = None,
        retention: RetentionPolicy | None = None,
    ) -> StepResult:
        """Build and run one Python step.

        `message` is the task or run request for the single-step invocation. `policy`
        attaches to the constructed step as its authored provider-operation policy.
        """
        step_def = PythonStep(
            name=name,
            handler=handler,
            writes=_normalize_sdk_writes(name, writes),
            reads=reads,
            requires=requires,
            provider_policy=_normalize_sdk_policy_input(policy),
        )
        return self.step(
            step_def,
            message=message,
            routes=routes,
            on_input=on_input,
            max_pauses=max_pauses,
            max_steps=max_steps,
            retention=retention,
            input=input,
        )

    def workflow_step(
        self,
        workflow: type[CoreWorkflow] | str,
        message: str | None = None,
        *,
        input: BaseModel | Mapping[str, Any] | None = None,
        child_message: str | None = None,
        name: str = "workflow",
        params: BaseModel | Mapping[str, Any] | None = None,
        writes: Sequence[Artifact | simple.ArtifactSpec] = (),
        reads: Sequence[Artifact | str | Path] = (),
        requires: Sequence[Artifact | str | Path] = (),
        routes: Mapping[str, Any] | None = None,
        policy: PolicyInput = None,
        on_input: InputHandler | None = None,
        max_pauses: int = 8,
        max_steps: int | None = None,
        provider_questions: bool | None = None,
        retention: RetentionPolicy | None = None,
    ) -> StepResult:
        """Build and run one child-workflow step.

        `message` is the outer task or run request for the single-step invocation.
        `child_message` is the child workflow request when it differs. `policy`
        attaches to the constructed child-workflow step as its authored policy.
        """
        step_def = ChildWorkflowStep(
            name=name,
            workflow=workflow,
            message=message if child_message is None else child_message,
            input=input,
            params=_materialize_child_workflow_params(params),
            writes=_normalize_sdk_writes(name, writes),
            reads=reads,
            requires=requires,
            provider_policy=_normalize_sdk_policy_input(policy),
        )
        return self.step(
            step_def,
            message=message,
            routes=routes,
            on_input=on_input,
            max_pauses=max_pauses,
            max_steps=max_steps,
            provider_questions=provider_questions,
            retention=retention,
            input=input,
        )

    def cleanup(
        self,
        *,
        older_than: timedelta | None = None,
        include_failed: bool = False,
        dry_run: bool = False,
    ) -> CleanupResult:
        return self.tasks.cleanup(older_than=older_than, include_failed=include_failed, dry_run=dry_run)

    def _direct_operation_policy_resolver(self):
        return create_provider_policy_resolver(
            sdk_default_policy=self.default_policy,
            workflow_policy=None,
            run_policy=None,
            workspace_root=self.root,
            provider_policy=self.provider_policy_config,
            runtime=self.runtime_config,
            provider=self._provider_config,
        )


class RunsClient:
    """Durable run operations exposed through ``client.runs``."""

    def __init__(self, client: Botpipe) -> None:
        self._client = client

    def list(
        self,
        *,
        workflow: type[object] | str | None = None,
        task_id: str | None = None,
        status: str | None = None,
    ) -> tuple[RunRecord, ...]:
        if workflow is None:
            return list_run_records(self._client.root, workflow_name=None, task_id=task_id, status=status)
        resolved, compiled = _resolve_and_compile_workflow(self._client.root, workflow)
        records = list_run_records(
            self._client.root,
            workflow_name=resolved.reference.workflow_name,
            task_id=task_id,
            status=status,
        )
        return tuple(_record_with_checkpoint_loadability(record, compiled) for record in records)

    def show(
        self,
        workflow: type[object] | str,
        task_id: str,
        *,
        run_id: str | None = None,
    ) -> RunRecord:
        resolved, compiled = _resolve_and_compile_workflow(self._client.root, workflow)
        record = _resolve_sdk_run_record(
            self._client.root,
            workflow_name=resolved.reference.workflow_name,
            task_id=task_id,
            run_id=run_id,
            selector="latest",
        )
        return _record_with_checkpoint_loadability(record, compiled)

    def repair(
        self,
        workflow: type[object] | str,
        task_id: str,
        *,
        run_id: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Reconstruct a missing or invalid checkpoint from durable trace state snapshots when possible."""

        resolved, compiled = _resolve_and_compile_workflow(self._client.root, workflow)
        workflow_name = resolved.reference.workflow_name
        record = _resolve_sdk_run_record(
            self._client.root,
            workflow_name=workflow_name,
            task_id=task_id,
            run_id=run_id,
            selector="latest",
        )
        return _repair_run_checkpoint_from_trace(record, compiled=compiled, force=force)

    def resume(
        self,
        workflow: type[object] | str,
        task_id: str,
        *,
        run_id: str | None = None,
        answer: InputResponse = None,
        max_steps: int | None = None,
        provider_questions: bool | None = None,
        policy: PolicyInput = None,
        on_event: Callable[[Mapping[str, object]], None] | None = None,
    ) -> WorkflowResult:
        """Resume an existing durable run and return the SDK result object.

        `on_event`, when provided, receives best-effort copies of the JSONL
        runtime events after they are durably written.
        """

        normalized_policy = _normalize_sdk_policy_input(policy)
        resolved, compiled = _resolve_and_compile_workflow(self._client.root, workflow)
        workflow_name = resolved.reference.workflow_name
        if answer is None and run_id is None:
            record = _resolve_latest_loadable_resume_run(
                self._client.root,
                workflow_name=workflow_name,
                task_id=task_id,
                compiled=compiled,
            )
        else:
            selector = "latest_paused" if answer is not None else "latest"
            record = _resolve_sdk_run_record(
                self._client.root,
                workflow_name=workflow_name,
                task_id=task_id,
                run_id=run_id,
                selector=selector,
            )
        if answer is None and record.running_live:
            raise _sdk_resolution_error(
                f"run {record.run_id!r} for workflow {workflow_name!r} on task {task_id!r} is still running "
                f"(pid={record.lease.get('pid')!r}, host={record.lease.get('host')!r}); stop the live process "
                "or wait for it to finish before resuming"
            )
        if answer is None:
            checkpoint_load_error = _checkpoint_load_error(record, compiled)
            if checkpoint_load_error is not None:
                diagnostic_record = (
                    _record_with_checkpoint_loadability(record, compiled)
                    if record.checkpoint_error is None
                    else record
                )
                raise _sdk_resolution_error(
                    _non_resumable_run_message(
                        diagnostic_record,
                        workflow_name=workflow_name,
                        task_id=task_id,
                        checkpoint_load_error=diagnostic_record.checkpoint_load_error or checkpoint_load_error,
                    )
                )
        if answer is not None and not record.paused:
            raise _sdk_resolution_error(
                f"run {record.run_id!r} for workflow {workflow_name!r} on task {task_id!r} is not awaiting input"
            )

        runtime_config = self._client.runtime_config
        if provider_questions is not None:
            runtime_config = _sdk_runtime_config_with_provider_questions(
                runtime_config,
                allow_provider_questions=provider_questions,
            )
        try:
            execution = execute_workflow_package(
                workflow,
                provider=self._client._provider,
                options=RunnerOptions(
                    root=self._client.root,
                    task_id=task_id,
                    run_id=record.run_id,
                    resume=True,
                    answer=None if answer is None else serialize_input_response(answer),
                    state_dir=self._client.state_dir,
                    max_steps=max_steps if max_steps is not None else self._client.runtime_config.max_steps,
                    runtime_config=runtime_config,
                    provider_policy_config=self._client.provider_policy_config,
                    sdk_default_policy=self._client.default_policy,
                    run_policy=normalized_policy,
                    event_callback=on_event,
                ),
            )
        except Exception as exc:
            raise _wrap_sdk_execution_error(exc, workflow_name=workflow_name, task_dir=record.task_dir) from exc

        return WorkflowResult.from_execution(execution, message=None, handled_inputs=())

    def events(
        self,
        workflow: type[object] | str,
        task_id: str | None = None,
        *,
        run_id: str | None = None,
        follow: bool = False,
        poll_interval: float = 0.2,
    ) -> AsyncIterator[dict[str, Any]]:
        record = self._select_log_run(workflow, task_id, run_id=run_id)
        return _iter_jsonl_records(record.events_file, label="events", follow=follow, poll_interval=poll_interval)

    def trace(
        self,
        workflow: type[object] | str,
        task_id: str | None = None,
        *,
        run_id: str | None = None,
        follow: bool = False,
        poll_interval: float = 0.2,
    ) -> AsyncIterator[dict[str, Any]]:
        record = self._select_log_run(workflow, task_id, run_id=run_id)
        return _iter_jsonl_records(record.trace_file, label="trace", follow=follow, poll_interval=poll_interval)

    def events_text(self, workflow: type[object] | str, task_id: str, *, run_id: str | None = None) -> str:
        return _read_run_log_text(self.show(workflow, task_id, run_id=run_id).events_file, "events")

    def trace_text(self, workflow: type[object] | str, task_id: str, *, run_id: str | None = None) -> str:
        return _read_run_log_text(self.show(workflow, task_id, run_id=run_id).trace_file, "trace")

    def _select_log_run(
        self,
        workflow_or_task_id: type[object] | str,
        task_id: str | None,
        *,
        run_id: str | None,
    ) -> RunRecord:
        if task_id is not None:
            return self.show(workflow_or_task_id, task_id, run_id=run_id)
        if not isinstance(workflow_or_task_id, str):
            raise SDKExecutionError("task-only run lookup requires a task id string")

        records = list_run_records(self._client.root, task_id=workflow_or_task_id)
        if run_id is not None:
            records = tuple(record for record in records if record.run_id == run_id)
        if not records:
            suffix = f" with run id {run_id!r}" if run_id is not None else ""
            raise _sdk_resolution_error(f"no run exists for task {workflow_or_task_id!r}{suffix}")
        if len(records) > 1:
            raise SDKExecutionError(
                f"task-only run lookup for task {workflow_or_task_id!r} is ambiguous; pass workflow and/or run_id"
            )
        return records[0]


class TasksClient:
    """Durable task operations exposed through ``client.tasks``."""

    def __init__(self, client: Botpipe) -> None:
        self._client = client

    def list(self, *, task_ids: str | Iterable[str] | None = None) -> tuple[TaskRecord, ...]:
        return list_task_records(self._client.root, task_ids=task_ids)

    def cleanup(
        self,
        *,
        older_than: timedelta | None = None,
        include_failed: bool = False,
        dry_run: bool = False,
    ) -> CleanupResult:
        tasks_roots = tuple(root for root in _sdk_readable_tasks_roots(self._client.root, self._client.state_dir) if root.is_dir())
        if not tasks_roots:
            return CleanupResult(deleted=(), skipped=(), errors={}, dry_run=dry_run)

        now = datetime.now(timezone.utc)
        deleted: list[Path] = []
        skipped: list[Path] = []
        errors: dict[Path, str] = {}
        seen_task_dirs: set[Path] = set()
        for tasks_root in tasks_roots:
            for task_dir in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
                resolved_task_dir = task_dir.resolve()
                if resolved_task_dir in seen_task_dirs:
                    continue
                seen_task_dirs.add(resolved_task_dir)
                try:
                    payload = _load_sdk_task_sentinel(task_dir)
                except SDKExecutionError:
                    skipped.append(task_dir)
                    continue
                if payload.get("schema") != "botpipe.sdk_task/v1":
                    skipped.append(task_dir)
                    continue
                if payload.get("generated_by") != "botpipe.sdk":
                    skipped.append(task_dir)
                    continue
                if payload.get("task_id") != task_dir.name:
                    skipped.append(task_dir)
                    continue
                if older_than is not None and now - _sdk_task_created_at(task_dir) < older_than:
                    skipped.append(task_dir)
                    continue
                if not include_failed and _task_dir_appears_failed_or_awaiting_input(task_dir):
                    skipped.append(task_dir)
                    continue
                if dry_run:
                    deleted.append(task_dir)
                    continue
                try:
                    _safe_delete_sdk_task_dir(
                        task_dir=task_dir,
                        task_id=task_dir.name,
                        tasks_root=tasks_root,
                    )
                except SDKExecutionError as exc:
                    errors[task_dir] = str(exc)
                    skipped.append(task_dir)
                    continue
                deleted.append(task_dir)

        return CleanupResult(
            deleted=tuple(deleted),
            skipped=tuple(skipped),
            errors=errors,
            dry_run=dry_run,
        )


def serialize_input_response(value: InputResponse) -> str:
    try:
        if isinstance(value, BaseModel):
            return json.dumps(value.model_dump(mode="json"), ensure_ascii=False)
        if isinstance(value, Mapping):
            return json.dumps(dict(value), ensure_ascii=False)
        if isinstance(value, tuple):
            return json.dumps(list(value), ensure_ascii=False)
        if isinstance(value, list):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, (int, float, bool)) or value is None:
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, str):
            return value
    except Exception as exc:
        raise exc
    raise TypeError(f"unsupported input response type: {type(value).__name__}")


def _resolve_sdk_workflow_name(root: Path, workflow: type[object] | str) -> str:
    try:
        return resolve_workflow_reference(root, workflow).reference.workflow_name
    except WorkflowDiscoveryError as exc:
        raise SDKExecutionError(str(exc), original_error=exc) from exc


def _resolve_sdk_run_record(
    root: Path,
    *,
    workflow_name: str,
    task_id: str,
    run_id: str | None,
    selector: str,
) -> RunRecord:
    try:
        return resolve_run_record(root, workflow_name=workflow_name, task_id=task_id, run_id=run_id, selector=selector)
    except FileNotFoundError as exc:
        raise SDKExecutionError(str(exc), original_error=exc) from exc


def _sdk_resolution_error(message: str) -> SDKExecutionError:
    return SDKExecutionError(message, original_error=FileNotFoundError(message))


def _non_resumable_run_message(
    record: RunRecord,
    *,
    workflow_name: str,
    task_id: str,
    checkpoint_load_error: str | None = None,
) -> str:
    details = [
        f"run {record.run_id!r} for workflow {workflow_name!r} on task {task_id!r} is not resumable",
        f"status={record.normalized_status!r}",
        f"checkpoint_exists={record.checkpoint_exists}",
        f"checkpoint_valid={record.checkpoint_valid}",
    ]
    if record.checkpoint_error is not None:
        details.append(f"checkpoint_error={record.checkpoint_error!r}")
    if checkpoint_load_error is not None:
        details.append(f"checkpoint_load_error={checkpoint_load_error!r}")
    if record.stale_running:
        details.append("running_state=stale")
    last_event = record.last_event
    if last_event is not None:
        last_bits = {
            key: last_event.get(key)
            for key in ("event_type", "step_name", "step_execution_id", "scope", "item_id", "turn_kind", "attempt")
            if last_event.get(key) is not None
        }
        if last_bits:
            details.append(f"last_event={last_bits!r}")
    details.append("start a new run or recover from artifacts/events if no checkpoint exists")
    return "; ".join(details)


def _repair_run_checkpoint_from_trace(
    record: RunRecord,
    *,
    compiled: WorkflowPlan,
    force: bool,
) -> dict[str, Any]:
    if record.running_live:
        raise _sdk_resolution_error(
            f"run {record.run_id!r} for workflow {record.workflow_name!r} on task {record.task_id!r} is still running "
            f"(pid={record.lease.get('pid')!r}, host={record.lease.get('host')!r}); stop the live process "
            "or wait for it to finish before repairing"
        )
    checkpoint_load_error = None
    if record.checkpoint_error is None:
        checkpoint_load_error = _checkpoint_load_error(record, compiled)
    if record.checkpoint_error is None and checkpoint_load_error is None and not force:
        return {
            "checkpoint_exists": record.checkpoint_exists,
            "checkpoint_valid": True,
            "reason": "checkpoint_already_valid",
            "repaired": False,
            "run_id": record.run_id,
            "task_id": record.task_id,
            "workflow": record.workflow_name,
        }

    candidate = _checkpoint_repair_candidate(record)
    unsupported_reason = _checkpoint_repair_unsupported_reason(compiled=compiled, candidate=candidate)
    if unsupported_reason is not None:
        raise _sdk_resolution_error(f"cannot repair run {record.run_id!r}: {unsupported_reason}")
    stage = candidate["stage"]
    if stage not in compiled.steps:
        raise _sdk_resolution_error(
            f"cannot repair run {record.run_id!r}: trace points to undeclared step {stage!r} "
            f"for workflow {record.workflow_name!r}"
        )
    try:
        state = compiled.state_cls.model_validate(candidate["state"])
    except ValidationError as exc:
        raise _sdk_resolution_error(
            f"cannot repair run {record.run_id!r}: trace state snapshot does not match "
            f"workflow state model {compiled.state_cls.__qualname__}"
        ) from exc
    warnings = list(candidate.get("warnings", ()))
    payload: dict[str, Any] = {
        "schema": CHECKPOINT_SCHEMA,
        "stage": stage,
        "state": state.model_dump(mode="json", warnings=False),
        "session_bindings": {
            "bindings": [],
            "active_keys_by_slot": {},
            "active_scopes": {},
        },
        "values": {},
        "step_states": {},
        "item_states": {},
        "step_item_states": {},
        "worklist_selections": {},
        "pending_handoffs": [],
        "pending_input": None,
        "pending_answer": None,
        "failure_context": {
            "kind": "checkpoint_repaired_from_trace",
            "trace_event_type": candidate["trace_event_type"],
            "trace_sequence": candidate.get("trace_sequence"),
            "warnings": warnings,
        },
        "resume_cursor": candidate.get("resume_cursor"),
    }
    _atomic_write_json(record.checkpoint_file, payload)
    verified = _resolve_sdk_run_record(
        record.root,
        workflow_name=record.workflow_name,
        task_id=record.task_id,
        run_id=record.run_id,
        selector="latest",
    )
    if not verified.checkpoint_valid:
        raise _sdk_resolution_error(
            f"repair wrote checkpoint for run {record.run_id!r}, but it is still invalid: "
            f"{verified.checkpoint_error}"
        )
    load_error = _checkpoint_load_error(verified, compiled)
    if load_error is not None:
        raise _sdk_resolution_error(
            f"repair wrote checkpoint for run {record.run_id!r}, but it cannot be loaded: {load_error}"
        )
    return {
        "checkpoint_file": str(record.checkpoint_file),
        "checkpoint_valid": True,
        "repaired": True,
        "resume_cursor": candidate.get("resume_cursor"),
        "run_id": record.run_id,
        "stage": stage,
        "task_id": record.task_id,
        "trace_event_type": candidate["trace_event_type"],
        "warnings": warnings,
        "workflow": record.workflow_name,
    }


def _checkpoint_repair_candidate(record: RunRecord) -> dict[str, Any]:
    trace_records = _read_jsonl_records(record.trace_file, label="trace")
    for trace in reversed(trace_records):
        event_type = trace.get("event_type")
        if event_type == "step_finished":
            terminal = trace.get("terminal")
            if isinstance(terminal, str) and terminal:
                raise _sdk_resolution_error(
                    f"cannot repair run {record.run_id!r}: latest traced step is terminal {terminal!r}"
                )
            stage = trace.get("target_step") if isinstance(trace.get("target_step"), str) else trace.get("step_name")
            state_payload = trace.get("state_after")
            if isinstance(stage, str) and stage and isinstance(state_payload, dict):
                return {
                    "stage": stage,
                    "state": state_payload,
                    "trace_event_type": "step_finished",
                    "trace_sequence": trace.get("sequence"),
                    "scope": trace.get("scope"),
                    "item_id": trace.get("item_id"),
                    "warnings": _checkpoint_repair_warnings(trace),
                }
        elif event_type == "step_started":
            stage = trace.get("step_name")
            state_payload = trace.get("state")
            if isinstance(stage, str) and stage and isinstance(state_payload, dict):
                return {
                    "stage": stage,
                    "state": state_payload,
                    "trace_event_type": "step_started",
                    "trace_sequence": trace.get("sequence"),
                    "resume_cursor": _repair_resume_cursor_from_events(
                        record.events_file,
                        step_name=stage,
                        step_execution_id=trace.get("step_execution_id"),
                    ),
                    "scope": trace.get("scope"),
                    "item_id": trace.get("item_id"),
                    "warnings": _checkpoint_repair_warnings(trace),
                }
    raise _sdk_resolution_error(
        f"cannot repair run {record.run_id!r}: trace log does not contain a step state snapshot"
    )


def _checkpoint_repair_warnings(trace: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    if trace.get("scope") is not None or trace.get("item_id") is not None:
        warnings.append(
            "checkpoint was reconstructed from workflow state only; verify scoped worklist state before resuming"
        )
    return warnings


def _checkpoint_repair_unsupported_reason(*, compiled: WorkflowPlan, candidate: Mapping[str, Any]) -> str | None:
    if compiled.worklists:
        return "repair from trace is unsafe for workflows with worklists because scoped item state cannot be reconstructed"
    if _workflow_has_repair_unsafe_sessions(compiled):
        return "repair from trace is unsafe for workflows with declared or open sessions because session bindings cannot be reconstructed"
    if candidate.get("scope") is not None or candidate.get("item_id") is not None:
        return "trace snapshot is scoped to a worklist item and cannot reconstruct item/worklist state"
    return None


def _workflow_has_repair_unsafe_sessions(compiled: WorkflowPlan) -> bool:
    if compiled.default_session_open:
        return True
    for name, session in compiled.sessions.items():
        if name != compiled.default_session_name:
            return True
        if bool(getattr(session, "open", False)):
            return True
    return False


def _checkpoint_load_error(record: RunRecord, compiled: WorkflowPlan) -> str | None:
    shallow_error = record.checkpoint_error
    if shallow_error is not None:
        return shallow_error
    try:
        checkpoint = FilesystemCheckpointStore(record.checkpoint_file, compiled.state_cls).load()
    except Exception as exc:
        return str(exc)
    if checkpoint is None:
        return "checkpoint payload could not be loaded"
    stage = checkpoint.stage
    if not isinstance(stage, str) or not stage:
        return "resume checkpoint does not declare the step to continue"
    if stage not in compiled.steps:
        return f"resume checkpoint refers to step {stage!r}, but the current workflow does not declare that step"
    cursor = checkpoint.resume_cursor
    if cursor is None:
        return None
    if cursor.get("phase") != "provider_attempt":
        return f"resume checkpoint declares unsupported resume phase {cursor.get('phase')!r}"
    cursor_step = cursor.get("step_name")
    if cursor_step != stage:
        return f"resume checkpoint provider-attempt cursor refers to step {cursor_step!r}, but stage is {stage!r}"
    return None


def _record_with_checkpoint_loadability(record: RunRecord, compiled: WorkflowPlan) -> RunRecord:
    metadata = dict(record.metadata)
    metadata.pop("checkpoint_load_error", None)
    if record.checkpoint_error is None:
        load_error = _checkpoint_load_error(record, compiled)
        if load_error is not None:
            metadata["checkpoint_load_error"] = load_error
    return replace(record, metadata=metadata)


def _resolve_latest_loadable_resume_run(
    root: Path,
    *,
    workflow_name: str,
    task_id: str,
    compiled: WorkflowPlan,
) -> RunRecord:
    records = tuple(
        _record_with_checkpoint_loadability(record, compiled)
        for record in list_run_records(root, workflow_name=workflow_name, task_id=task_id)
    )
    candidates = tuple(record for record in records if record.resumable)
    if not candidates:
        raise _sdk_resolution_error(f"no resumable run exists for workflow {workflow_name!r} on task {task_id!r}")
    return max(candidates, key=lambda record: record.sort_key)


def _repair_resume_cursor_from_events(
    events_file: Path,
    *,
    step_name: str,
    step_execution_id: object,
) -> dict[str, Any] | None:
    events = _read_jsonl_records(events_file, label="events", missing_ok=True)
    current: dict[str, Any] | None = None
    for event in events:
        event_type = event.get("event_type")
        if event.get("step_name") != step_name:
            continue
        if isinstance(step_execution_id, str) and event.get("step_execution_id") != step_execution_id:
            continue
        if event_type == "provider_attempt_started":
            current = {
                "phase": "provider_attempt",
                "step_name": step_name,
                "step_execution_id": event.get("step_execution_id"),
                "turn_kind": event.get("turn_kind"),
                "attempt": event.get("attempt"),
                "max_attempts": event.get("max_attempts"),
            }
            continue
        if current is None or not _event_matches_repair_cursor(event, current):
            continue
        if event_type == "provider_turn_started":
            for key in ("expected_response", "prompt_fingerprint", "provider_target", "session_id_before"):
                if event.get(key) is not None:
                    current[key] = event.get(key)
        elif event_type == "provider_session_known":
            if event.get("session_id") is not None:
                current["provider_session_id"] = event.get("session_id")
            if event.get("provider_target") is not None:
                current["provider_target"] = event.get("provider_target")
        elif event_type in {"provider_attempt_finished", "provider_attempt_failed"}:
            current = None
    return current


def _event_matches_repair_cursor(event: Mapping[str, Any], cursor: Mapping[str, Any]) -> bool:
    if event.get("turn_kind") != cursor.get("turn_kind"):
        return False
    if event.get("attempt") != cursor.get("attempt"):
        return False
    cursor_step_execution_id = cursor.get("step_execution_id")
    if isinstance(cursor_step_execution_id, str):
        return event.get("step_execution_id") == cursor_step_execution_id
    return True


def _read_jsonl_records(path: Path, *, label: str, missing_ok: bool = False) -> list[dict[str, Any]]:
    if not path.is_file():
        if missing_ok:
            return []
        raise _sdk_resolution_error(f"{label} log is missing at {path}")
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        records.append(_parse_jsonl_record(line, path=path, label=label, line_number=line_number))
    return records


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(payload), indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        with suppress(FileNotFoundError):
            tmp_path.unlink()


def _read_run_log_text(path: Path, label: str) -> str:
    if not path.is_file():
        message = f"{label} log is missing at {path}"
        raise _sdk_resolution_error(message)
    return path.read_text(encoding="utf-8")


async def _iter_jsonl_records(
    path: Path,
    *,
    label: str,
    follow: bool,
    poll_interval: float,
) -> AsyncIterator[dict[str, Any]]:
    if poll_interval <= 0:
        raise SDKExecutionError(f"poll_interval must be > 0; received {poll_interval!r}")

    offset = 0
    buffered = ""
    line_number = 1
    while True:
        if not path.is_file():
            if not follow:
                message = f"{label} log is missing at {path}"
                raise _sdk_resolution_error(message)
            await asyncio.sleep(poll_interval)
            continue

        with path.open("r", encoding="utf-8") as handle:
            handle.seek(offset)
            chunk = handle.read()
            offset = handle.tell()

        if chunk:
            buffered += chunk
            lines = buffered.splitlines(keepends=True)
            if lines and not (lines[-1].endswith("\n") or lines[-1].endswith("\r")):
                buffered = lines.pop()
            else:
                buffered = ""
            for raw_line in lines:
                current_line = line_number
                line_number += 1
                line = raw_line.strip()
                if not line:
                    continue
                yield _parse_jsonl_record(line, path=path, label=label, line_number=current_line)
            continue

        if buffered and not follow:
            current_line = line_number
            line_number += 1
            line = buffered.strip()
            buffered = ""
            if line:
                yield _parse_jsonl_record(line, path=path, label=label, line_number=current_line)
        if not follow:
            return
        await asyncio.sleep(poll_interval)


def _parse_jsonl_record(line: str, *, path: Path, label: str, line_number: int) -> dict[str, Any]:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise SDKExecutionError(
            f"{label} log at {path}:{line_number} contains malformed JSON: {exc.msg}",
            original_error=exc,
        ) from exc
    if not isinstance(payload, dict):
        raise SDKExecutionError(f"{label} log at {path}:{line_number} must contain a JSON object")
    return payload


def _resolve_sdk_provider(
    *,
    provider: str | LLMProvider | None,
    provider_config: ProviderConfig,
    runtime_config: RuntimeConfig,
    provider_policy_config: ProviderPolicyRuntimeConfig,
) -> LLMProvider:
    if provider is not None and not isinstance(provider, str):
        try:
            return validate_llm_provider(provider)
        except Exception as exc:
            raise SDKExecutionError(f"invalid provider object {type(provider).__name__!r}: {exc}", original_error=exc) from exc

    try:
        backend_config = ResolvedRuntimeConfig(
            provider=provider_config,
            runtime=runtime_config,
            provider_policy=provider_policy_config,
        )
        return resolve_provider_backend(config=backend_config)
    except (ConfigError, RuntimeError, TypeError) as exc:
        provider_label = provider if isinstance(provider, str) else None
        detail = provider_label or "the configured default provider"
        raise SDKExecutionError(f"could not resolve SDK provider {detail!r}: {exc}", original_error=exc) from exc


def _provider_config_with_overrides(
    base: ProviderConfig,
    *,
    provider: str | LLMProvider | None,
    model: str | None,
    model_effort: str | None,
) -> ProviderConfig:
    if provider is not None and not isinstance(provider, str):
        if model is not None or model_effort is not None:
            raise SDKExecutionError(
                "model and model_effort overrides are only supported when provider is a built-in provider name or None"
            )
        return base
    provider_name = provider.strip() if isinstance(provider, str) else base.name
    updated = replace(base, name=provider_name)
    if model is None and model_effort is None:
        return updated
    if provider_name == "codex":
        return replace(updated, codex=CodexProviderConfig(model=model or updated.codex.model, model_effort=model_effort))
    if provider_name == "claude":
        return replace(
            updated,
            claude=ClaudeProviderConfig(
                model=model or updated.claude.model,
                effort=model_effort if model_effort is not None else updated.claude.effort,
                permission_strategy=updated.claude.permission_strategy,
            ),
        )
    return updated


def _resolve_and_compile_workflow(root: Path, workflow: type[object] | str) -> tuple[Any, WorkflowPlan]:
    try:
        resolved = resolve_workflow_reference(root, workflow)
        try:
            return resolved, compile_workflow(resolved.workflow_cls)
        except WorkflowValidationError as exc:
            message = runtime_workflow_validation_message(exc)
            if message is None:
                raise
            normalized_error = WorkflowExecutionError(message)
            raise _wrap_sdk_execution_error(
                normalized_error,
                workflow_name=resolved.workflow_cls.__name__,
            ) from exc
    except Exception as exc:
        if isinstance(exc, (WorkflowCompilationError, WorkflowExecutionError)):
            raise
        if isinstance(exc, WorkflowValidationError):
            message = runtime_workflow_validation_message(exc)
            if message is not None:
                normalized_error = WorkflowExecutionError(message)
                workflow_name = workflow.__name__ if isinstance(workflow, type) else None
                raise _wrap_sdk_execution_error(normalized_error, workflow_name=workflow_name) from exc
        if isinstance(exc, WorkflowDiscoveryError):
            raise SDKExecutionError(str(exc), original_error=exc) from exc
        raise


def _coerce_sdk_input(
    compiled: WorkflowPlan,
    input: BaseModel | Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    workflow_name = compiled.workflow_cls.__name__
    input_model = compiled.input_model
    if input_model is None:
        if input is not None:
            raise WorkflowInputError(
                f"{workflow_name} does not declare Input and does not accept input=...; "
                f"received {type(input).__name__}"
            )
        return None
    if input is None:
        try:
            default_input = input_model()
        except ValidationError as exc:
            raise WorkflowInputError(
                f"{workflow_name} requires {workflow_name}.Input; missing required fields: "
                f"{', '.join(sorted(_missing_validation_fields(exc)))}"
            ) from exc
        return default_input.model_dump(mode="json")
    if isinstance(input, BaseModel):
        if type(input) is not input_model:
            raise WorkflowInputError(
                f"{workflow_name} expects input= of exact type {input_model.__module__}.{input_model.__qualname__} "
                f"or a mapping; received {type(input).__module__}.{type(input).__qualname__}"
            )
        return input.model_dump(mode="json")
    if not isinstance(input, Mapping):
        raise WorkflowInputError(
            f"{workflow_name} input must be a mapping, {workflow_name}.Input instance, or None; "
            f"received {type(input).__name__}"
        )
    try:
        validated = input_model.model_validate(dict(input))
    except ValidationError as exc:
        raise WorkflowInputError(f"{workflow_name} input is invalid: {exc}") from exc
    return validated.model_dump(mode="json")


def _normalize_sdk_policy_input(
    policy: PolicyInput,
    *,
    field_name: str = "policy",
) -> PolicyInput:
    if policy is None or isinstance(policy, (Policy, ProviderPolicy, ProviderPolicyOverride)):
        return policy
    raise TypeError(f"{field_name} must be a Policy or core provider policy object, or None")


def _sdk_step_invocation_layer(
    step_def: Step | object,
    invocation_policy: PolicyInput,
) -> tuple[Step | object, PolicyInput]:
    if invocation_policy is None:
        return step_def, None
    layered_step = _shallow_sdk_clone(step_def)
    if isinstance(layered_step, Step):
        authored_policy = layered_step.provider_policy
        layered_step.provider_policy = invocation_policy
        return layered_step, authored_policy
    authored_policy = getattr(layered_step, "policy", None)
    setattr(layered_step, "policy", invocation_policy)
    return layered_step, authored_policy


def _shallow_sdk_clone(value: object) -> object:
    clone = object.__new__(value.__class__)
    if hasattr(value, "__dict__"):
        clone.__dict__.update(value.__dict__)
    for cls in value.__class__.mro():
        slots = getattr(cls, "__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        for slot in slots:
            if slot in {"__dict__", "__weakref__"}:
                continue
            if hasattr(value, slot):
                object.__setattr__(clone, slot, getattr(value, slot))
    return clone


def _normalize_sdk_writes(
    step_name: str,
    writes: Sequence[Artifact | simple.ArtifactSpec],
) -> dict[str, Artifact] | None:
    if not writes:
        return None
    normalized: dict[str, Artifact] = {}
    for item in writes:
        if isinstance(item, Artifact):
            artifact = item
        elif isinstance(item, simple.ArtifactSpec):
            artifact = item.materialize(step_name)
        else:
            raise TypeError("writes entries must be Artifact or simple artifact specs such as Md(...)")
        artifact_name = artifact.name
        if not isinstance(artifact_name, str) or not artifact_name.strip():
            raise ValueError("writes artifacts must have a stable non-empty name")
        if artifact_name in normalized and normalized[artifact_name] is not artifact:
            raise ValueError(f"duplicate write artifact name {artifact_name!r}")
        normalized[artifact_name] = artifact
    return normalized


def _coerce_sdk_params(
    parameters_cls: type[Any] | None,
    params: BaseModel | Mapping[str, Any] | None,
    *,
    workflow_name: str,
) -> dict[str, Any]:
    if params is None:
        return {}
    if isinstance(params, BaseModel):
        payload = params.model_dump(mode="python")
    elif isinstance(params, Mapping):
        payload = dict(params)
    else:
        raise WorkflowParameterError(
            f"{workflow_name} params must be a mapping, {workflow_name}.Params instance, or None; "
            f"received {type(params).__name__}"
        )
    try:
        return coerce_workflow_parameter_mapping(parameters_cls, payload)
    except RuntimeWorkflowParameterError as exc:
        raise WorkflowParameterError(f"{workflow_name} params are invalid: {exc}", original_error=exc) from exc


def _sdk_runtime_config_with_provider_questions(
    runtime_config: RuntimeConfig,
    *,
    allow_provider_questions: bool,
) -> RuntimeConfig:
    return replace(runtime_config, full_auto=not allow_provider_questions)


def _generate_sdk_task_id(
    workflow_name: str,
    *,
    root: Path,
    state_dir: Path,
) -> str:
    try:
        return generate_task_id(
            root=root,
            state_dir=state_dir,
            message=workflow_name,
            workflow_name=workflow_name,
            prefix="sdk",
            max_slug_words=5,
            max_slug_chars=48,
            suffix_chars=8,
        )
    except TaskIdGenerationError as exc:
        raise SDKExecutionError(str(exc), original_error=exc) from exc


def _sdk_debug_info(execution: RunExecution) -> SDKDebugInfo:
    run_workspace = execution.run_workspace
    return SDKDebugInfo(
        task_id=execution.task_workspace.task_id,
        run_id=run_workspace.run_id,
        task_dir=execution.task_workspace.task_dir,
        workflow_dir=execution.workflow_workspace.workflow_dir,
        run_dir=run_workspace.run_dir,
        events_file=run_workspace.events_file,
        trace_file=run_workspace.trace_file if run_workspace.trace_file.exists() else None,
        checkpoint_file=run_workspace.checkpoint_file if run_workspace.checkpoint_file.exists() else None,
    )


def _sdk_result_artifacts(
    execution: RunExecution,
    *,
    message: str | None,
) -> dict[str, ResultArtifact]:
    context = _sdk_artifact_context(execution, message=message)
    artifacts: dict[str, ResultArtifact] = {}
    for name, artifact in execution.compiled.artifact_items(authoritative=False):
        if not _sdk_artifact_root_resolvable(execution, artifact):
            continue
        path = _resolve_sdk_artifact_path(artifact, context)
        artifacts[name] = ResultArtifact(
            name=name,
            path=path,
            kind=artifact.kind,
            schema=artifact.schema,
            source_path=path,
            promoted=False,
            required=artifact.required,
            qualified_name=artifact.qualified_name,
        )
    return artifacts


def _sdk_artifact_root_resolvable(execution: RunExecution, artifact: ArtifactSpec) -> bool:
    requirements = execution.compiled.reference_graph.artifact_template_requirements.get(artifact.qualified_name)
    if requirements is None:
        return True
    return not bool(requirements.roots & ROOT_STABLE_ARTIFACT_TEMPLATE_BLOCKING_ROOTS)


def _sdk_tasks_root(root: Path, state_dir: Path) -> Path:
    del root
    return state_dir / "tasks"


def _sdk_readable_tasks_roots(root: Path, state_dir: Path) -> tuple[Path, ...]:
    return (_sdk_tasks_root(root, state_dir.resolve()),)


def _sdk_artifact_context(execution: RunExecution, *, message: str | None) -> Any:
    return _runtime_equivalent_artifact_context(execution, message=message)


def _runtime_equivalent_artifact_context(execution: RunExecution, *, message: str | None) -> Any:
    session_store = InMemorySessionStore()
    checkpoint = execution.result.checkpoint
    snapshot = checkpoint.session_bindings if checkpoint is not None else SessionSnapshot(bindings=())
    session_store.restore(snapshot)
    params = materialize_workflow_params(execution.compiled.parameters_cls, execution.workflow_params)
    return Context(
        root=execution.task_workspace.root,
        task_id=execution.task_workspace.task_id,
        run_id=execution.run_workspace.run_id,
        workflow_name=execution.compiled.workflow_name,
        task_folder=execution.task_workspace.task_dir,
        workflow_folder=execution.workflow_workspace.workflow_dir,
        run_folder=execution.run_workspace.run_dir,
        package_folder=execution.workflow_workspace.package_dir,
        request_file=execution.run_workspace.request_file,
        task_request_file=execution.task_workspace.task_request_file,
        state=execution.result.state,
        session_store=session_store,
        params=params,
        workflow_params=execution.workflow_params,
        message=message,
        workflow_input=execution.workflow_input,
    )


def _resolve_sdk_artifact_path(artifact: ArtifactSpec, context: Any) -> Path:
    candidate = Path(artifact.template)
    if not candidate.is_absolute() and artifact.owner_step is not None and "{" not in artifact.template and "}" not in artifact.template:
        return context.workflow_folder / artifact.owner_step / artifact.template
    return resolve_artifact_template(artifact, context)


def _terminal_status(terminal: str) -> tuple[Literal["completed", "failed", "awaiting_input"], bool]:
    if terminal == FINISH:
        return "completed", True
    if terminal == FAIL:
        return "failed", False
    if terminal == AWAIT_INPUT:
        return "awaiting_input", False
    return "failed", False


def _is_resume_input_validation_error(exc: BaseException) -> bool:
    failure_context = exception_failure_context(exc)
    return failure_context is not None and failure_context.kind == "resume_input_validation"


def _wrap_sdk_execution_error(
    exc: Exception,
    *,
    workflow_name: str | None = None,
    operation_name: str | None = None,
    task_dir: Path | None = None,
) -> SDKExecutionError:
    if isinstance(exc, BotpipeSDKError):
        return (
            exc
            if isinstance(exc, SDKExecutionError)
            else SDKExecutionError(str(exc), original_error=exc, task_dir=task_dir)
        )
    if _is_active_loop_runtime_error(exc):
        subject = operation_name or "workflow execution"
        return SDKExecutionError(
            f"Synchronous SDK {subject} cannot run inside an active event loop. {_ACTIVE_LOOP_HINT}",
            original_error=exc,
            task_dir=task_dir,
        )
    if workflow_name is not None:
        return SDKExecutionError(f"workflow {workflow_name!r} execution failed: {exc}", original_error=exc, task_dir=task_dir)
    if operation_name is not None:
        return SDKExecutionError(f"sdk.{operation_name} failed: {exc}", original_error=exc, task_dir=task_dir)
    return SDKExecutionError(str(exc), original_error=exc, task_dir=task_dir)


def _is_active_loop_runtime_error(exc: BaseException) -> bool:
    return isinstance(exc, RuntimeError) and "active event loop" in str(exc).lower()


def _missing_validation_fields(exc: ValidationError) -> set[str]:
    missing: set[str] = set()
    for error in exc.errors():
        if error.get("type") != "missing":
            continue
        location = error.get("loc")
        if isinstance(location, tuple) and location:
            missing.add(str(location[0]))
    return missing or {"<unknown>"}


def _sdk_operation_dir(root: Path, state_dir: Path, *, kind: str) -> Path:
    operation_dir = state_dir / "sdk-operations" / f"{kind}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    operation_dir.mkdir(parents=True, exist_ok=True)
    return operation_dir


def _is_inside_path(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _write_sdk_task_sentinel(
    *,
    task_dir: Path,
    task_id: str,
    policy: RetentionPolicy,
) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    sentinel = task_dir / SDK_TASK_SENTINEL_FILENAME
    payload = {
        "schema": "botpipe.sdk_task/v1",
        "generated_by": "botpipe.sdk",
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "retention_mode": policy.mode,
    }
    sentinel.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_sdk_task_sentinel(task_dir: Path) -> dict[str, Any]:
    sentinel = _sdk_task_sentinel_path(task_dir)
    try:
        payload = json.loads(sentinel.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SDKExecutionError(f"refusing to delete non-SDK or unsafe task directory {task_dir}", original_error=exc) from exc
    except json.JSONDecodeError as exc:
        raise SDKExecutionError(f"refusing to delete non-SDK or unsafe task directory {task_dir}", original_error=exc) from exc
    if not isinstance(payload, dict):
        raise SDKExecutionError(f"refusing to delete non-SDK or unsafe task directory {task_dir}")
    return payload


def _safe_delete_sdk_task_dir(
    *,
    task_dir: Path,
    task_id: str,
    tasks_root: Path,
) -> None:
    resolved_task_dir = task_dir.resolve()
    resolved_tasks_root = tasks_root.resolve()
    sentinel = _sdk_task_sentinel_path(task_dir)
    blocked_roots = {
        resolved_tasks_root,
        resolved_tasks_root.parent,
        resolved_tasks_root.parent.parent,
        Path.home().resolve(),
        Path(resolved_task_dir.anchor).resolve(),
    }
    if not task_id.startswith("sdk-"):
        raise SDKExecutionError(f"refusing to delete non-SDK or unsafe task directory {task_dir}")
    if task_dir.name != task_id:
        raise SDKExecutionError(f"refusing to delete non-SDK or unsafe task directory {task_dir}")
    if not _is_inside_path(resolved_task_dir, resolved_tasks_root):
        raise SDKExecutionError(f"refusing to delete non-SDK or unsafe task directory {task_dir}")
    if not sentinel.is_file():
        raise SDKExecutionError(f"refusing to delete non-SDK or unsafe task directory {task_dir}")
    payload = _load_sdk_task_sentinel(task_dir)
    if payload.get("schema") != "botpipe.sdk_task/v1":
        raise SDKExecutionError(f"refusing to delete non-SDK or unsafe task directory {task_dir}")
    if payload.get("generated_by") != "botpipe.sdk":
        raise SDKExecutionError(f"refusing to delete non-SDK or unsafe task directory {task_dir}")
    if payload.get("task_id") != task_dir.name:
        raise SDKExecutionError(f"refusing to delete non-SDK or unsafe task directory {task_dir}")
    if resolved_task_dir in blocked_roots:
        raise SDKExecutionError(f"refusing to delete non-SDK or unsafe task directory {task_dir}")
    shutil.rmtree(resolved_task_dir)


def _collect_declared_write_artifacts(
    execution: RunExecution,
    *,
    message: str | None,
) -> dict[str, DeclaredWriteArtifact]:
    context = _runtime_equivalent_artifact_context(execution, message=message)
    artifacts: dict[str, DeclaredWriteArtifact] = {}
    for name, artifact in execution.compiled.artifact_items(authoritative=False):
        if not _sdk_artifact_root_resolvable(execution, artifact):
            continue
        path = _resolve_sdk_artifact_path(artifact, context)
        artifacts[name] = DeclaredWriteArtifact(
            name=name,
            path=path,
            kind=artifact.kind,
            schema=artifact.schema,
            required=artifact.required,
            qualified_name=artifact.qualified_name,
        )
    return artifacts


def _promotion_base_dir(*, root: Path, task_id: str, policy: RetentionPolicy) -> Path:
    if policy.promoted_writes_dir is None:
        return root / ".botpipe" / "outputs" / "sdk" / task_id
    candidate = Path(policy.promoted_writes_dir)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate


def _sdk_task_sentinel_path(task_dir: Path) -> Path:
    return task_dir / SDK_TASK_SENTINEL_FILENAME


def _uniquify_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}-{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _promotion_destination(
    *,
    artifact: DeclaredWriteArtifact,
    source: Path,
    root: Path,
    task_id: str,
    task_dir: Path,
    policy: RetentionPolicy,
) -> Path:
    base_dir = _promotion_base_dir(root=root, task_id=task_id, policy=policy).resolve()
    relative_path = source.relative_to(task_dir.resolve())
    destination = (base_dir / relative_path).resolve()
    if not _is_inside_path(destination, base_dir):
        raise SDKExecutionError(f"refusing to promote declared write outside the promotion directory: {artifact.path}")
    if destination.exists() and policy.promoted_writes_dir is not None:
        return _uniquify_path(destination)
    return destination


def _promote_declared_write(
    *,
    artifact: DeclaredWriteArtifact,
    root: Path,
    task_id: str,
    task_dir: Path,
    policy: RetentionPolicy,
) -> Path:
    source = artifact.path.resolve()
    resolved_task_dir = task_dir.resolve()
    if not _is_inside_path(source, resolved_task_dir):
        raise SDKExecutionError(f"declared write {artifact.name!r} is not inside SDK task scratch: {artifact.path}")
    if source.is_dir():
        raise SDKExecutionError(f"declared write {artifact.name!r} points to a directory, which is unsupported in the SDK MVP")
    destination = _promotion_destination(
        artifact=artifact,
        source=source,
        root=root,
        task_id=task_id,
        task_dir=resolved_task_dir,
        policy=policy,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination


def _result_artifact_map_from_declared_writes(
    declared_writes: Mapping[str, DeclaredWriteArtifact],
    *,
    retained_paths: Mapping[str, Path] | None = None,
    promoted_names: frozenset[str] = frozenset(),
) -> ArtifactMap:
    result: dict[str, ResultArtifact] = {}
    path_overrides = dict(retained_paths or {})
    names = tuple(path_overrides) if retained_paths is not None else tuple(declared_writes)
    for name in names:
        artifact = declared_writes[name]
        retained_path = path_overrides.get(name, artifact.path)
        result[name] = ResultArtifact(
            name=name,
            path=retained_path,
            kind=artifact.kind,
            schema=artifact.schema,
            source_path=artifact.path,
            promoted=name in promoted_names,
            required=artifact.required,
            qualified_name=artifact.qualified_name,
        )
    return ArtifactMap(result)


def _apply_retention(
    *,
    execution: RunExecution,
    result: WorkflowResult,
    policy: RetentionPolicy,
    message: str | None,
    too_many_pauses: bool = False,
) -> WorkflowResult:
    task_dir = execution.task_workspace.task_dir
    task_id = execution.task_workspace.task_id
    tasks_root = _sdk_tasks_root(execution.task_workspace.root, execution.task_workspace.state_root)
    root = execution.task_workspace.root
    declared_writes = _collect_declared_write_artifacts(execution, message=message)

    keep_task_dir = policy.mode == "keep_all"
    if result.status == "failed" and policy.keep_on_failure:
        keep_task_dir = True
    if result.status == "awaiting_input" and policy.keep_on_input_required:
        keep_task_dir = True
    if too_many_pauses and policy.keep_on_too_many_pauses:
        keep_task_dir = True

    retained_paths: dict[str, Path] = {}
    promoted_artifacts: list[str] = []
    if keep_task_dir:
        for name, artifact in declared_writes.items():
            retained_paths[name] = artifact.path
    else:
        for name, artifact in declared_writes.items():
            artifact_path = artifact.path
            if not _is_inside_path(artifact_path, task_dir):
                retained_paths[name] = artifact_path
                continue
            if not policy.keep_declared_writes:
                continue
            if not artifact_path.exists():
                retained_paths[name] = artifact_path
                continue
            if not policy.promote_task_writes:
                raise SDKExecutionError(
                    f"declared write {name!r} would be deleted with SDK task scratch retention disabled"
                )
            retained_paths[name] = _promote_declared_write(
                artifact=artifact,
                root=root,
                task_id=task_id,
                task_dir=task_dir,
                policy=policy,
            )
            promoted_artifacts.append(name)

    if not keep_task_dir and policy.mode in {"delete_task_scratch", "delete_all_sdk_managed"}:
        _safe_delete_sdk_task_dir(
            task_dir=task_dir,
            task_id=task_id,
            tasks_root=tasks_root,
        )

    retention = RetentionInfo(
        policy=policy,
        task_scratch_retained=keep_task_dir,
        task_scratch_deleted=not keep_task_dir and policy.mode in {"delete_task_scratch", "delete_all_sdk_managed"},
        promoted_artifacts=tuple(promoted_artifacts),
        retained_task_dir=task_dir if keep_task_dir else None,
    )
    return replace(
        result,
        artifacts=_result_artifact_map_from_declared_writes(
            declared_writes,
            retained_paths=retained_paths,
            promoted_names=frozenset(promoted_artifacts),
        ),
        retention=retention,
    )


def _sdk_task_created_at(candidate: Path) -> datetime:
    payload = _load_sdk_task_sentinel(candidate)
    created_at = payload.get("created_at")
    if isinstance(created_at, str):
        try:
            return datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)


def _task_dir_appears_failed_or_awaiting_input(task_dir: Path) -> bool:
    run_meta_files = sorted(task_dir.glob("wf_*/runs/*/run.json"))
    if not run_meta_files:
        return True
    for run_meta_file in run_meta_files:
        try:
            payload = json.loads(run_meta_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return True
        if not isinstance(payload, dict):
            return True
        status = payload.get("status")
        terminal = payload.get("terminal")
        pending_input = payload.get("pending_input")
        if status not in {"completed"}:
            return True
        if terminal == AWAIT_INPUT:
            return True
        if isinstance(pending_input, dict) and pending_input:
            return True
        if payload.get("error") is not None:
            return True
    return False


def _build_single_step_execution_plan(
    root: Path,
    step_def: Step | object,
    input: BaseModel | Mapping[str, Any] | None,
    params: BaseModel | Mapping[str, Any] | None,
    *,
    routes: Mapping[str, Any] | None,
    workflow_policy: PolicyInput = None,
) -> tuple[SingleStepPlan, WorkflowPlan]:
    _validate_step_declaration_supported(root, step_def)
    return _compile_single_step_execution_plan(
        step_def,
        input_model=_single_step_input_model(input),
        params_model=_single_step_params_model(params),
        routes=routes,
        workflow_policy=workflow_policy,
    )


def _single_step_input_model(input: BaseModel | Mapping[str, Any] | None) -> type[BaseModel] | None:
    if isinstance(input, BaseModel):
        return type(input)
    if isinstance(input, Mapping):
        return create_model(
            f"SDKStepInput_{uuid4().hex[:8]}",
            **{str(key): (Any, ...) for key in input},
        )
    return None


def _single_step_params_model(params: BaseModel | Mapping[str, Any] | None) -> type[BaseModel] | None:
    if isinstance(params, BaseModel):
        return type(params)
    if isinstance(params, Mapping) and params:
        return create_model(
            f"SDKStepParams_{uuid4().hex[:8]}",
            **{str(key): (Any, ...) for key in params},
        )
    return None


def _single_step_workflow_reference(root: Path, workflow_plan: WorkflowPlan) -> WorkflowReference:
    workflow_cls = workflow_plan.workflow_cls
    return WorkflowReference(
        original=f"botpipe.sdk.step:{workflow_plan.workflow_name}",
        kind="workflow_class",
        workflow_name=workflow_plan.workflow_name,
        title=None,
        description=None,
        aliases=(),
        class_name=workflow_cls.__name__,
        module_name=workflow_cls.__module__,
        source_path=Path(__file__).resolve(),
        package_dir=root,
        manifest_path=None,
        authoring_shape="unknown",
        source_root_kind="workspace",
        source_root=root,
        package_name=None,
        package_module=None,
        workflow_module=workflow_cls.__module__,
    )

def _normalize_prompt(prompt: str | Prompt) -> Prompt:
    if isinstance(prompt, Prompt):
        return prompt
    if isinstance(prompt, str):
        return Prompt.inline(prompt)
    raise TypeError(f"unsupported prompt type: {type(prompt).__name__}")


def _normalize_retry_policy(retry: int | ProviderRetryPolicy | None) -> ProviderRetryPolicy | None:
    if retry is None or isinstance(retry, ProviderRetryPolicy):
        return retry
    if isinstance(retry, bool) or not isinstance(retry, int):
        raise TypeError("retry must be an integer, ProviderRetryPolicy, or None")
    return ProviderRetryPolicy(max_attempts=retry)


def _materialize_child_workflow_params(params: BaseModel | Mapping[str, Any] | None) -> dict[str, Any]:
    if params is None:
        return {}
    if isinstance(params, BaseModel):
        return params.model_dump(mode="python")
    if isinstance(params, Mapping):
        return dict(params)
    raise WorkflowParameterError(
        "workflow_step params must be a mapping, Workflow.Params instance, or None"
    )


def _step_result_route(workflow_result: WorkflowResult) -> str | None:
    if workflow_result.last_event is not None:
        return workflow_result.last_event.tag
    if workflow_result.last_outcome is not None:
        return workflow_result.last_outcome.tag
    return None


def _validate_step_declaration_supported(root: Path, step_def: object) -> None:
    if isinstance(step_def, BranchGroupStep) or getattr(step_def, "kind", None) == "branch_group":
        raise SDKExecutionError("client.step(...) does not support branch-group declarations in the MVP")
    if getattr(step_def, "scope", None) is not None:
        raise SDKExecutionError("client.step(...) does not support worklist-scoped declarations in the MVP")

    if isinstance(step_def, Step):
        if isinstance(step_def, ChildWorkflowStep):
            _ensure_child_workflow_resolvable(root, step_def.workflow)
        return

    if isinstance(step_def, getattr(simple, "_NamedDeclaration")):
        kind = getattr(step_def, "kind", None)
        if kind == "workflow":
            _ensure_child_workflow_resolvable(root, getattr(step_def, "workflow"))
        return

    raise SDKExecutionError(
        "client.step(...) expects a simple named step declaration or a supported core Step instance"
    )


def _ensure_child_workflow_resolvable(root: Path, workflow: object) -> None:
    try:
        resolve_workflow_reference(root, workflow)
    except Exception as exc:
        raise SDKExecutionError(f"child workflow reference could not be resolved for client.step(...): {exc}", original_error=exc) from exc


__all__ = [
    "ArtifactMap",
    "Botpipe",
    "BotpipeSDKError",
    "BestSuppositionInput",
    "CleanupResult",
    "ConsoleInput",
    "DeclaredWriteArtifact",
    "HandledInput",
    "InputRequest",
    "InputRequired",
    "InputResponseValidationError",
    "MappingInput",
    "ResultArtifact",
    "RunRecord",
    "RunsClient",
    "SDKDebugInfo",
    "SDKExecutionError",
    "StaticInput",
    "StepResult",
    "TaskRecord",
    "TasksClient",
    "TooManyPauses",
    "Policy",
    "PolicyInput",
    "ProviderName",
    "ModelEffort",
    "ModelVerbosity",
    "ReasoningSummary",
    "SandboxMode",
    "NetworkMode",
    "PermissionMode",
    "RetentionInfo",
    "RetentionPolicy",
    "WorkflowInputError",
    "WorkflowParameterError",
    "WorkflowResult",
]
