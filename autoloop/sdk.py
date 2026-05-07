"""Public SDK facade over the filesystem workflow runtime."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ValidationError

import autoloop.simple as simple
from autoloop.core import Workflow as CoreWorkflow
from autoloop.core.artifacts import CompiledArtifact, resolve_artifact_template
from autoloop.core.compiler import CompiledWorkflow, compile_workflow
from autoloop.core.context import Context, WorkflowInputView
from autoloop.core.errors import WorkflowCompilationError, WorkflowExecutionError, exception_failure_context
from autoloop.core.operations import classify_call, llm_call
from autoloop.core.primitives import AWAIT_INPUT, FAIL, FINISH, Event, Outcome
from autoloop.core.prompts import Prompt
from autoloop.core.provider_policy import ProviderPolicy, ProviderPolicyOverride
from autoloop.core.providers.protocols import LLMProvider, validate_llm_provider
from autoloop.core.steps import BranchGroupStep, ChildWorkflowStep, ProduceVerifyStep, PromptStep, PythonStep, Step
from autoloop.core.stores.protocols import SessionSnapshot
from autoloop.core.stores.session_store import InMemorySessionStore
from autoloop.runtime.config import (
    ClaudeProviderConfig,
    CodexProviderConfig,
    ConfigError,
    ProviderConfig,
    ProviderPolicyRuntimeConfig,
    ResolvedRuntimeConfig,
    RuntimeConfig,
    resolve_runtime_config,
)
from autoloop.runtime.loader import (
    WorkflowDiscoveryError,
    WorkflowParameterError as RuntimeWorkflowParameterError,
    coerce_workflow_parameter_mapping,
    materialize_workflow_params,
    resolve_workflow_reference,
)
from autoloop.runtime.provider_backends import resolve_provider_backend
from autoloop.runtime.runner import RunExecution, RunnerOptions, execute_workflow_package
from autoloop.runtime.workspace import primary_state_root, resolve_task_workspace


InputResponse = str | BaseModel | Mapping[str, Any] | Sequence[Any] | int | float | bool | None
InputHandler = Callable[["InputRequest"], InputResponse]
_TASK_ID_SAFE_RE = re.compile(r"[^a-z0-9]+")
_ACTIVE_LOOP_HINT = "Use an async SDK entrypoint instead."


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


class AutoloopSDKError(Exception):
    """Base exception for the public SDK facade."""

    def __init__(self, message: str, *, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class WorkflowInputError(AutoloopSDKError):
    """Raised when SDK workflow input is invalid."""


class WorkflowParameterError(AutoloopSDKError):
    """Raised when SDK workflow params are invalid."""


class SDKExecutionError(AutoloopSDKError):
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


class InputRequired(AutoloopSDKError):
    """Raised when a workflow pauses and no input handler is configured."""

    def __init__(self, *, request: InputRequest, partial: WorkflowResult) -> None:
        self.request = request
        self.partial = partial
        super().__init__(f"workflow paused awaiting input: {request.question}")


class TooManyPauses(AutoloopSDKError):
    """Raised when the SDK exceeds the configured pause budget."""

    def __init__(self, *, max_pauses: int, partial: WorkflowResult | None) -> None:
        self.max_pauses = max_pauses
        self.partial = partial
        super().__init__(f"workflow exceeded max_pauses={max_pauses}")


class InputResponseValidationError(AutoloopSDKError):
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


class Autoloop:
    def __init__(
        self,
        *,
        root: str | Path = ".",
        provider: str | LLMProvider | None = None,
        model: str | None = None,
        model_effort: str | None = None,
        runtime_config: RuntimeConfig | None = None,
        provider_policy_config: ProviderPolicyRuntimeConfig | None = None,
        state_dir: str | Path | None = None,
        retention: RetentionPolicy | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.runtime_config = runtime_config or RuntimeConfig()
        self.provider_policy_config = provider_policy_config or ProviderPolicyRuntimeConfig()
        self.state_dir = primary_state_root(self.root) if state_dir is None else Path(state_dir).resolve()
        self.retention = retention or RetentionPolicy.sdk_default()
        self._provider = _resolve_sdk_provider(
            root=self.root,
            provider=provider,
            model=model,
            model_effort=model_effort,
            runtime_config=self.runtime_config,
            provider_policy_config=self.provider_policy_config,
        )

    def run(
        self,
        workflow: type[object] | str,
        message: str | None = None,
        typed_input: BaseModel | None = None,
        /,
        *,
        params: BaseModel | Mapping[str, Any] | None = None,
        on_input: InputHandler | None = None,
        max_pauses: int = 8,
        max_steps: int | None = None,
        provider_questions: bool | None = None,
        options: RunOptions | None = None,
        retention: RetentionPolicy | None = None,
    ) -> WorkflowResult:
        if message is not None and not isinstance(message, str):
            raise WorkflowInputError(f"message must be str | None; received {type(message).__name__}")
        if isinstance(max_pauses, bool) or not isinstance(max_pauses, int) or max_pauses < 0:
            raise SDKExecutionError(f"max_pauses must be an integer >= 0; received {max_pauses!r}")
        if options is not None and not isinstance(options, RunOptions):
            raise SDKExecutionError(f"options must be RunOptions | None; received {type(options).__name__}")

        resolved, compiled = _resolve_and_compile_workflow(self.root, workflow)
        structured_input = _coerce_sdk_typed_input(compiled, typed_input)
        structured_params = _coerce_sdk_params(resolved.parameters_cls, params, workflow_name=compiled.workflow_name)
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
                execution = execute_workflow_package(
                    resolved.workflow_cls,
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
        policy: ProviderPolicy | ProviderPolicyOverride | None = None,
    ) -> Any:
        try:
            return llm_call(
                prompt if isinstance(prompt, Prompt) else prompt,
                returns=returns,
                retry=retry,
                provider=self._provider,
                run_folder=_sdk_operation_dir(self.root, self.state_dir, kind="llm"),
                policy=policy,
            )
        except Exception as exc:
            raise _wrap_sdk_execution_error(exc, operation_name="llm") from exc

    def classify(
        self,
        prompt: str | Path | Prompt,
        *,
        choices: Sequence[str],
        retry: int = 3,
        policy: ProviderPolicy | ProviderPolicyOverride | None = None,
    ) -> str:
        try:
            return classify_call(
                prompt if isinstance(prompt, Prompt) else prompt,
                choices=choices,
                retry=retry,
                provider=self._provider,
                run_folder=_sdk_operation_dir(self.root, self.state_dir, kind="classify"),
                policy=policy,
            )
        except Exception as exc:
            raise _wrap_sdk_execution_error(exc, operation_name="classify") from exc

    def step(
        self,
        declaration: object,
        message: str | None = None,
        typed_input: BaseModel | None = None,
        /,
        *,
        params: BaseModel | Mapping[str, Any] | None = None,
        routes: Mapping[str, Any] | None = None,
        on_input: InputHandler | None = None,
        max_pauses: int = 8,
        max_steps: int | None = None,
        provider_questions: bool | None = None,
        retention: RetentionPolicy | None = None,
    ) -> StepResult:
        workflow_cls = _build_synthetic_step_workflow(self.root, declaration, typed_input, routes=routes)
        workflow_result = self.run(
            workflow_cls,
            message,
            typed_input,
            params=params,
            on_input=on_input,
            max_pauses=max_pauses,
            max_steps=max_steps,
            provider_questions=provider_questions,
            retention=retention,
        )
        route = workflow_result.last_event.tag if workflow_result.last_event is not None else None
        return StepResult(
            ok=workflow_result.ok,
            status=workflow_result.status,
            route=route,
            value=None,
            state=workflow_result.state,
            artifacts=workflow_result.artifacts,
            workflow_result=workflow_result,
        )

    def cleanup(
        self,
        *,
        older_than: timedelta | None = None,
        include_failed: bool = False,
        dry_run: bool = False,
    ) -> CleanupResult:
        tasks_root = _sdk_tasks_root(self.root, self.state_dir)
        if not tasks_root.is_dir():
            return CleanupResult(deleted=(), skipped=(), errors={}, dry_run=dry_run)

        now = datetime.now(timezone.utc)
        deleted: list[Path] = []
        skipped: list[Path] = []
        errors: dict[Path, str] = {}
        for task_dir in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
            try:
                payload = _load_sdk_task_sentinel(task_dir)
            except SDKExecutionError:
                skipped.append(task_dir)
                continue
            if payload.get("schema") != "autoloop.sdk_task/v1":
                skipped.append(task_dir)
                continue
            if payload.get("generated_by") != "autoloop.sdk":
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


def _resolve_sdk_provider(
    *,
    root: Path,
    provider: str | LLMProvider | None,
    model: str | None,
    model_effort: str | None,
    runtime_config: RuntimeConfig,
    provider_policy_config: ProviderPolicyRuntimeConfig,
) -> LLMProvider:
    if provider is not None and not isinstance(provider, str):
        if model is not None or model_effort is not None:
            raise SDKExecutionError(
                "model and model_effort overrides are only supported when provider is a built-in provider name or None"
            )
        try:
            return validate_llm_provider(provider)
        except Exception as exc:
            raise SDKExecutionError(f"invalid provider object {type(provider).__name__!r}: {exc}", original_error=exc) from exc

    try:
        resolved = resolve_runtime_config(root, argparse.Namespace())
        provider_name = provider.strip() if isinstance(provider, str) else resolved.provider.name
        effective_provider_config = _provider_config_with_overrides(
            resolved.provider,
            provider_name=provider_name,
            model=model,
            model_effort=model_effort,
        )
        backend_config = ResolvedRuntimeConfig(
            provider=effective_provider_config,
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
    provider_name: str,
    model: str | None,
    model_effort: str | None,
) -> ProviderConfig:
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


def _resolve_and_compile_workflow(root: Path, workflow: type[object] | str) -> tuple[Any, CompiledWorkflow]:
    try:
        resolved = resolve_workflow_reference(root, workflow)
        return resolved, compile_workflow(resolved.workflow_cls)
    except Exception as exc:
        if isinstance(exc, (WorkflowCompilationError, WorkflowExecutionError)):
            raise
        if isinstance(exc, WorkflowDiscoveryError):
            raise SDKExecutionError(str(exc), original_error=exc) from exc
        raise


def _coerce_sdk_typed_input(
    compiled: CompiledWorkflow,
    typed_input: BaseModel | None,
) -> dict[str, Any] | None:
    workflow_name = compiled.workflow_cls.__name__
    input_model = compiled.input_model
    if typed_input is not None and not isinstance(typed_input, BaseModel):
        raise WorkflowInputError(
            f"{workflow_name} expects {workflow_name}.Input as the third positional argument; "
            f"received {type(typed_input).__name__}"
        )
    if input_model is None:
        if typed_input is not None:
            raise WorkflowInputError(
                f"{workflow_name} does not declare Input and does not accept typed input; "
                f"received {type(typed_input).__name__}"
            )
        return None
    if typed_input is None:
        try:
            default_input = input_model()
        except ValidationError as exc:
            raise WorkflowInputError(
                f"{workflow_name} requires {workflow_name}.Input; missing required fields: "
                f"{', '.join(sorted(_missing_validation_fields(exc)))}"
            ) from exc
        return default_input.model_dump(mode="json")
    if type(typed_input) is not input_model:
        raise WorkflowInputError(
            f"{workflow_name} expects typed input of exact type {input_model.__module__}.{input_model.__qualname__}; "
            f"received {type(typed_input).__module__}.{type(typed_input).__qualname__}"
        )
    return typed_input.model_dump(mode="json")


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
    slug = _TASK_ID_SAFE_RE.sub("-", workflow_name.strip().lower()).strip("-") or "workflow"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for _ in range(32):
        candidate = f"sdk-{slug}-{timestamp}-{uuid4().hex[:8]}"
        task_workspace = resolve_task_workspace(root, candidate, state_dir=state_dir)
        if not task_workspace.task_dir.exists():
            return candidate
    raise SDKExecutionError(f"could not generate a unique SDK task id for workflow {workflow_name!r}")


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


def _sdk_tasks_root(root: Path, state_dir: Path) -> Path:
    del root
    return state_dir / "tasks"


def _sdk_artifact_context(execution: RunExecution, *, message: str | None) -> Any:
    workflow_input = execution.workflow_input
    return SimpleNamespace(
        root=execution.task_workspace.root,
        task_id=execution.task_workspace.task_id,
        run_id=execution.run_workspace.run_id,
        workflow_name=execution.compiled.workflow_name,
        task_folder=execution.task_workspace.task_dir,
        workflow_folder=execution.workflow_workspace.workflow_dir,
        run_folder=execution.run_workspace.run_dir,
        package_folder=execution.workflow_workspace.package_dir,
        state=execution.result.state,
        message=message,
        input_fields=workflow_input,
        input=WorkflowInputView(message=message, fields=workflow_input),
    )


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


def _resolve_sdk_artifact_path(artifact: CompiledArtifact, context: Any) -> Path:
    candidate = Path(artifact.template)
    if not candidate.is_absolute() and artifact.owner_step is not None and "{" not in artifact.template and "}" not in artifact.template:
        return context.workflow_folder / artifact.owner_step / artifact.template
    return resolve_artifact_template(artifact.template, context)


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
    if isinstance(exc, AutoloopSDKError):
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
    sentinel = task_dir / ".autoloop-sdk-task.json"
    payload = {
        "schema": "autoloop.sdk_task/v1",
        "generated_by": "autoloop.sdk",
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "retention_mode": policy.mode,
    }
    sentinel.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_sdk_task_sentinel(task_dir: Path) -> dict[str, Any]:
    sentinel = task_dir / ".autoloop-sdk-task.json"
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
    sentinel = task_dir / ".autoloop-sdk-task.json"
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
    if payload.get("schema") != "autoloop.sdk_task/v1":
        raise SDKExecutionError(f"refusing to delete non-SDK or unsafe task directory {task_dir}")
    if payload.get("generated_by") != "autoloop.sdk":
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
        return root / ".autoloop" / "outputs" / "sdk" / task_id
    candidate = Path(policy.promoted_writes_dir)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate


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
    base_dir = _promotion_base_dir(root=root, task_id=task_id, policy=policy).resolve()
    relative_path = source.relative_to(resolved_task_dir)
    destination = (base_dir / relative_path).resolve()
    if not _is_inside_path(destination, base_dir):
        raise SDKExecutionError(f"refusing to promote declared write outside the promotion directory: {artifact.path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not _is_inside_path(destination, base_dir):
        destination = _uniquify_path(destination)
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


def _build_synthetic_step_workflow(
    root: Path,
    declaration: object,
    typed_input: BaseModel | None,
    *,
    routes: Mapping[str, Any] | None,
) -> type[simple.Workflow]:
    _validate_step_declaration_supported(root, declaration)
    attrs: dict[str, Any] = {
        "__module__": __name__,
        "State": _SDKStepState,
    }
    if typed_input is not None:
        attrs["Input"] = type(typed_input)
    if isinstance(declaration, Step):
        attrs["entry"] = declaration
        attrs[declaration.name] = declaration
        attrs["name"] = f"sdk_step_{_TASK_ID_SAFE_RE.sub('_', declaration.name.strip().lower()).strip('_') or 'step'}"
        attrs["transitions"] = {declaration: dict(routes) if routes is not None else _default_routes_for_step(declaration)}
        name = f"SDKStepWorkflow_{declaration.name}_{uuid4().hex[:8]}"
        return type(name, (CoreWorkflow,), attrs)

    step_name = getattr(declaration, "name", None) or "step"
    attrs[step_name] = declaration
    name = f"SDKStepWorkflow_{step_name}_{uuid4().hex[:8]}"
    return type(name, (simple.Workflow,), attrs)


class _SDKStepState(BaseModel):
    pass


def _default_routes_for_step(declaration: Step) -> dict[str, object]:
    if declaration.route_metadata:
        transitions: dict[str, object] = {}
        for route_name in declaration.route_metadata:
            if route_name in {"question", "blocked"}:
                transitions[route_name] = AWAIT_INPUT
            elif route_name == "failed":
                transitions[route_name] = FAIL
            elif isinstance(declaration, ProduceVerifyStep) and route_name == "needs_rework":
                transitions[route_name] = declaration
            else:
                transitions[route_name] = FINISH
        return transitions
    if isinstance(declaration, ProduceVerifyStep):
        return {"accepted": FINISH, "needs_rework": declaration}
    if isinstance(declaration, (PromptStep, PythonStep, ChildWorkflowStep)):
        return {"done": FINISH}
    return {"done": FINISH}


def _validate_step_declaration_supported(root: Path, declaration: object) -> None:
    if isinstance(declaration, BranchGroupStep) or getattr(declaration, "kind", None) == "branch_group":
        raise SDKExecutionError("client.step(...) does not support branch-group declarations in the MVP")
    if getattr(declaration, "scope", None) is not None:
        raise SDKExecutionError("client.step(...) does not support worklist-scoped declarations in the MVP")

    if isinstance(declaration, Step):
        if isinstance(declaration, ChildWorkflowStep):
            _ensure_child_workflow_resolvable(root, declaration.workflow)
        return

    if isinstance(declaration, getattr(simple, "_NamedDeclaration")):
        kind = getattr(declaration, "kind", None)
        if kind == "workflow":
            _ensure_child_workflow_resolvable(root, getattr(declaration, "workflow"))
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
    "Autoloop",
    "AutoloopSDKError",
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
    "SDKDebugInfo",
    "SDKExecutionError",
    "StaticInput",
    "StepResult",
    "TooManyPauses",
    "RetentionInfo",
    "RetentionPolicy",
    "WorkflowInputError",
    "WorkflowParameterError",
    "WorkflowResult",
]
