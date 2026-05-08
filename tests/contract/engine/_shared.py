from __future__ import annotations
import json
from pathlib import Path
from typing import cast
import pytest
from pydantic import BaseModel, Field
from botlane.core.compiler import compile_workflow
from botlane.core.artifacts import Artifact, render_runtime_template, resolve_artifact_template
from botlane.core.context import ChildWorkflowResult, Context
from botlane.core.engine import Engine
from botlane.core.errors import (
    MissingArtifactError,
    ProviderExecutionError,
    WorkflowExecutionError,
    WorkflowValidationError,
)
import botlane.core.lowering as workflow_lowering
from botlane.core.extensions import RunBinding, StepFinish, StepStart, TerminalFinish
from botlane.core.operations import _load_replay_store
from botlane.core.prompts import Prompt
from botlane.core.schema_registry import OPERATION_REPLAY_SCHEMA
from botlane.core import AWAIT_INPUT, FAIL, FINISH, GLOBAL, Workflow
from botlane.core.primitives import Checkpoint, Event, Fail, Goto, Outcome, RequestInput
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.providers.models import (
    OutcomeResponse,
    ProducerResponse,
    RuntimeInteractionPolicy,
    StepProviderUsage,
    TokenUsage,
)
from botlane.core.providers.rendered import RenderedLLMProvider
from botlane.core.providers.retries import ProviderRetryPolicy
from botlane.core.providers.turns import ProviderTurnResult, RenderedProviderTurn
from botlane.core.routes import Route
from botlane.core.sessions import Continuity, SessionKey
from botlane.core.steps import PromptStep, ProduceVerifyStep, Session, PythonStep, ChildWorkflowStep
from botlane.core.worklists import Selector, WorkItem, Worklist
from botlane.simple import Effects, Json, Md, ValidationResult, Workflow as SimpleWorkflow, WorklistEffect, classify, llm, produce_verify_step, python_step, step, validation_step, workflow_step
from botlane.core.stores import InMemoryCheckpointStore, InMemorySessionStore, SessionBinding, SessionSnapshot
from botlane.runtime.prompts import FilesystemPromptRegistry
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
def _chain_hooks(*hooks):
    active = tuple(hook for hook in hooks if hook is not None)
    if not active:
        return None

    def chained(ctx):
        for hook in active:
            result = hook(ctx)
            if result is not None:
                return result
        return None

    return chained
def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()
    return task_folder, run_folder
def _install_fake_jsonschema_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeValidator:
        def __init__(self, schema):
            self._schema = schema

        @staticmethod
        def check_schema(schema):
            if not isinstance(schema, dict):
                raise TypeError("schema must be a mapping")

        def validate(self, payload):
            required = self._schema.get("required", [])
            for field_name in required:
                if field_name not in payload:
                    raise ValueError(f"{field_name!r} is a required property")

    monkeypatch.setattr(workflow_lowering, "_load_jsonschema_validator_cls", lambda: _FakeValidator)
class _RenderedTransportStub:
    def __init__(
        self,
        raw_text: str = '{"tag":"done","reason":"completed"}',
        *,
        raw_texts: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.raw_text = raw_text
        self.raw_texts = list(raw_texts) if raw_texts is not None else None
        self.turns: list[RenderedProviderTurn] = []

    async def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        self.turns.append(turn)
        raw_text = self.raw_texts.pop(0) if self.raw_texts else self.raw_text
        return ProviderTurnResult(raw_text=raw_text, session=None)

    def run_turn_sync(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        self.turns.append(turn)
        raw_text = self.raw_texts.pop(0) if self.raw_texts else self.raw_text
        return ProviderTurnResult(raw_text=raw_text, session=None)
class _ConfigurableRenderedTransport(_RenderedTransportStub):
    def __init__(self, *, model: str, raw_text: str = '"summary"') -> None:
        super().__init__(raw_text=raw_text)
        self._model = model
def _rendered_provider_with_operation_executor(transport: _RenderedTransportStub) -> RenderedLLMProvider:
    return RenderedLLMProvider(transport, operation_executor=transport.run_turn_sync)
class _BoundRecorder:
    def __init__(self, name: str, sink: list[tuple[object, ...]]) -> None:
        self.name = name
        self.sink = sink

    def before_step(self, event: StepStart) -> None:
        self.sink.append((self.name, "before", event.step_name, event.step_kind, event.binding.root))

    def after_step(self, event: StepFinish) -> None:
        self.sink.append((self.name, "after", event.step_name, None if event.event is None else event.event.tag, event.state_after))

    def on_terminal(self, event: TerminalFinish) -> None:
        self.sink.append((self.name, "terminal", event.terminal, event.step_name, event.state))
class _RecordingExtension:
    def __init__(self, name: str, sink: list[tuple[object, ...]]) -> None:
        self.name = name
        self.sink = sink
        self.bindings: list[RunBinding] = []

    def bind(self, binding: RunBinding) -> _BoundRecorder:
        self.bindings.append(binding)
        return _BoundRecorder(self.name, self.sink)
class _ApprovalInput(BaseModel):
    approval: str
