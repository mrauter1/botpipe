from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from pydantic import BaseModel, Field

from autoloop.core.compiler import compile_workflow
from autoloop.core.artifacts import Artifact
from autoloop.core.context import ChildWorkflowResult
from autoloop.core.engine import Engine
from autoloop.core.errors import (
    MissingArtifactError,
    ProviderExecutionError,
    WorkflowExecutionError,
    WorkflowValidationError,
)
import autoloop.core.lowering as workflow_lowering
from autoloop.core.extensions import RunBinding, StepFinish, StepStart, TerminalFinish
from autoloop.core.operations import _load_replay_store
from autoloop.core.prompts import Prompt
from autoloop.core.schema_registry import OPERATION_REPLAY_SCHEMA
from autoloop.core import AWAIT_INPUT, FAIL, FINISH, GLOBAL, Workflow
from autoloop.core.primitives import Checkpoint, Event, Fail, Goto, Outcome, RequestInput
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.providers.models import (
    OutcomeResponse,
    ProducerResponse,
    RuntimeInteractionPolicy,
    StepProviderUsage,
    TokenUsage,
)
from autoloop.core.providers.rendered import RenderedLLMProvider
from autoloop.core.providers.retries import ProviderRetryPolicy
from autoloop.core.providers.turns import ProviderTurnResult, RenderedProviderTurn
from autoloop.core.routes import Route
from autoloop.core.sessions import Continuity, SessionKey
from autoloop.core.steps import PromptStep, ProduceVerifyStep, Session, PythonStep, ChildWorkflowStep
from autoloop.core.worklists import Selector, WorkItem, Worklist
from autoloop.simple import Effects, Json, Md, ValidationResult, Workflow as SimpleWorkflow, WorklistEffect, classify, llm, produce_verify_step, python_step, step, validation_step, workflow_step
from autoloop.core.stores import InMemoryCheckpointStore, InMemorySessionStore, SessionBinding, SessionSnapshot
from autoloop.runtime.prompts import FilesystemPromptRegistry

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


def test_runtime_extensions_bind_before_workflow_extensions(tmp_path: Path):
    events: list[str] = []

    class RuntimeBound:
        def before_step(self, event):
            events.append(f"runtime:before:{event.step_name}")

        def after_step(self, event):
            events.append(f"runtime:after:{event.step_name}")

        def on_terminal(self, event):
            events.append(f"runtime:terminal:{event.terminal}")

    class WorkflowBound:
        def before_step(self, event):
            events.append(f"workflow:before:{event.step_name}")

        def after_step(self, event):
            events.append(f"workflow:after:{event.step_name}")

        def on_terminal(self, event):
            events.append(f"workflow:terminal:{event.terminal}")

    class WorkflowExtensionRecorder:
        def bind(self, binding):
            return WorkflowBound()

    def _orderedworkflow_on_bootstrap(ctx):
        ctx.state = ctx.state.model_copy(update={'ready': True})
        return Event('done')

    class OrderedWorkflow(Workflow):
        class State(BaseModel):
            ready: bool = False

        bootstrap = PythonStep(name="bootstrap", handler=_orderedworkflow_on_bootstrap)
        entry = bootstrap
        transitions = {bootstrap: {"done": FINISH}}
        extensions = (WorkflowExtensionRecorder(),)


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        OrderedWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_extension_factories=(lambda binding: RuntimeBound(),),
    )

    result = engine.run(
        task_id="task-ordered",
        run_id="run-ordered",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert events == [
        "runtime:before:bootstrap",
        "workflow:before:bootstrap",
        "runtime:after:bootstrap",
        "workflow:after:bootstrap",
        "runtime:terminal:FINISH",
        "workflow:terminal:FINISH",
    ]


def test_low_level_engine_requires_prompt_registry_for_relative_file_prompts(tmp_path: Path):
    (tmp_path / "ask.md").write_text("Answer the request.\n", encoding="utf-8")

    def _filepromptworkflow_on_ask(ctx):
        return None

    class FilePromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer=Prompt.file("ask.md"), retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub()
    provider = RenderedLLMProvider(transport)

    with pytest.raises(ProviderExecutionError, match="did not resolve to text"):
        Engine(
            FilePromptWorkflow,
            provider=provider,
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-file-prompt-missing-registry",
            run_id="run-file-prompt-missing-registry",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    assert transport.turns == []


def test_low_level_engine_resolves_relative_file_prompts_with_filesystem_registry(tmp_path: Path):
    prompt_path = tmp_path / "ask.md"
    prompt_path.write_text("Answer the request.\n", encoding="utf-8")

    def _filepromptworkflow_on_ask(ctx):
        return None

    class FilePromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer=Prompt.file("ask.md"), retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub()
    result = Engine(
        FilePromptWorkflow,
        provider=_rendered_provider_with_operation_executor(transport),
        prompt_registry=FilesystemPromptRegistry(tmp_path),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-file-prompt-with-registry",
        run_id="run-file-prompt-with-registry",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(transport.turns) == 1
    assert "Answer the request." in transport.turns[0].prompt_text


def test_extension_core_modules_remain_autoloop_agnostic():
    engine_text = (PACKAGE_ROOT / "autoloop" / "core" / "engine.py").read_text(encoding="utf-8")
    extension_text = (PACKAGE_ROOT / "autoloop" / "core" / "extensions.py").read_text(encoding="utf-8")
    corpus = f"{engine_text}\n{extension_text}"

    for forbidden in (
        "autoloop_v1",
        "run_autoloop_v1",
        "autoloop_v1_support",
        "autoloop_v1_parity",
        "autoloop_v1_conventions",
        "activate_next_phase",
        "phase_selected",
        "phase_started",
        "phase_completed",
    ):
        assert forbidden not in corpus


def test_pair_step_contract_logs_raw_output_and_updates_state(tmp_path: Path):
    def _pairworkflow_on_start(ctx):
        ctx.open_session(PairWorkflow.main)

    def _pairworkflow_on_pair(ctx):
        ctx.state = ctx.state.model_copy(update={'draft_text': ctx.artifacts.draft.read_text()})
        return None

    def _pairworkflow_on_finish(ctx):
        return Event('done')

    class PairWorkflow(Workflow):
        class State(BaseModel):
            draft_text: str = ""

        main = Session()
        request = Artifact("{task_folder}/request.txt")
        raw_log = Artifact("{run_folder}/pair.log")
        pair = ProduceVerifyStep(
            name="pair",
            session=main,
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            requires=[request],
            producer_writes={"draft": Artifact("{run_folder}/draft.txt")},
            log_artifacts=[raw_log],
        )
        finish = PythonStep(name="finish", handler=_pairworkflow_on_finish)
        entry = pair
        transitions = {pair: {"pair_ok": finish}, finish: {"done": FINISH}}
    PairWorkflow.pair.before = _chain_hooks(_pairworkflow_on_start, PairWorkflow.pair.before)
    PairWorkflow.pair.after_verifier = _chain_hooks(_pairworkflow_on_pair, PairWorkflow.pair.after_verifier)


    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "request.txt").write_text("request", encoding="utf-8")
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.draft.write_text("artifact draft"),
                "producer raw\n",
            )[1]
        ],
        verifier_turns=[Outcome(raw_output="verified", tag="pair_ok")],
    )
    engine = Engine(
        PairWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.draft_text == "artifact draft"
    assert (run_folder / "pair.log").read_text(encoding="utf-8") == "producer raw\n"
    assert result.history == ("pair", "finish")
    assert [(call.kind, call.step_name, call.prompt_path) for call in provider.calls] == [
        ("producer", "pair", "pair/producer.md"),
        ("verifier", "pair", "pair/verifier.md"),
    ]


def test_step_finish_exposes_raw_outputs_for_package_local_parity_extensions(tmp_path: Path):
    pair_usage = StepProviderUsage(
        producer=TokenUsage(input_tokens=5, output_tokens=7, total_tokens=12, source="fake"),
        verifier=TokenUsage(input_tokens=11, output_tokens=3, total_tokens=14, source="fake"),
    )
    llm_usage = StepProviderUsage(llm=TokenUsage(input_tokens=2, output_tokens=4, total_tokens=6, source="fake"))
    seen: list[tuple[str, str | None, str | None, StepProviderUsage | None]] = []

    class RawOutputExtension:
        def bind(self, binding):
            class Bound:
                def before_step(self, event):
                    return None

                def after_step(self, event):
                    seen.append((event.step_name, event.producer_raw_output, event.verifier_raw_output, event.provider_usage))

                def on_terminal(self, event):
                    return None

            return Bound()

    def _rawoutputworkflow_on_start(ctx):
        ctx.open_session(RawOutputWorkflow.main)

    def _rawoutputworkflow_on_finish(ctx):
        return Event('complete')

    class RawOutputWorkflow(Workflow):
        class State(BaseModel):
            note: str = ""

        main = Session()
        request = Artifact("{task_folder}/request.txt")
        pair = ProduceVerifyStep(name="pair", producer="pair/producer.md", verifier="pair/verifier.md", requires=[request], session=main)
        ask = PromptStep(name="ask", producer="ask.md", session=main)
        finish = PythonStep(name="finish", handler=_rawoutputworkflow_on_finish)
        entry = pair
        transitions = {pair: {"pair_ok": ask}, ask: {"done": finish}, finish: {"complete": FINISH}}
        extensions = (RawOutputExtension(),)
    RawOutputWorkflow.pair.before = _chain_hooks(_rawoutputworkflow_on_start, RawOutputWorkflow.pair.before)


    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "request.txt").write_text("request", encoding="utf-8")
    engine = Engine(
        RawOutputWorkflow,
        provider=ScriptedLLMProvider(
            producer_turns=[
                ProducerResponse(
                    raw_output="pair producer raw\n",
                    usage=pair_usage.producer,
                )
            ],
            verifier_turns=[
                OutcomeResponse(
                    outcome=Outcome(raw_output="pair verifier raw\n", tag="pair_ok"),
                    usage=pair_usage.verifier,
                )
            ],
            llm_turns=[
                OutcomeResponse(
                    outcome=Outcome(raw_output="llm raw\n", tag="done"),
                    usage=llm_usage.llm,
                )
            ],
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert seen == [
        ("pair", "pair producer raw\n", "pair verifier raw\n", pair_usage),
        ("ask", "llm raw\n", None, llm_usage),
        ("finish", None, None, None),
    ]


def test_pair_and_llm_handlers_remain_optional(tmp_path: Path):
    def _optionalhandlerworkflow_on_start(ctx):
        ctx.open_session(OptionalHandlerWorkflow.main)

    def _optionalhandlerworkflow_on_finish(ctx):
        ctx.state = ctx.state.model_copy(update={'finished': True})
        return Event('complete')

    class OptionalHandlerWorkflow(Workflow):
        class State(BaseModel):
            finished: bool = False

        main = Session()
        request = Artifact("{task_folder}/request.txt")
        pair = ProduceVerifyStep(name="pair", producer="pair/producer.md", verifier="pair/verifier.md", requires=[request], session=main)
        ask = PromptStep(name="ask", producer="ask.md", session=main)
        finish = PythonStep(name="finish", handler=_optionalhandlerworkflow_on_finish)
        entry = pair
        transitions = {pair: {"pair_ok": ask}, ask: {"done": finish}, finish: {"complete": FINISH}}
    OptionalHandlerWorkflow.pair.before = _chain_hooks(_optionalhandlerworkflow_on_start, OptionalHandlerWorkflow.pair.before)


    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "request.txt").write_text("request", encoding="utf-8")
    engine = Engine(
        OptionalHandlerWorkflow,
        provider=ScriptedLLMProvider(
            producer_turns=["producer raw"],
            verifier_turns=[Outcome(raw_output="verified", tag="pair_ok")],
            llm_turns=[Outcome(raw_output="done", tag="done")],
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.finished is True
    assert result.history == ("pair", "ask", "finish")


def test_llm_step_contract_logs_outcome_raw_output_and_uses_global_route(tmp_path: Path):
    def _llmworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'tag_seen': ctx.outcome.tag})
        return None

    class LLMWorkflow(Workflow):
        class State(BaseModel):
            tag_seen: str = ""

        request = Artifact("{task_folder}/request.txt")
        raw_log = Artifact("{run_folder}/llm.log")
        ask = PromptStep(
            name="ask",
            producer="ask.md",
            requires=[request],
            log_artifacts=[raw_log],
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {"done": FINISH},
            GLOBAL: {"failed": "FAIL"},
        }

    LLMWorkflow.ask.after = _chain_hooks(_llmworkflow_on_ask, LLMWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "request.txt").write_text("request", encoding="utf-8")
    provider = ScriptedLLMProvider(
        llm_turns=[Outcome(raw_output="bad\n", tag="failed", reason="The request could not be completed.")]
    )
    engine = Engine(
        LLMWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == "FAIL"
    assert result.state.tag_seen == "failed"
    assert (run_folder / "llm.log").read_text(encoding="utf-8") == "bad\n"
    assert [(call.kind, call.step_name, call.prompt_path) for call in provider.calls] == [("step", "ask", "ask.md")]


def test_route_objects_execute_without_breaking_engine_routing(tmp_path: Path):
    def _typedrouteworkflow_on_ask(ctx):
        return None

    def _typedrouteworkflow_on_finish(ctx):
        ctx.state = ctx.state.model_copy(update={'finished': True})
        return Event('complete')

    class TypedRouteWorkflow(Workflow):
        class State(BaseModel):
            finished: bool = False

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Answer the request."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        finish = PythonStep(name="finish", handler=_typedrouteworkflow_on_finish)
        entry = ask
        transitions = {
            ask: {"done": Route.to(finish)},
            finish: {"complete": Route.finish()},
        }


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        TypedRouteWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok\n", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.finished is True
    assert result.history == ("ask", "finish")


def test_llm_requests_include_step_control_contracts(tmp_path: Path):
    class ReviewPayload(BaseModel):
        summary: str

    def _contractworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'summary': ctx.outcome.payload['summary']})
        return None

    class ContractWorkflow(Workflow):
        class State(BaseModel):
            summary: str = ""

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            expected_output_schema=ReviewPayload,
            route_metadata={"done": "workflow completed cleanly"},
        )
        entry = ask
        transitions = {
            ask: {"done": FINISH},
            GLOBAL: {"failed": FAIL},
        }

    ContractWorkflow.ask.after = _chain_hooks(_contractworkflow_on_ask, ContractWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[Outcome(raw_output="ok", tag="done", payload={"summary": "ready"})]
    )
    engine = Engine(
        ContractWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    call = provider.calls[0]
    assert result.terminal == FINISH
    assert result.state.summary == "ready"
    assert call.kind == "step"
    assert call.available_routes == ("done", "failed", "question")
    assert call.routes["done"].summary == "workflow completed cleanly"
    assert call.expected_output_schema is not None
    assert call.expected_output_schema["required"] == ["summary"]
    assert call.readable_artifacts == ()
    assert call.required_artifacts == ()
    assert call.writable_artifacts == ()
    assert call.route_required_writes == {
        "done": (),
        "failed": (),
        "question": (),
    }
    assert call.attempt == 1
    assert call.max_attempts == 3


def test_pair_requests_include_step_control_contracts(tmp_path: Path):
    class VerdictPayload(BaseModel):
        verdict: str

    def _paircontractworkflow_on_pair(ctx):
        ctx.state = ctx.state.model_copy(update={'verdict': ctx.outcome.payload['verdict']})
        return None

    def _paircontractworkflow_on_finish(ctx):
        return Event('done')

    class PairContractWorkflow(Workflow):
        class State(BaseModel):
            verdict: str = ""

        request = Artifact("{task_folder}/request.txt")
        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            requires=[request],
            expected_output_schema=VerdictPayload,
            route_metadata={"pair_ok": "verification finished"},
        )
        finish = PythonStep(name="finish", handler=_paircontractworkflow_on_finish)
        entry = pair
        transitions = {
            pair: {"pair_ok": finish},
            finish: {"done": FINISH},
            GLOBAL: {"failed": FAIL},
        }
    PairContractWorkflow.pair.after_verifier = _chain_hooks(_paircontractworkflow_on_pair, PairContractWorkflow.pair.after_verifier)


    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "request.txt").write_text("request", encoding="utf-8")
    provider = ScriptedLLMProvider(
        producer_turns=["producer raw\n"],
        verifier_turns=[Outcome(raw_output="verified", tag="pair_ok", payload={"verdict": "approve"})],
    )
    engine = Engine(
        PairContractWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.verdict == "approve"
    assert [(call.kind, call.available_routes) for call in provider.calls] == [
        ("producer", ()),
        ("verifier", ("pair_ok", "failed", "question")),
    ]
    assert provider.calls[0].routes == {}
    assert provider.calls[0].expected_output_schema is None
    assert provider.calls[1].expected_output_schema is not None
    assert provider.calls[0].readable_artifacts == ()
    assert [ref.qualified_name for ref in provider.calls[0].required_artifacts] == ["request"]
    assert provider.calls[0].writable_artifacts == ()
    assert provider.calls[0].route_required_writes == {}
    assert provider.calls[1].routes["pair_ok"].summary == "verification finished"


def test_full_auto_hides_default_question_route_from_provider_contract(tmp_path: Path):
    class FullAutoQuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Answer the request."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    result = Engine(
        FullAutoQuestionWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        interaction_policy=RuntimeInteractionPolicy(allow_provider_questions=False),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert provider.calls[0].available_routes == ("done",)


def test_step_contract_keeps_missing_workspace_reads_visible_as_unavailable_context(tmp_path: Path):
    def _missingreadworkflow_on_ask(ctx):
        return None

    class MissingReadWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", reads=["notes/missing.txt"])
        entry = ask
        transitions = {ask: {"done": FINISH}}

    MissingReadWorkflow.ask.after = _chain_hooks(_missingreadworkflow_on_ask, MissingReadWorkflow.ask.after)

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    result = Engine(
        MissingReadWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(provider.calls) == 1
    readable_ref = provider.calls[0].readable_artifacts[0]
    assert readable_ref.name == "notes/missing.txt"
    assert readable_ref.path == str((tmp_path / "notes/missing.txt").resolve())
    assert readable_ref.exists is False
    assert readable_ref.declared_artifact is False


def test_invalid_route_tag_raises_provider_execution_error_and_checkpoints(tmp_path: Path):
    def _invalidrouteworkflow_on_ask(ctx):
        return None

    class InvalidRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Answer the request."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {"done": FINISH},
            GLOBAL: {"failed": FAIL},
        }


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        InvalidRouteWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="oops", tag="unexpected")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match="illegal route 'unexpected'"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert len(engine.provider.calls) == 1
    assert engine.provider.calls[0].attempt == 1
    assert engine.provider.calls[0].retry_feedback is None


def test_invalid_expected_output_payload_raises_provider_execution_error_and_checkpoints(tmp_path: Path):
    class ReviewPayload(BaseModel):
        summary: str

    def _invalidpayloadworkflow_on_ask(ctx):
        return None

    class InvalidPayloadWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            expected_output_schema=ReviewPayload,
            route_metadata={"done": "workflow completed cleanly"},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        InvalidPayloadWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done", payload={})]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match="invalid payload"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert len(engine.provider.calls) == 1
    assert engine.provider.calls[0].attempt == 1


def test_scripted_provider_rejects_invalid_custom_raw_route_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_jsonschema_validator(monkeypatch)
    raw_payload_schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }

    class RawRoutePayloadWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Answer the request."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "done": Route.finish(payload_schema=raw_payload_schema),
            }
        }

    task_folder, run_folder = _workspace(tmp_path)
    with pytest.raises(ProviderExecutionError, match="invalid payload"):
        Engine(
            RawRoutePayloadWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="bad payload", tag="done", payload={})]),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-raw-route-payload-scripted",
            run_id="run-raw-route-payload-scripted",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_scripted_provider_rejects_invalid_custom_raw_route_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_jsonschema_validator(monkeypatch)
    raw_route_fields_schema = {
        "type": "object",
        "properties": {"reason": {"type": "string"}},
        "required": ["reason"],
        "additionalProperties": False,
    }

    class RawRouteFieldsWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Answer the request."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "done": Route.finish(route_fields_schema=raw_route_fields_schema),
            }
        }

    task_folder, run_folder = _workspace(tmp_path)
    with pytest.raises(ProviderExecutionError, match="invalid payload"):
        Engine(
            RawRouteFieldsWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="bad route fields", tag="done", route_fields={})]),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-raw-route-fields-scripted",
            run_id="run-raw-route-fields-scripted",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_rendered_provider_rejects_invalid_custom_raw_route_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_jsonschema_validator(monkeypatch)
    raw_payload_schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }

    class RawRoutePayloadWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Answer the request."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "done": Route.finish(payload_schema=raw_payload_schema),
            }
        }

    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub(raw_text='{"outcome":{"tag":"done","payload":{},"route_fields":{}}}')

    with pytest.raises(ProviderExecutionError, match="invalid payload"):
        Engine(
            RawRoutePayloadWorkflow,
            provider=RenderedLLMProvider(transport),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-raw-route-payload-rendered",
            run_id="run-raw-route-payload-rendered",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_rendered_provider_rejects_invalid_custom_raw_route_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_jsonschema_validator(monkeypatch)
    raw_route_fields_schema = {
        "type": "object",
        "properties": {"reason": {"type": "string"}},
        "required": ["reason"],
        "additionalProperties": False,
    }

    class RawRouteFieldsWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Answer the request."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "done": Route.finish(route_fields_schema=raw_route_fields_schema),
            }
        }

    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub(raw_text='{"outcome":{"tag":"done","payload":{},"route_fields":{}}}')

    with pytest.raises(ProviderExecutionError, match="invalid payload"):
        Engine(
            RawRouteFieldsWorkflow,
            provider=RenderedLLMProvider(transport),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-raw-route-fields-rendered",
            run_id="run-raw-route-fields-rendered",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_question_route_requires_question_field(tmp_path: Path):
    def _questionworkflow_on_ask(ctx):
        return None

    class QuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}


    task_folder, run_folder = _workspace(tmp_path)
    with pytest.raises(ProviderExecutionError, match="question route without a non-empty question"):
        Engine(
            QuestionWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="need input", tag="question")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_provider_invalid_question_retries_and_recovers(tmp_path: Path):
    def _questionworkflow_on_ask(ctx):
        return None

    class QuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=2))
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="need input", tag="question", reason="Need input"),
            Outcome(raw_output="need input", tag="question", reason="Need input", question="Approve?"),
        ]
    )
    result = Engine(
        QuestionWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == AWAIT_INPUT
    assert result.checkpoint is not None
    assert result.checkpoint.pending_input is not None
    assert result.checkpoint.pending_input.question == "Approve?"
    assert [call.attempt for call in provider.calls] == [1, 2]
    assert provider.calls[1].retry_feedback is not None
    assert (
        "The selected route 'question' has an invalid payload: "
        "question route requires a non-empty question field."
    ) in provider.calls[1].retry_feedback


def test_rendered_provider_invalid_question_retries_and_recovers(tmp_path: Path):
    class QuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Ask for the missing input when needed."),
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}

    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub(
        raw_texts=[
            '{"tag":"question"}',
            '{"tag":"question","question":"Approve?"}',
        ]
    )
    result = Engine(
        QuestionWorkflow,
        provider=RenderedLLMProvider(transport),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == AWAIT_INPUT
    assert result.checkpoint is not None
    assert result.checkpoint.pending_input is not None
    assert result.checkpoint.pending_input.question == "Approve?"
    assert len(transport.turns) == 2
    assert (
        "The selected route 'question' has an invalid payload: "
        "question route requires a non-empty question field."
    ) in transport.turns[1].prompt_text


def test_rendered_provider_canonical_question_route_does_not_fall_back_to_legacy_question(tmp_path: Path):
    class QuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Ask for the missing input when needed."),
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}

    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub(
        raw_texts=[
            '{"outcome":{"tag":"question","payload":{},"route_fields":{}},"question":"Legacy?"}',
            '{"outcome":{"tag":"question","payload":{},"route_fields":{"questions":["Approve?"],"reason":null}}}',
        ]
    )
    result = Engine(
        QuestionWorkflow,
        provider=RenderedLLMProvider(transport),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == AWAIT_INPUT
    assert result.checkpoint is not None
    assert result.checkpoint.pending_input is not None
    assert result.checkpoint.pending_input.question == "Approve?"
    assert len(transport.turns) == 2
    assert (
        "The selected route 'question' has an invalid payload: "
        "question route requires a non-empty question field."
    ) in transport.turns[1].prompt_text


def test_explicit_blocked_and_failed_routes_do_not_require_reason_field(tmp_path: Path):
    def _failureworkflow_on_ask(ctx):
        return None

    class FailureWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Choose a legal route."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"blocked": AWAIT_INPUT, "failed": FAIL}}

    task_folder, run_folder = _workspace(tmp_path)
    blocked_result = Engine(
        FailureWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="blocked", tag="blocked")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-blocked",
        run_id="run-blocked",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )
    failed_result = Engine(
        FailureWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="failed", tag="failed")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-failed",
        run_id="run-failed",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert blocked_result.terminal == AWAIT_INPUT
    assert blocked_result.last_event is not None
    assert blocked_result.last_event.tag == "blocked"
    assert blocked_result.last_event.reason == ""
    assert failed_result.terminal == FAIL
    assert failed_result.last_event is not None
    assert failed_result.last_event.tag == "failed"
    assert failed_result.last_event.reason == ""


def test_rendered_provider_matches_direct_reason_optional_behavior_for_explicit_blocked_and_failed_routes(tmp_path: Path):
    class FailureWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Choose a legal route."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"blocked": AWAIT_INPUT, "failed": FAIL}}

    task_folder, run_folder = _workspace(tmp_path)
    blocked_result = Engine(
        FailureWorkflow,
        provider=RenderedLLMProvider(_RenderedTransportStub(raw_text='{"tag":"blocked"}')),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-blocked",
        run_id="run-blocked",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )
    failed_result = Engine(
        FailureWorkflow,
        provider=RenderedLLMProvider(_RenderedTransportStub(raw_text='{"tag":"failed"}')),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-failed",
        run_id="run-failed",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert blocked_result.terminal == AWAIT_INPUT
    assert blocked_result.last_event is not None
    assert blocked_result.last_event.tag == "blocked"
    assert blocked_result.last_event.reason == ""
    assert failed_result.terminal == FAIL
    assert failed_result.last_event is not None
    assert failed_result.last_event.tag == "failed"
    assert failed_result.last_event.reason == ""


def test_provider_question_route_is_illegal_in_full_auto_mode(tmp_path: Path):
    def _fullautoworkflow_on_ask(ctx):
        return None

    class FullAutoQuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Choose a legal route."),
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="need input", tag="question", question="Approve?"),
            Outcome(raw_output="done", tag="done"),
        ]
    )
    result = Engine(
        FullAutoQuestionWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        interaction_policy=RuntimeInteractionPolicy(allow_provider_questions=False),
    ).run(
        task_id="task-full-auto",
        run_id="run-full-auto",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert [call.attempt for call in provider.calls] == [1, 2]
    assert provider.calls[1].retry_feedback is not None
    assert "The selected route was not allowed for step 'ask'." in provider.calls[1].retry_feedback


def test_rendered_provider_question_route_is_illegal_in_full_auto_mode(tmp_path: Path):
    class FullAutoQuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Choose a legal route."),
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub(
        raw_texts=[
            '{"tag":"question","question":"Approve?"}',
            '{"tag":"done"}',
        ]
    )
    result = Engine(
        FullAutoQuestionWorkflow,
        provider=RenderedLLMProvider(transport),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        interaction_policy=RuntimeInteractionPolicy(allow_provider_questions=False),
    ).run(
        task_id="task-full-auto",
        run_id="run-full-auto",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(transport.turns) == 2
    assert "question-style route" in transport.turns[1].prompt_text
    assert "outcome.route_fields.questions" in transport.turns[1].prompt_text


def test_provider_invalid_question_retry_exhaustion_marks_failure_context(tmp_path: Path):
    def _questionworkflow_on_ask(ctx):
        return None

    class QuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=2))
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="need input", tag="question", reason="Need input"),
            Outcome(raw_output="need input", tag="question", reason="Need input"),
        ]
    )
    engine = Engine(
        QuestionWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match="question route without a non-empty question"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert checkpoint.pending_question is None
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "invalid_payload"
    assert checkpoint.failure_context["route"] == "question"
    assert checkpoint.failure_context["provider_attributable"] is True
    assert checkpoint.failure_context["retry_exhausted"] is True
    assert [call.attempt for call in provider.calls] == [1, 2]


def test_rendered_provider_invalid_question_retry_exhaustion_marks_failure_context(tmp_path: Path):
    class QuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Ask for the missing input when needed."),
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        QuestionWorkflow,
        provider=RenderedLLMProvider(
            _RenderedTransportStub(
                raw_texts=[
                    '{"tag":"question"}',
                    '{"tag":"question"}',
                ]
            )
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match="question route without a non-empty question"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert checkpoint.pending_question is None
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "invalid_payload"
    assert checkpoint.failure_context["route"] == "question"
    assert checkpoint.failure_context["provider_attributable"] is True
    assert checkpoint.failure_context["retry_exhausted"] is True


def test_system_question_events_validate_strictly_and_failed_remains_authored(tmp_path: Path):
    def _askquestionworkflow_on_ask(ctx):
        return Event('question', question='Need input?')

    class AskQuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PythonStep(name="ask", handler=_askquestionworkflow_on_ask)
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}


    def _invalidquestionworkflow_on_ask(ctx):
        return Event('question')

    class InvalidQuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PythonStep(name="ask", handler=_invalidquestionworkflow_on_ask)
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}


    def _failworkflow_on_ask(ctx):
        return Event('failed', reason='Could not continue.')

    class FailWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PythonStep(name="ask", handler=_failworkflow_on_ask)
        entry = ask
        transitions = {ask: {"failed": FAIL}}


    task_folder, run_folder = _workspace(tmp_path)
    paused = Engine(
        AskQuestionWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-pause",
        run_id="run-pause",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )
    failed = Engine(
        FailWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-fail",
        run_id="run-fail",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == AWAIT_INPUT
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_input is not None
    assert paused.checkpoint.pending_input.question == "Need input?"
    assert failed.terminal == FAIL
    assert failed.last_event is not None
    assert failed.last_event.reason == "Could not continue."

    with pytest.raises(WorkflowExecutionError, match="question route without a non-empty question"):
        Engine(
            InvalidQuestionWorkflow,
            provider=ScriptedLLMProvider(),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-bad-question",
            run_id="run-bad-question",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )



def test_llm_step_retries_illegal_route_twice_and_succeeds_on_third_attempt(tmp_path: Path):
    def _retryrouteworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'final_note': ctx.outcome.raw_output})
        return None

    class RetryRouteWorkflow(Workflow):
        class State(BaseModel):
            final_note: str = ""

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}, GLOBAL: {"failed": FAIL}}

    RetryRouteWorkflow.ask.after = _chain_hooks(_retryrouteworkflow_on_ask, RetryRouteWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="first", tag="unexpected"),
            Outcome(raw_output="second", tag="unexpected"),
            Outcome(raw_output="third", tag="done"),
        ]
    )
    result = Engine(
        RetryRouteWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.final_note == "third"
    assert [call.attempt for call in provider.calls] == [1, 2, 3]
    assert provider.calls[0].retry_feedback is None
    assert provider.calls[1].retry_feedback is not None
    assert "selected route was not allowed" in provider.calls[1].retry_feedback
    assert provider.calls[2].retry_feedback is not None


def test_llm_step_retries_invalid_payload_twice_and_succeeds_on_third_attempt(tmp_path: Path):
    class ReviewPayload(BaseModel):
        summary: str

    def _retrypayloadworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'summary': ctx.outcome.payload['summary']})
        return None

    class RetryPayloadWorkflow(Workflow):
        class State(BaseModel):
            summary: str = ""

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            expected_output_schema=ReviewPayload,
            route_metadata={"done": "workflow completed cleanly"},
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    RetryPayloadWorkflow.ask.after = _chain_hooks(_retrypayloadworkflow_on_ask, RetryPayloadWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="one", tag="done", payload={}),
            Outcome(raw_output="two", tag="done", payload={}),
            Outcome(raw_output="three", tag="done", payload={"summary": "ready"}),
        ]
    )
    result = Engine(
        RetryPayloadWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.summary == "ready"
    assert [call.attempt for call in provider.calls] == [1, 2, 3]
    assert provider.calls[1].retry_feedback is not None
    assert "The selected route 'done' has an invalid payload:" in provider.calls[1].retry_feedback
    assert "summary" in provider.calls[1].retry_feedback


def test_retry_policy_can_disable_illegal_route_retries(tmp_path: Path):
    def _noillegalrouteretryworkflow_on_ask(ctx):
        return None

    class NoIllegalRouteRetryWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            retry_policy=ProviderRetryPolicy(
                max_attempts=3,
                retry_illegal_route=False,
            ),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}, GLOBAL: {"failed": FAIL}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="bad-route", tag="unexpected"),
            Outcome(raw_output="would-have-succeeded", tag="done"),
        ]
    )
    engine = Engine(
        NoIllegalRouteRetryWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match="illegal route 'unexpected'"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "illegal_route"
    assert "retry_exhausted" not in checkpoint.failure_context
    assert len(provider.calls) == 1
    assert provider.calls[0].attempt == 1
    assert provider.calls[0].retry_feedback is None


def test_llm_step_retries_malformed_provider_output_twice_and_succeeds_on_third_attempt(tmp_path: Path):
    def _retrymalformedoutputworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'note': ctx.outcome.raw_output})
        return None

    class RetryMalformedOutputWorkflow(Workflow):
        class State(BaseModel):
            note: str = ""

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    RetryMalformedOutputWorkflow.ask.after = _chain_hooks(_retrymalformedoutputworkflow_on_ask, RetryMalformedOutputWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: OutcomeResponse(outcome="bad"),  # type: ignore[arg-type]
            lambda request: OutcomeResponse(outcome="still-bad"),  # type: ignore[arg-type]
            Outcome(raw_output="third", tag="done"),
        ]
    )
    result = Engine(
        RetryMalformedOutputWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.note == "third"
    assert [call.attempt for call in provider.calls] == [1, 2, 3]
    assert provider.calls[0].retry_feedback is None
    assert provider.calls[1].retry_feedback is not None
    assert "could not be parsed into a valid workflow outcome" in provider.calls[1].retry_feedback
    assert provider.calls[2].retry_feedback is not None


def test_llm_step_retries_provider_transport_failure_twice_and_succeeds_on_third_attempt(tmp_path: Path):
    def _retrytransportfailureworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'note': ctx.outcome.raw_output})
        return None

    class RetryTransportFailureWorkflow(Workflow):
        class State(BaseModel):
            note: str = ""

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    RetryTransportFailureWorkflow.ask.after = _chain_hooks(_retrytransportfailureworkflow_on_ask, RetryTransportFailureWorkflow.ask.after)


    def transport_failure(_request):
        raise ProviderExecutionError("provider failed while running step 'ask': boom")

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            transport_failure,
            transport_failure,
            Outcome(raw_output="recovered", tag="done"),
        ]
    )
    result = Engine(
        RetryTransportFailureWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.note == "recovered"
    assert [call.attempt for call in provider.calls] == [1, 2, 3]
    assert provider.calls[0].retry_feedback is None
    assert provider.calls[1].retry_feedback is not None
    assert "transport failed before a usable response was accepted" in provider.calls[1].retry_feedback
    assert provider.calls[2].retry_feedback is not None


def test_pair_step_retries_from_producer_when_route_required_artifact_is_missing(tmp_path: Path):
    def _retrypairworkflow_on_review(ctx):
        if ctx.outcome.payload.get('write_report'):
            ctx.artifacts.report.write_text('ready')
        ctx.state = ctx.state.model_copy(update={'verified': True})
        return None

    class RetryPairWorkflow(Workflow):
        class State(BaseModel):
            verified: bool = False

        review = ProduceVerifyStep(
            name="review",
            producer="review.md",
            verifier="verify.md",
            producer_writes={"report": Artifact.md("report.md")},
            route_metadata={"done": Route(summary="review completed", required_writes=("report",))},
        )
        entry = review
        transitions = {review: {"done": FINISH}}

    RetryPairWorkflow.review.after_verifier = _chain_hooks(_retrypairworkflow_on_review, RetryPairWorkflow.review.after_verifier)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["draft-one", "draft-two"],
        verifier_turns=[
            Outcome(raw_output="verify-one", tag="done", payload={"write_report": False}),
            Outcome(raw_output="verify-two", tag="done", payload={"write_report": True}),
        ],
    )
    result = Engine(
        RetryPairWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.verified is True
    assert [(call.kind, call.attempt) for call in provider.calls] == [
        ("producer", 1),
        ("verifier", 1),
        ("producer", 2),
        ("verifier", 2),
    ]
    assert [ref.qualified_name for ref in provider.calls[0].writable_artifacts] == ["review.report"]
    assert provider.calls[0].route_required_writes == {}
    assert provider.calls[2].retry_feedback is not None
    assert "missing required output artifact" in provider.calls[2].retry_feedback
    assert "draft-one" not in provider.calls[2].retry_feedback
    assert "verify-one" not in provider.calls[2].retry_feedback


def test_llm_retry_reuses_pre_step_session_not_failed_attempt_session(tmp_path: Path):
    def _sessionretryworkflow_on_start(ctx):
        ctx.open_session(SessionRetryWorkflow.main)

    def _sessionretryworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'final_session_id': ctx.outcome.payload['session_id']})
        return None

    class SessionRetryWorkflow(Workflow):
        class State(BaseModel):
            final_session_id: str = ""

        main = Session()
        ask = PromptStep(name="ask", producer="ask.md", session=main)
        entry = ask
        transitions = {ask: {"done": FINISH}, GLOBAL: {"failed": FAIL}}


    SessionRetryWorkflow.ask.before = _chain_hooks(_sessionretryworkflow_on_start, SessionRetryWorkflow.ask.before)
    SessionRetryWorkflow.ask.after = _chain_hooks(_sessionretryworkflow_on_ask, SessionRetryWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    seen_request_sessions: list[tuple[int, str | None]] = []

    def illegal_route(request):
        seen_request_sessions.append((request.attempt, request.session.session_id if request.session is not None else None))
        assert request.session is not None
        return OutcomeResponse(
            outcome=Outcome(raw_output="bad", tag="unexpected"),
            session=SessionBinding(key=request.session.key, session_id="retry-attempt-1"),
        )

    def accepted(request):
        seen_request_sessions.append((request.attempt, request.session.session_id if request.session is not None else None))
        assert request.session is not None
        return OutcomeResponse(
            outcome=Outcome(
                raw_output="ok",
                tag="done",
                payload={"session_id": "retry-attempt-2"},
            ),
            session=SessionBinding(key=request.session.key, session_id="retry-attempt-2"),
        )

    result = Engine(
        SessionRetryWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[illegal_route, accepted]),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(seen_request_sessions) == 2
    assert seen_request_sessions[0][0] == 1
    assert seen_request_sessions[1][0] == 2
    assert seen_request_sessions[0][1] is not None
    assert seen_request_sessions[1][1] == seen_request_sessions[0][1]
    final_binding = session_store.get("main")
    assert final_binding is not None
    assert final_binding.session_id == "retry-attempt-2"


def test_pair_retry_reuses_pre_step_session_but_keeps_attempt_local_session_chain(tmp_path: Path):
    def _pairsessionretryworkflow_on_start(ctx):
        ctx.open_session(PairSessionRetryWorkflow.main)

    def _pairsessionretryworkflow_on_review(ctx):
        if ctx.outcome.payload.get('write_report'):
            ctx.artifacts.report.write_text('ready')
        ctx.state = ctx.state.model_copy(update={'final_session_id': ctx.outcome.payload['session_id']})
        return None

    class PairSessionRetryWorkflow(Workflow):
        class State(BaseModel):
            final_session_id: str = ""

        main = Session()
        review = ProduceVerifyStep(
            name="review",
            producer="review.md",
            verifier="verify.md",
            session=main,
            producer_writes={"report": Artifact.md("report.md")},
            route_metadata={"done": Route(summary="review completed", required_writes=("report",))},
        )
        entry = review
        transitions = {review: {"done": FINISH}}


    PairSessionRetryWorkflow.review.before = _chain_hooks(_pairsessionretryworkflow_on_start, PairSessionRetryWorkflow.review.before)
    PairSessionRetryWorkflow.review.after_verifier = _chain_hooks(_pairsessionretryworkflow_on_review, PairSessionRetryWorkflow.review.after_verifier)


    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    producer_sessions: list[tuple[int, str | None]] = []
    verifier_sessions: list[tuple[int, str | None]] = []

    def produce(request):
        producer_sessions.append((request.attempt, request.session.session_id if request.session is not None else None))
        assert request.session is not None
        return ProducerResponse(
            raw_output=f"draft-{request.attempt}",
            session=SessionBinding(key=request.session.key, session_id=f"producer-{request.attempt}"),
        )

    def verify(request):
        verifier_sessions.append((request.attempt, request.session.session_id if request.session is not None else None))
        assert request.session is not None
        return OutcomeResponse(
            outcome=Outcome(
                raw_output=f"verify-{request.attempt}",
                tag="done",
                payload={
                    "write_report": request.attempt == 2,
                    "session_id": f"verifier-{request.attempt}",
                },
            ),
            session=SessionBinding(key=request.session.key, session_id=f"verifier-{request.attempt}"),
        )

    result = Engine(
        PairSessionRetryWorkflow,
        provider=ScriptedLLMProvider(producer_turns=[produce, produce], verifier_turns=[verify, verify]),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(producer_sessions) == 2
    assert len(verifier_sessions) == 2
    assert producer_sessions[0][1] is not None
    assert producer_sessions[1][1] == producer_sessions[0][1]
    assert verifier_sessions == [
        (1, "producer-1"),
        (2, "producer-2"),
    ]
    final_binding = session_store.get("main")
    assert final_binding is not None
    assert final_binding.session_id == "verifier-2"


def test_declared_extensions_bind_once_per_run_in_tuple_order(tmp_path: Path):
    events: list[tuple[object, ...]] = []
    first = _RecordingExtension("first", events)
    second = _RecordingExtension("second", events)

    def _extensionworkflow_on_ask(ctx):
        return None

    def _extensionworkflow_on_finish(ctx):
        ctx.state = ctx.state.model_copy(update={'done': True})
        return Event('complete')

    class ExtensionWorkflow(Workflow):
        class State(BaseModel):
            done: bool = False

        extensions = (first, second)
        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        finish = PythonStep(name="finish", handler=_extensionworkflow_on_finish)
        entry = ask
        transitions = {ask: {"done": finish}, finish: {"complete": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        ExtensionWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(first.bindings) == 1
    assert len(second.bindings) == 1
    assert first.bindings[0] == second.bindings[0]
    assert first.bindings[0].root == tmp_path
    assert first.bindings[0].workflow_name == "extension_workflow"
    assert [(name, phase, step) for name, phase, step, *_ in events] == [
        ("first", "before", "ask"),
        ("second", "before", "ask"),
        ("first", "after", "ask"),
        ("second", "after", "ask"),
        ("first", "before", "finish"),
        ("second", "before", "finish"),
        ("first", "after", "finish"),
        ("second", "after", "finish"),
        ("first", "terminal", FINISH),
        ("second", "terminal", FINISH),
    ]


def test_extensions_receive_isolated_snapshots_and_cannot_mutate_execution_state(tmp_path: Path):
    class MutatingExtension:
        def bind(self, binding: RunBinding):
            class Bound:
                def before_step(self, event: StepStart) -> None:
                    event.state.seen = "before"

                def after_step(self, event: StepFinish) -> None:
                    event.state_before.seen = "mutated-before"
                    event.state_after.seen = "mutated-after"
                    if event.outcome is not None:
                        event.outcome.payload["tag_seen"] = "mutated"

                def on_terminal(self, event: TerminalFinish) -> None:
                    if event.state is not None:
                        event.state.seen = "terminal"

            return Bound()

    def _isolationworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': ctx.outcome.payload['tag_seen']})
        return None

    class IsolationWorkflow(Workflow):
        class State(BaseModel):
            seen: str = ""

        extensions = (MutatingExtension(),)
        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    IsolationWorkflow.ask.after = _chain_hooks(_isolationworkflow_on_ask, IsolationWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        IsolationWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[Outcome(raw_output="ok", tag="done", payload={"tag_seen": "done"})]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.seen == "done"


def test_malformed_bound_extension_fails_before_any_step_executes(tmp_path: Path):
    class BrokenExtension:
        def bind(self, binding: RunBinding):
            class Bound:
                def before_step(self, event: StepStart) -> None:
                    return None

                def after_step(self, event: StepFinish) -> None:
                    return None

            return Bound()

    def _brokenworkflow_on_ask(ctx):
        return None

    class BrokenWorkflow(Workflow):
        class State(BaseModel):
            pass

        extensions = (BrokenExtension(),)
        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        BrokenWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match=r"without callable on_terminal\(\)"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    assert provider.calls == []
    assert checkpoint_store.load() is None


def test_system_step_contract_bypasses_middleware(tmp_path: Path):
    def _systemworkflow_on_begin(ctx):
        ctx.state = ctx.state.model_copy(update={'completed': True})
        return Event('done')

    def _systemworkflow_on_outcome(ctx):
        raise AssertionError('middleware must not run for system steps')

    class SystemWorkflow(Workflow):
        class State(BaseModel):
            completed: bool = False

        begin = PythonStep(name="begin", handler=_systemworkflow_on_begin)
        entry = begin
        transitions = {begin: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    engine = Engine(
        SystemWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.completed is True
    snapshot = session_store.snapshot()
    assert "default" not in snapshot.active_keys_by_slot
    assert snapshot.bindings == ()


def test_on_start_opens_sessions_before_execution(tmp_path: Path):
    def _startsessionworkflow_on_start(ctx):
        ctx.open_session(StartSessionWorkflow.main)
        ctx.open_session(StartSessionWorkflow.auxiliary_slot)

    def _startsessionworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'session_id': ctx.outcome.payload['session_id']})
        return None

    class StartSessionWorkflow(Workflow):
        class State(BaseModel):
            session_id: str = ""

        main = Session()
        auxiliary_slot = Session()
        ask = PromptStep(name="ask", producer="ask.md", session=main)
        entry = ask
        transitions = {ask: {"done": FINISH}}


    StartSessionWorkflow.ask.before = _chain_hooks(_startsessionworkflow_on_start, StartSessionWorkflow.ask.before)
    StartSessionWorkflow.ask.after = _chain_hooks(_startsessionworkflow_on_ask, StartSessionWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    engine = Engine(
        StartSessionWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: Outcome(
                    raw_output="ok",
                    tag="done",
                    payload={"session_id": request.session.session_id},
                )
            ]
        ),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    snapshot = session_store.snapshot()
    assert result.state.session_id.startswith("main:global:")
    assert snapshot.active_scopes == {"main": None, "auxiliary_slot": None}


def test_declared_session_auto_opens_without_on_start(tmp_path: Path):
    def _autoopensessionworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': ctx.outcome.payload['session_id']})
        return None

    class AutoOpenSessionWorkflow(Workflow):
        class State(BaseModel):
            seen: str = ""

        main = Session(continuity=Continuity.task())
        ask = PromptStep(name="ask", producer="ask.md", session=main)
        entry = ask
        transitions = {ask: {"done": FINISH}}

    AutoOpenSessionWorkflow.ask.after = _chain_hooks(_autoopensessionworkflow_on_ask, AutoOpenSessionWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    engine = Engine(
        AutoOpenSessionWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: Outcome(
                    raw_output="ok",
                    tag="done",
                    payload={"session_id": request.session.session_id},
                )
            ]
        ),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    checkpoint = session_store.snapshot()
    assert result.state.seen.startswith("main:task-1:")
    assert checkpoint.active_keys_by_slot["main"].domain == "task"


def test_provider_steps_without_explicit_session_use_default_session(tmp_path: Path):
    def _defaultsessionworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'llm_session': ctx.outcome.payload['session_id']})
        return None

    def _defaultsessionworkflow_on_review(ctx):
        ctx.state = ctx.state.model_copy(update={'pair_session': ctx.outcome.payload['session_id']})
        return None

    class DefaultSessionWorkflow(Workflow):
        class State(BaseModel):
            llm_session: str = ""
            pair_session: str = ""

        ask = PromptStep(name="ask", producer="ask.md")
        review = ProduceVerifyStep(name="review", producer="review.md", verifier="verify.md")
        entry = ask
        transitions = {
            ask: {"next": review},
            review: {"done": FINISH},
        }


    DefaultSessionWorkflow.ask.after = _chain_hooks(_defaultsessionworkflow_on_ask, DefaultSessionWorkflow.ask.after)
    DefaultSessionWorkflow.review.after_verifier = _chain_hooks(_defaultsessionworkflow_on_review, DefaultSessionWorkflow.review.after_verifier)


    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    engine = Engine(
        DefaultSessionWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: Outcome(
                    raw_output="ask",
                    tag="next",
                    payload={"session_id": request.session.session_id},
                )
            ],
            producer_turns=[lambda request: "draft"],
            verifier_turns=[
                lambda request: Outcome(
                    raw_output="verify",
                    tag="done",
                    payload={"session_id": request.session.session_id},
                )
            ],
        ),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    snapshot = session_store.snapshot()
    assert result.state.llm_session.startswith("global:global:")
    assert result.state.pair_session == result.state.llm_session
    assert snapshot.active_keys_by_slot["global"].domain == "run"


def test_middleware_pause_skips_handler_and_resume_injects_answer_once(tmp_path: Path):
    def _pauseworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'handler_calls': ctx.state.handler_calls + 1, 'answer_seen': ctx.outcome.payload.get('answer')})
        return None

    def _pauseworkflow_on_finish(ctx):
        ctx.state = ctx.state.model_copy(update={'answer_visible_in_system': ctx.answer})
        return Event('done')

    def _pauseworkflow_on_outcome(ctx):
        if ctx.outcome.tag == 'question':
            return Event('question', reason=ctx.outcome.reason, question=ctx.outcome.question)
        return None

    class PauseWorkflow(Workflow):
        class State(BaseModel):
            handler_calls: int = 0
            answer_seen: str | None = None
            answer_visible_in_system: str | None = None

        ask = PromptStep(name="ask", producer="ask.md")
        finish = PythonStep(name="finish", handler=_pauseworkflow_on_finish)
        entry = ask
        transitions = {ask: {"answered": finish, "question": "AWAIT_INPUT"}, finish: {"done": FINISH}}
    PauseWorkflow.ask.after = _chain_hooks(_pauseworkflow_on_outcome, _pauseworkflow_on_ask, PauseWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        PauseWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: Outcome(
                    raw_output="Need answer",
                    tag="answered" if request.context.answer else "question",
                    question=None if request.context.answer else "What value?",
                    payload={"answer": request.context.answer} if request.context.answer else {},
                ),
                lambda request: Outcome(
                    raw_output="Need answer",
                    tag="answered" if request.context.answer else "question",
                    question=None if request.context.answer else "What value?",
                    payload={"answer": request.context.answer} if request.context.answer else {},
                ),
            ]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    paused = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == "AWAIT_INPUT"
    assert paused.state.handler_calls == 0
    assert paused.checkpoint.pending_input is not None
    assert paused.checkpoint.pending_input.question == "What value?"

    resumed = engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer="42",
    )

    assert resumed.terminal == FINISH
    assert resumed.state.handler_calls == 1
    assert resumed.state.answer_seen == "42"
    assert resumed.state.answer_visible_in_system is None
    assert checkpoint_store.load() is None


def test_resume_reuses_legacy_global_session_binding(tmp_path: Path):
    def _resumeworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': ctx.outcome.payload['session_id']})
        return None

    class ResumeWorkflow(Workflow):
        class State(BaseModel):
            seen: str = ""

        main = Session()
        ask = PromptStep(name="ask", producer="ask.md", session=main)
        entry = ask
        transitions = {ask: {"done": FINISH}}

    ResumeWorkflow.ask.after = _chain_hooks(_resumeworkflow_on_ask, ResumeWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    checkpoint_store = InMemoryCheckpointStore()
    checkpoint_store.save(
        Checkpoint(
            stage="ask",
            state=ResumeWorkflow.State(),
            session_bindings=SessionSnapshot(
                bindings=(SessionBinding(ref_name="main", scope=None, session_id="legacy-main:global:7"),),
                active_scopes={"main": None},
            ),
        )
    )
    engine = Engine(
        ResumeWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: Outcome(
                    raw_output="ok",
                    tag="done",
                    payload={"session_id": request.session.session_id},
                )
            ]
        ),
        session_store=session_store,
        checkpoint_store=checkpoint_store,
    )

    resumed = engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert resumed.terminal == FINISH
    assert resumed.state.seen == "legacy-main:global:7"
    snapshot = session_store.snapshot()
    assert snapshot.active_keys_by_slot["main"] == SessionKey("main", "run", "run-1")
    assert snapshot.bindings[0].key == SessionKey("main", "run", "run-1")


def test_handler_exception_saves_failure_checkpoint(tmp_path: Path):
    def _explodingworkflow_on_ask(ctx):
        raise RuntimeError('boom')

    class ExplodingWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    ExplodingWorkflow.ask.after = _chain_hooks(_explodingworkflow_on_ask, ExplodingWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        ExplodingWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="boom"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"


def test_extension_failure_semantics_checkpoint_latest_state_and_surface_terminal(tmp_path: Path):
    terminals: list[TerminalFinish] = []

    class FailingExtension:
        def bind(self, binding: RunBinding):
            class Bound:
                def before_step(self, event: StepStart) -> None:
                    return None

                def after_step(self, event: StepFinish) -> None:
                    raise RuntimeError("extension boom")

                def on_terminal(self, event: TerminalFinish) -> None:
                    terminals.append(event)

            return Bound()

    def _extensionfailureworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'calls': ctx.state.calls + 1})
        return None

    class ExtensionFailureWorkflow(Workflow):
        class State(BaseModel):
            calls: int = 0

        extensions = (FailingExtension(),)
        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    ExtensionFailureWorkflow.ask.after = _chain_hooks(_extensionfailureworkflow_on_ask, ExtensionFailureWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        ExtensionFailureWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(RuntimeError, match="extension boom"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert checkpoint.state.calls == 1
    assert len(terminals) == 1
    assert terminals[0].terminal == "fatal"
    assert terminals[0].step_name == "ask"
    assert terminals[0].state is not None
    assert terminals[0].state.calls == 1


def test_terminal_extensions_receive_pause_fail_and_fatal_events(tmp_path: Path):
    seen: list[tuple[str, str | None, str]] = []

    class TerminalExtension:
        def bind(self, binding: RunBinding):
            class Bound:
                def before_step(self, event: StepStart) -> None:
                    return None

                def after_step(self, event: StepFinish) -> None:
                    return None

                def on_terminal(self, event: TerminalFinish) -> None:
                    seen.append((event.terminal, event.step_name, event.binding.run_id))

            return Bound()

    def _pauseworkflow_on_outcome(ctx):
        return Event('question', question=ctx.outcome.question)

    class PauseWorkflow(Workflow):
        class State(BaseModel):
            pass

        extensions = (TerminalExtension(),)
        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"question": "AWAIT_INPUT"}}

    PauseWorkflow.ask.after = _chain_hooks(_pauseworkflow_on_outcome, PauseWorkflow.ask.after)


    class FailWorkflow(Workflow):
        class State(BaseModel):
            pass

        extensions = (TerminalExtension(),)
        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"failed": "FAIL"}}

    def _fatalworkflow_on_ask(ctx):
        raise RuntimeError('boom')

    class FatalWorkflow(Workflow):
        class State(BaseModel):
            pass

        extensions = (TerminalExtension(),)
        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    FatalWorkflow.ask.after = _chain_hooks(_fatalworkflow_on_ask, FatalWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)

    paused = Engine(
        PauseWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="Need answer", tag="question", question="What value?")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(task_id="task-1", run_id="run-1", task_folder=task_folder, run_folder=run_folder, root=tmp_path)

    failed = Engine(
        FailWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="bad", tag="failed", reason="The step failed.")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(task_id="task-2", run_id="run-2", task_folder=task_folder, run_folder=run_folder, root=tmp_path)

    fatal_checkpoint_store = InMemoryCheckpointStore()
    fatal_engine = Engine(
        FatalWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=fatal_checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="boom"):
        fatal_engine.run(task_id="task-3", run_id="run-3", task_folder=task_folder, run_folder=run_folder, root=tmp_path)

    assert paused.terminal == "AWAIT_INPUT"
    assert failed.terminal == "FAIL"
    assert fatal_checkpoint_store.load() is not None
    assert seen == [
        ("AWAIT_INPUT", "ask", "run-1"),
        ("FAIL", "ask", "run-2"),
        ("fatal", "ask", "run-3"),
    ]


def test_missing_required_artifact_raises_and_checkpoints(tmp_path: Path):
    def _missinginputworkflow_on_ask(ctx):
        return None

    class MissingInputWorkflow(Workflow):
        class State(BaseModel):
            pass

        request = Artifact("{task_folder}/request.txt")
        ask = PromptStep(name="ask", producer="ask.md", requires=[request])
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        MissingInputWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(MissingArtifactError):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"


def test_missing_required_produced_artifact_raises_provider_error_and_checkpoints_context(tmp_path: Path):
    def _requiredproducedworkflow_on_ask(ctx):
        return None

    class RequiredProducedWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"summary": Artifact.md("summary.md", required=True)},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        RequiredProducedWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match=r"artifact validation failed.*route 'done'.*summary"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "missing_required_output_artifact"
    assert checkpoint.failure_context["step_name"] == "ask"
    assert checkpoint.failure_context["candidate_route"] == "done"
    assert checkpoint.failure_context["final_route"] == "done"
    assert checkpoint.failure_context["provider_attributable"] is True
    assert checkpoint.failure_context["artifact_name"] == "summary"
    assert checkpoint.failure_context["qualified_name"] == "ask.summary"
    assert checkpoint.failure_context["path"] == str(task_folder / "wf_required_produced_workflow" / "ask" / "summary.md")
    assert checkpoint.failure_context["errors"] == ["artifact file does not exist"]
    assert "artifact validation failed for step 'ask' route 'done'" in checkpoint.failure_context["error"]
    assert checkpoint.failure_context["details"]["retry_attempts_consumed"] == 1
    assert checkpoint.failure_context["details"]["retry_max_attempts"] == 1
    assert checkpoint.failure_context["details"]["retry_exhausted"] is True
    assert len(engine.provider.calls) == 1


def test_invalid_middleware_route_still_fails_before_artifact_validation(tmp_path: Path):
    def _invalidmiddlewarerouteworkflow_on_outcome(ctx):
        return Event('bogus')

    class InvalidMiddlewareRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"summary": Artifact.md("summary.md", required=True)},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}


    InvalidMiddlewareRouteWorkflow.ask.after = _invalidmiddlewarerouteworkflow_on_outcome


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        InvalidMiddlewareRouteWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="produced illegal route 'bogus'"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "hook_failure"
    assert checkpoint.failure_context["candidate_route"] == "done"
    assert checkpoint.failure_context["provider_attributable"] is False
    assert checkpoint.failure_context["source_hook"] == "_invalidmiddlewarerouteworkflow_on_outcome"
    assert checkpoint.failure_context["source_phase"] == "after"
    assert len(engine.provider.calls) == 1


def test_invalid_system_route_still_fails_before_artifact_validation(tmp_path: Path):
    def _invalidsystemrouteworkflow_on_publish(ctx):
        return Event('bogus')

    class InvalidSystemRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        publish = PythonStep(
            name="publish",
            writes={"summary": Artifact.md("summary.md", required=True)},
            handler=_invalidsystemrouteworkflow_on_publish,
        )
        entry = publish
        transitions = {publish: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        InvalidSystemRouteWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="produced illegal route 'bogus'"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "publish"
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "route_validation"
    assert checkpoint.failure_context["candidate_route"] == "bogus"
    assert engine.provider.calls == []


def test_python_step_tuple_state_event_return_is_rejected(tmp_path: Path):
    def _invalidtuplepythonstepworkflow_on_publish(ctx):
        return (ctx.state, Event('done'))

    class InvalidTuplePythonStepWorkflow(Workflow):
        class State(BaseModel):
            pass

        publish = PythonStep(name="publish", handler=_invalidtuplepythonstepworkflow_on_publish)
        entry = publish
        transitions = {publish: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        InvalidTuplePythonStepWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(WorkflowExecutionError, match=r"python_step hook for step 'publish' returned unsupported value"):
        engine.run(
            task_id="task-tuple-return",
            run_id="run-tuple-return",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_python_step_basemodel_return_is_rejected(tmp_path: Path):
    def _invalidstatereturnworkflow_on_publish(ctx):
        return ctx.state.model_copy(update={'done': True})

    class InvalidStateReturnWorkflow(Workflow):
        class State(BaseModel):
            done: bool = False

        publish = PythonStep(name="publish", handler=_invalidstatereturnworkflow_on_publish)
        entry = publish
        transitions = {publish: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        InvalidStateReturnWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(WorkflowExecutionError, match=r"python_step hook for step 'publish' returned unsupported value"):
        engine.run(
            task_id="task-state-return",
            run_id="run-state-return",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_retry_budget_exhaustion_checkpoints_failure_context_and_attempt_count(tmp_path: Path):
    def _exhaustedretryworkflow_on_ask(ctx):
        return None

    class ExhaustedRetryWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"summary": Artifact.md("summary.md", required=True)},
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="one", tag="done"),
            Outcome(raw_output="two", tag="done"),
            Outcome(raw_output="three", tag="done"),
        ]
    )
    engine = Engine(
        ExhaustedRetryWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match=r"artifact validation failed.*summary"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "missing_required_output_artifact"
    assert checkpoint.failure_context["artifact_name"] == "summary"
    assert checkpoint.failure_context["retry_attempts_consumed"] == 3
    assert checkpoint.failure_context["retry_max_attempts"] == 3
    assert checkpoint.failure_context["retry_exhausted"] is True
    assert len(provider.calls) == 3


def test_engine_emits_provider_attempt_events_with_step_execution_identity(tmp_path: Path):
    def _attempteventworkflow_on_ask(ctx):
        return None

    class AttemptEventWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    runtime_events: list[tuple[str, dict[str, object]]] = []
    result = Engine(
        AttemptEventWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-attempt-events",
        run_id="run-attempt-events",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert runtime_events[:3] == [
        (
            "provider_policy_resolved",
            {
                "policy_fingerprint": runtime_events[0][1]["policy_fingerprint"],
                "step_name": "ask",
                "visit": 1,
                "step_execution_id": "ask:1",
            },
        ),
        (
            "provider_attempt_started",
            {
                "step_name": "ask",
                "visit": 1,
                "step_execution_id": "ask:1",
                "turn_kind": "llm",
                "attempt": 1,
            },
        ),
        (
            "provider_attempt_finished",
            {
                "step_name": "ask",
                "visit": 1,
                "step_execution_id": "ask:1",
                "turn_kind": "llm",
                "attempt": 1,
            },
        ),
    ]


def test_engine_emits_artifact_validation_failure_events(tmp_path: Path):
    def _missingartifactworkflow_on_ask(ctx):
        return None

    class MissingArtifactWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"summary": Artifact.md("summary.md", required=True)},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    runtime_events: list[tuple[str, dict[str, object]]] = []
    engine = Engine(
        MissingArtifactWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    )

    with pytest.raises(ProviderExecutionError, match=r"artifact validation failed.*summary"):
        engine.run(
            task_id="task-artifact-events",
            run_id="run-artifact-events",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    artifact_events = [payload for event_type, payload in runtime_events if event_type == "artifact_validation_failed"]
    assert artifact_events == [
        {
            "step_name": "ask",
            "visit": 1,
            "step_execution_id": "ask:1",
            "route": "done",
            "artifact_name": "summary",
            "qualified_name": "ask.summary",
            "path": str(task_folder / "wf_missing_artifact_workflow" / "ask" / "summary.md"),
            "validation_kind": "missing_required_artifact",
            "errors": ["artifact file does not exist"],
            "provider_attributable": True,
        }
    ]


def test_required_json_artifact_written_by_handler_validates_after_handler(tmp_path: Path):
    class SummaryPayload(BaseModel):
        summary: str

    def _handlerartifactworkflow_on_ask(ctx):
        ctx.artifacts.summary.write_json({'summary': ctx.outcome.payload['summary']})
        ctx.state = ctx.state.model_copy(update={'summary': ctx.outcome.payload['summary']})
        return None

    class HandlerArtifactWorkflow(Workflow):
        class State(BaseModel):
            summary: str = ""

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"summary": Artifact.json("summary.json", schema=SummaryPayload, required=True)},
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    HandlerArtifactWorkflow.ask.after = _chain_hooks(_handlerartifactworkflow_on_ask, HandlerArtifactWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        HandlerArtifactWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[Outcome(raw_output="ok", tag="done", payload={"summary": "ready"})]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.summary == "ready"
    assert (
        task_folder / "wf_handler_artifact_workflow" / "ask" / "summary.json"
    ).read_text(encoding="utf-8").strip() == '{\n  "summary": "ready"\n}'


def test_optional_json_artifact_absent_is_allowed(tmp_path: Path):
    class SummaryPayload(BaseModel):
        summary: str

    def _optionalartifactworkflow_on_ask(ctx):
        return None

    class OptionalArtifactWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"summary": Artifact.json("summary.json", schema=SummaryPayload)},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        OptionalArtifactWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH


def test_optional_present_schema_artifact_must_validate(tmp_path: Path):
    class SummaryPayload(BaseModel):
        summary: str

    def _invalidoptionalartifactworkflow_on_ask(ctx):
        ctx.artifacts.summary.write_json({'wrong': 'value'})
        return None

    class InvalidOptionalArtifactWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"summary": Artifact.json("summary.json", schema=SummaryPayload)},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    InvalidOptionalArtifactWorkflow.ask.after = _chain_hooks(_invalidoptionalartifactworkflow_on_ask, InvalidOptionalArtifactWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        InvalidOptionalArtifactWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match=r"artifact validation failed.*summary"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["artifact_name"] == "summary"
    assert checkpoint.failure_context["route"] == "done"
    assert checkpoint.failure_context["kind"] == "invalid_output_artifact"
    assert checkpoint.failure_context["retry_attempts_consumed"] == 1
    assert checkpoint.failure_context["retry_max_attempts"] == 1
    assert checkpoint.failure_context["retry_exhausted"] is True
    assert len(engine.provider.calls) == 1


def test_route_specific_required_artifacts_override_required_defaults(tmp_path: Path):
    def _routeoverrideworkflow_on_ask(ctx):
        ctx.artifacts.report.write_text('ready')
        return None

    class RouteOverrideWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={
                "summary": Artifact.md("summary.md", required=True),
                "report": Artifact.md("report.md"),
            },
            route_metadata={
                "done": Route(summary="only the report is required for this route", required_writes=("report",))
            },
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    RouteOverrideWorkflow.ask.after = _chain_hooks(_routeoverrideworkflow_on_ask, RouteOverrideWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        RouteOverrideWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert (task_folder / "wf_route_override_workflow" / "ask" / "summary.md").exists() is False


def test_system_step_route_specific_required_artifacts_raise_workflow_error(tmp_path: Path):
    def _systemrouteworkflow_on_publish(ctx):
        return Event('done')

    class SystemRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        publish = PythonStep(
            name="publish",
            writes={
                "summary": Artifact.md("summary.md", required=True),
                "report": Artifact.md("report.md"),
            },
            route_metadata={"done": Route(summary="publish completed", required_writes=("report",))},
            handler=_systemrouteworkflow_on_publish,
        )
        entry = publish
        transitions = {publish: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        SystemRouteWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match=r"artifact validation failed.*report"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["artifact_name"] == "report"
    assert checkpoint.failure_context["qualified_name"] == "publish.report"


def test_phase_scoped_sessions_follow_active_scope_switches(tmp_path: Path):
    def _scopedworkflow_on_activate_a(ctx):
        ctx.open_session('phase_session', scope='phase-a')
        return Event('phase-a')

    def _scopedworkflow_on_use_a(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, ctx.outcome.payload['session_id']]})
        return None

    def _scopedworkflow_on_activate_b(ctx):
        ctx.open_session('phase_session', scope='phase-b')
        return Event('phase-b')

    def _scopedworkflow_on_use_b(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, ctx.outcome.payload['session_id']]})
        return None

    def _scopedworkflow_on_finish(ctx):
        return Event('end')

    class ScopedWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        phase_session = Session()
        activate_a = PythonStep(name="activate_a", handler=_scopedworkflow_on_activate_a)
        use_a = PromptStep(name="use_a", producer="use.md", session=phase_session)
        activate_b = PythonStep(name="activate_b", handler=_scopedworkflow_on_activate_b)
        use_b = PromptStep(name="use_b", producer="use.md", session=phase_session)
        finish = PythonStep(name="finish", handler=_scopedworkflow_on_finish)
        entry = activate_a
        transitions = {
            activate_a: {"phase-a": use_a},
            use_a: {"next": activate_b},
            activate_b: {"phase-b": use_b},
            use_b: {"done": finish},
            finish: {"end": FINISH},
        }
    ScopedWorkflow.use_a.after = _chain_hooks(_scopedworkflow_on_use_a, ScopedWorkflow.use_a.after)
    ScopedWorkflow.use_b.after = _chain_hooks(_scopedworkflow_on_use_b, ScopedWorkflow.use_b.after)


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        ScopedWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: Outcome(
                    raw_output="a",
                    tag="next",
                    payload={"session_id": request.session.session_id},
                ),
                lambda request: Outcome(
                    raw_output="b",
                    tag="done",
                    payload={"session_id": request.session.session_id},
                ),
            ]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(result.state.seen) == 2
    assert result.state.seen[0].startswith("phase_session:phase-a:")
    assert result.state.seen[1].startswith("phase_session:phase-b:")
    assert result.state.seen[0] != result.state.seen[1]


def test_route_handoff_combines_static_and_dynamic_messages_for_target_provider_step(tmp_path: Path):
    def _handoffworkflow_on_start(ctx):
        return Event('review', handoff='Dynamic handoff.')

    def _handoffworkflow_on_review(ctx):
        ctx.state = ctx.state.model_copy(update={'done': True})
        return None

    def _handoffworkflow_on_finish(ctx):
        return Event('complete')

    class HandoffWorkflow(Workflow):
        class State(BaseModel):
            done: bool = False

        start = PythonStep(name="start", handler=_handoffworkflow_on_start)
        review = PromptStep(name="review", producer="review.md")
        finish = PythonStep(name="finish", handler=_handoffworkflow_on_finish)
        entry = start
        transitions = {
            start: {"review": Route.to(review, handoff="Static handoff.")},
            review: {"done": finish},
            finish: {"complete": FINISH},
        }
    HandoffWorkflow.review.after = _chain_hooks(_handoffworkflow_on_review, HandoffWorkflow.review.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    engine = Engine(
        HandoffWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert provider.calls[0].route_handoff == "Static handoff.\n\nDynamic handoff."


def test_route_handoff_is_consumed_after_first_dispatch(tmp_path: Path):
    def _consumeonceworkflow_on_start(ctx):
        return Event('ask')

    def _consumeonceworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'passes': ctx.state.passes + 1})
        return None

    def _consumeonceworkflow_on_finish(ctx):
        return Event('complete')

    class ConsumeOnceWorkflow(Workflow):
        class State(BaseModel):
            passes: int = 0

        start = PythonStep(name="start", handler=_consumeonceworkflow_on_start)
        ask = PromptStep(name="ask", producer="ask.md")
        finish = PythonStep(name="finish", handler=_consumeonceworkflow_on_finish)
        entry = start
        transitions = {
            start: {"ask": Route.to(ask, handoff="Use this handoff once.")},
            ask: {"redo": ask, "done": finish},
            finish: {"complete": FINISH},
        }
    ConsumeOnceWorkflow.ask.after = _chain_hooks(_consumeonceworkflow_on_ask, ConsumeOnceWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="first", tag="redo"),
            Outcome(raw_output="second", tag="done"),
        ]
    )
    engine = Engine(
        ConsumeOnceWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert [call.route_handoff for call in provider.calls] == ["Use this handoff once.", None]


def test_route_handoff_is_scoped_to_the_active_worklist_item(tmp_path: Path):
    def _scopedhandoffworkflow_on_outcome(ctx):
        if ctx.outcome.tag == 'review':
            item_id = str(ctx.outcome.payload['item_id'])
            return Event('review', handoff=f'handoff:{item_id}')
        return None

    def _scopedhandoffworkflow_on_draft(ctx):
        return None

    def _scopedhandoffworkflow_on_review(ctx):
        item_id = str(ctx.outcome.payload['item_id'])
        ctx.state = ctx.state.model_copy(update={'reviewed': [*ctx.state.reviewed, item_id]})
        return None

    def _scopedhandoffworkflow_on_advance(ctx):
        ctx.worklists.gate.advance()
        return Event('draft')

    def _scopedhandoffworkflow_on_finish(ctx):
        return Event('complete')

    class ScopedHandoffWorkflow(Workflow):
        class State(BaseModel):
            reviewed: list[str] = Field(default_factory=list)

        gates = Worklist.from_items(
            name="gate",
            items=(
                {"id": "alpha", "title": "Alpha"},
                {"id": "beta", "title": "Beta"},
            ),
        )
        draft = PromptStep(name="draft", producer="draft.md", scope=gates)
        review = PromptStep(name="review", producer="review.md", scope=gates)
        advance = PythonStep(name="advance", handler=_scopedhandoffworkflow_on_advance)
        finish = PythonStep(name="finish", handler=_scopedhandoffworkflow_on_finish)
        entry = draft
        transitions = {
            draft: {"review": review},
            review: {"next": advance, "done": finish},
            advance: {"draft": draft},
            finish: {"complete": FINISH},
        }
    ScopedHandoffWorkflow.draft.after = _chain_hooks(_scopedhandoffworkflow_on_outcome, _scopedhandoffworkflow_on_draft, ScopedHandoffWorkflow.draft.after)
    ScopedHandoffWorkflow.review.after = _chain_hooks(_scopedhandoffworkflow_on_outcome, _scopedhandoffworkflow_on_review, ScopedHandoffWorkflow.review.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: Outcome(raw_output="draft alpha", tag="review", payload={"item_id": request.context.item.id}),
            lambda request: Outcome(raw_output="review alpha", tag="next", payload={"item_id": request.context.item.id}),
            lambda request: Outcome(raw_output="draft beta", tag="review", payload={"item_id": request.context.item.id}),
            lambda request: Outcome(raw_output="review beta", tag="done", payload={"item_id": request.context.item.id}),
        ]
    )
    engine = Engine(
        ScopedHandoffWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    review_calls = [call for call in provider.calls if call.step_name == "review"]

    assert result.terminal == FINISH
    assert [call.route_handoff for call in review_calls] == ["handoff:alpha", "handoff:beta"]


def test_route_handoff_survives_checkpoint_resume_before_dispatch_consumes_it(tmp_path: Path):
    def _resumehandoffworkflow_on_start(ctx):
        return Event('review')

    def _resumehandoffworkflow_on_review(ctx):
        ctx.state = ctx.state.model_copy(update={'done': True})
        return None

    def _resumehandoffworkflow_on_finish(ctx):
        return Event('complete')

    class ResumeHandoffWorkflow(Workflow):
        class State(BaseModel):
            done: bool = False

        start = PythonStep(name="start", handler=_resumehandoffworkflow_on_start)
        review = PromptStep(
            name="review",
            producer="review.md",
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        finish = PythonStep(name="finish", handler=_resumehandoffworkflow_on_finish)
        entry = start
        transitions = {
            start: {"review": Route.to(review, handoff="Resume this handoff.")},
            review: {"done": finish},
            finish: {"complete": FINISH},
        }
    ResumeHandoffWorkflow.review.after = _chain_hooks(_resumehandoffworkflow_on_review, ResumeHandoffWorkflow.review.after)


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    failing_engine = Engine(
        ResumeHandoffWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[lambda request: (_ for _ in ()).throw(RuntimeError("transport crashed"))]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="transport crashed"):
        failing_engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.pending_handoffs

    resumed_provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    resumed_engine = Engine(
        ResumeHandoffWorkflow,
        provider=resumed_provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    result = resumed_engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert resumed_provider.calls[0].route_handoff == "Resume this handoff."


def test_route_handoff_targeting_system_step_is_dropped_before_later_provider_step(tmp_path: Path):
    def _systemtargethandoffworkflow_on_outcome(ctx):
        if ctx.outcome.tag == 'bridge':
            return Event('bridge', handoff='Drop this at the system step.')
        return None

    def _systemtargethandoffworkflow_on_ask(ctx):
        return None

    def _systemtargethandoffworkflow_on_bridge(ctx):
        return Event('review')

    def _systemtargethandoffworkflow_on_review(ctx):
        ctx.state = ctx.state.model_copy(update={'reviewed': True})
        return None

    def _systemtargethandoffworkflow_on_finish(ctx):
        return Event('complete')

    class SystemTargetHandoffWorkflow(Workflow):
        class State(BaseModel):
            reviewed: bool = False

        ask = PromptStep(name="ask", producer="ask.md")
        bridge = PythonStep(name="bridge", handler=_systemtargethandoffworkflow_on_bridge)
        review = PromptStep(name="review", producer="review.md")
        finish = PythonStep(name="finish", handler=_systemtargethandoffworkflow_on_finish)
        entry = ask
        transitions = {
            ask: {"bridge": bridge},
            bridge: {"review": review},
            review: {"done": finish},
            finish: {"complete": FINISH},
        }
    SystemTargetHandoffWorkflow.ask.after = _chain_hooks(_systemtargethandoffworkflow_on_outcome, _systemtargethandoffworkflow_on_ask, SystemTargetHandoffWorkflow.ask.after)
    SystemTargetHandoffWorkflow.review.after = _chain_hooks(_systemtargethandoffworkflow_on_outcome, _systemtargethandoffworkflow_on_review, SystemTargetHandoffWorkflow.review.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="route to bridge", tag="bridge"),
            Outcome(raw_output="reviewed", tag="done"),
        ]
    )
    engine = Engine(
        SystemTargetHandoffWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.reviewed is True
    assert [call.route_handoff for call in provider.calls] == [None, None]


def test_route_handoff_targeting_workflow_step_is_dropped_before_later_provider_step(tmp_path: Path):
    def after_ask(ctx):
        if ctx.outcome.tag == "launch":
            return Event("launch", handoff="Drop this at the workflow step.")
        return None

    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    class WorkflowTargetHandoffWorkflow(SimpleWorkflow):
        ask = step(
            prompt="Ask for child execution.",
            routes={"launch": "launch"},
            after=after_ask,
        )
        launch = workflow_step(ChildWorkflow, message="Run child workflow")
        review = step("Review the child result.")

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    child_runs: list[str] = []

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_runs.append(message)
        child_run_root = task_folder / "child-runs" / "child-1"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id="child-1",
            terminal=FINISH,
            status="success",
            last_event=Event("done"),
            output_metadata={},
            output_artifacts={},
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_root / "run",
            package_folder=child_run_root / "package",
            request_file=child_run_root / "request.md",
            run_meta_file=child_run_root / "run.json",
            events_file=child_run_root / "events.jsonl",
            checkpoint_file=child_run_root / "checkpoint.json",
            sessions_dir=child_run_root / "sessions",
            trace_file=child_run_root / "trace.jsonl",
            raw_dir=child_run_root / "raw",
            parent_file=child_run_root / "parent.json",
        )

    engine = Engine(
        WorkflowTargetHandoffWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                Outcome(raw_output="launch child", tag="launch"),
                lambda request: (_ for _ in ()).throw(RuntimeError("transport crashed")),
            ]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="transport crashed"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            workflow_invoker=invoke_child,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.pending_handoffs == ()
    assert child_runs == ["Run child workflow"]


def test_route_handoff_targeting_terminal_is_not_persisted_in_pause_checkpoint(tmp_path: Path):
    def _terminaltargethandoffworkflow_on_outcome(ctx):
        return Event('pause', handoff='Drop this at pause.')

    def _terminaltargethandoffworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'paused': True})
        return None

    class TerminalTargetHandoffWorkflow(Workflow):
        class State(BaseModel):
            paused: bool = False

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"pause": AWAIT_INPUT}}


    TerminalTargetHandoffWorkflow.ask.after = _chain_hooks(_terminaltargethandoffworkflow_on_outcome, _terminaltargethandoffworkflow_on_ask, TerminalTargetHandoffWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="pause now", tag="pause")])
    engine = Engine(
        TerminalTargetHandoffWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == AWAIT_INPUT
    assert result.checkpoint is not None
    assert result.checkpoint.pending_handoffs == ()


def test_compiled_workflow_is_deterministic():
    def _deterministicworkflow_on_ask(ctx):
        return None

    class DeterministicWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}


    first = compile_workflow(DeterministicWorkflow)
    second = compile_workflow(DeterministicWorkflow)

    assert first is second


def test_step_named_start_executes_without_being_treated_as_lifecycle_hook(tmp_path: Path):
    def _startnamedworkflow_on_start(ctx):
        ctx.state = ctx.state.model_copy(update={'handler_calls': ctx.state.handler_calls + 1})
        return None

    class StartNamedWorkflow(Workflow):
        class State(BaseModel):
            handler_calls: int = 0

        start = PromptStep(name="start", producer="start.md")
        entry = start
        transitions = {start: {"done": FINISH}}

    StartNamedWorkflow.start.after = _chain_hooks(_startnamedworkflow_on_start, StartNamedWorkflow.start.after)


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        StartNamedWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.handler_calls == 1


def test_step_named_outcome_executes_without_being_treated_as_global_middleware(tmp_path: Path):
    def _outcomenamedworkflow_on_outcome(ctx):
        ctx.state = ctx.state.model_copy(update={'handler_calls': ctx.state.handler_calls + 1})
        return None

    class OutcomeNamedWorkflow(Workflow):
        class State(BaseModel):
            handler_calls: int = 0

        outcome = PromptStep(name="outcome", producer="outcome.md")
        entry = outcome
        transitions = {outcome: {"done": FINISH}}

    OutcomeNamedWorkflow.outcome.after = _chain_hooks(_outcomenamedworkflow_on_outcome, OutcomeNamedWorkflow.outcome.after)


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        OutcomeNamedWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.handler_calls == 1


def test_step_named_verdict_executes_without_being_treated_as_global_middleware(tmp_path: Path):
    def _verdictnamedworkflow_on_verdict(ctx):
        ctx.state = ctx.state.model_copy(update={'handler_calls': ctx.state.handler_calls + 1})
        return None

    class VerdictNamedWorkflow(Workflow):
        class State(BaseModel):
            handler_calls: int = 0

        verdict = PromptStep(name="verdict", producer="verdict.md")
        entry = verdict
        transitions = {verdict: {"done": FINISH}}

    VerdictNamedWorkflow.verdict.after = _chain_hooks(_verdictnamedworkflow_on_verdict, VerdictNamedWorkflow.verdict.after)


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        VerdictNamedWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.handler_calls == 1


def test_scoped_step_advances_worklist_items_and_uses_item_placeholders(tmp_path: Path):
    def _advance_gate(ctx):
        if ctx.current_worklist.advance():
            return Goto("assess")
        return None

    def _scopedassessmentworkflow_on_assess(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, ctx.outcome.payload['item_id']], 'sessions': [*ctx.state.sessions, ctx.outcome.payload['session_id']]})
        return None

    class ScopedAssessmentWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)
            sessions: list[str] = Field(default_factory=list)

        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        reviewer = Session(continuity=Continuity.work_item(gates))
        assess = PromptStep(
            name="assess",
            producer="assess.md",
            session=reviewer,
            scope=gates,
            writes={"report": Artifact.md("{workflow_folder}/reports/{item.dir_key}.md")},
            route_metadata={"passed": Route(summary="gate assessed")},
        )
        entry = assess
        transitions = {assess: {"passed": Route.to(FINISH, on_taken=_advance_gate)}}

    ScopedAssessmentWorkflow.assess.after = _chain_hooks(_scopedassessmentworkflow_on_assess, ScopedAssessmentWorkflow.assess.after)


    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        '{"gates":[{"gate_id":"gate-a","title":"Gate A","status":"queued"},{"gate_id":"gate-b","title":"Gate B","status":"queued"}]}\n',
        encoding="utf-8",
    )

    def _turn(request):
        item = request.context.item
        assert item is not None
        request.artifacts.report.write_text(f"report for {item.id}\n")
        return Outcome(
            raw_output=f"assessed {item.id}",
            tag="passed",
            payload={"item_id": item.id, "session_id": request.session.session_id},
        )

    engine = Engine(
        ScopedAssessmentWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_turn, _turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    workflow_folder = task_folder / "wf_scoped_assessment_workflow"
    assert result.terminal == FINISH
    assert result.history == ("assess", "assess")
    assert result.state.seen == ["gate-a", "gate-b"]
    assert result.state.sessions[0] != result.state.sessions[1]
    assert (workflow_folder / "reports" / "gate-a.md").read_text(encoding="utf-8") == "report for gate-a\n"
    assert (workflow_folder / "reports" / "gate-b.md").read_text(encoding="utf-8") == "report for gate-b\n"


def test_selector_single_item_from_workflow_params_limits_scoped_execution(tmp_path: Path):
    def _advance_gate(ctx):
        if ctx.current_worklist.advance():
            return Goto("assess")
        return None

    def _selectedgateworkflow_on_assess(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, ctx.outcome.payload['item_id']]})
        return None

    class SelectedGateWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        gates = Worklist.from_items(
            name="gate",
            items=(
                {"id": "gate-a", "title": "Gate A"},
                {"id": "gate-b", "title": "Gate B"},
            ),
            selector=Selector(item_param="gate_id", mode_param="mode", allowed_modes=("all", "single")),
        )
        assess = PromptStep(
            name="assess",
            producer="assess.md",
            scope=gates,
            route_metadata={"passed": Route(summary="selected gate assessed")},
        )
        entry = assess
        transitions = {assess: {"passed": Route.to(FINISH, on_taken=_advance_gate)}}

    SelectedGateWorkflow.assess.after = _chain_hooks(_selectedgateworkflow_on_assess, SelectedGateWorkflow.assess.after)


    def _turn(request):
        item = request.context.item
        assert item is not None
        return Outcome(raw_output="ok", tag="passed", payload={"item_id": item.id})

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        SelectedGateWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_params={"gate_id": "gate-b", "mode": "single"},
    )

    assert result.terminal == FINISH
    assert result.history == ("assess",)
    assert result.state.seen == ["gate-b"]


def test_prompt_runtime_lazily_renders_item_and_worklist_placeholders(tmp_path: Path):
    class PromptRenderWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "alpha", "title": "Alpha", "payload": {"foo": "bar"}},),
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline(
                "Inspect {item.id} / {item.payload.foo} / {worklist.gate.current.id} / {worklist.gate.current.payload.foo}."
            ),
            scope=gates,
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)

    def _turn(request):
        assert request.prompt.text == "Inspect alpha / bar / alpha / bar."
        return Outcome(raw_output="ok", tag="done")

    engine = Engine(
        PromptRenderWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH


def test_prompt_runtime_renders_item_state_placeholders(tmp_path: Path):
    class GateState(BaseModel):
        severity: str = "medium"

    class ItemStatePromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "alpha", "title": "Alpha", "status": "pending"},),
            status="status",
            item_state=GateState,
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Inspect {item.state.status} / {item.state.severity}."),
            scope=gates,
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)

    def _turn(request):
        assert request.prompt.text == "Inspect pending / medium."
        return Outcome(raw_output="ok", tag="done")

    result = Engine(
        ItemStatePromptWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH


def test_prompt_runtime_reports_missing_item_state_field_with_placeholder_context(tmp_path: Path):
    class GateState(BaseModel):
        severity: str = "medium"

    class MissingItemStateFieldWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "alpha", "title": "Alpha"},),
            item_state=GateState,
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Inspect {item.state.priority}."),
            scope=gates,
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        MissingItemStateFieldWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt placeholder on step 'assess' \{item\.state\.priority\} references unknown runtime field 'priority' on worklist 'gate'",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_prompt_runtime_reports_missing_payload_path_with_placeholder_context(tmp_path: Path):
    class MissingPayloadPromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "alpha", "title": "Alpha", "payload": {}},),
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Inspect {item.payload.foo}."),
            scope=gates,
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        MissingPayloadPromptWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt placeholder on step 'assess' \{item\.payload\.foo\} references missing payload path 'foo' on worklist 'gate'",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_operation_prompt_runtime_reports_missing_payload_path_with_placeholder_context(tmp_path: Path):
    def _missingpayloadoperationworkflow_on_assess(ctx):
        llm("Inspect {item.payload.foo}.")
        return None

    class MissingPayloadOperationWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "alpha", "title": "Alpha", "payload": {}},),
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Assess the current item."),
            scope=gates,
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    MissingPayloadOperationWorkflow.assess.before = _chain_hooks(
        _missingpayloadoperationworkflow_on_assess,
        MissingPayloadOperationWorkflow.assess.before,
    )

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        MissingPayloadOperationWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt placeholder on step 'assess' \{item\.payload\.foo\} references missing payload path 'foo' on worklist 'gate'",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_prompt_runtime_reports_missing_worklist_current_payload_path_with_placeholder_context(tmp_path: Path):
    class MissingWorklistPayloadPromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "alpha", "title": "Alpha", "payload": {}},),
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Inspect {worklist.gate.current.payload.foo}."),
            scope=gates,
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        MissingWorklistPayloadPromptWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt placeholder on step 'assess' \{worklist\.gate\.current\.payload\.foo\} references missing payload path 'foo' on worklist 'gate'",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_prompt_runtime_reports_missing_current_item_with_placeholder_context(tmp_path: Path):
    class MissingCurrentItemPromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(name="gate", items=())
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Inspect {worklist.gate.current.id}."),
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        MissingCurrentItemPromptWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt placeholder on step 'assess' \{worklist\.gate\.current\.id\} requires a current item on worklist 'gate'",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_prompt_runtime_reports_missing_worklist_source_with_placeholder_context(tmp_path: Path):
    class MissingWorklistSourcePromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Inspect {worklist.gate.current.id}."),
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        MissingWorklistSourcePromptWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt placeholder on step 'assess' \{worklist\.gate\.current\.id\} could not load worklist 'gate'",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_unused_artifact_backed_worklist_does_not_load_on_non_scoped_path(tmp_path: Path):
    def _finish(_ctx):
        return Event("done")

    class UnusedArtifactWorklistWorkflow(Workflow):
        class State(BaseModel):
            pass

        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        finalize = PythonStep(name="finalize", handler=_finish)
        entry = finalize
        transitions = {finalize: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        UnusedArtifactWorklistWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert not (task_folder / "gates.json").exists()


def test_artifact_backed_worklist_materializes_after_runtime_creates_source(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    def _create_gates(ctx):
        ctx.write(
            ctx.task_folder / "gates.json",
            '{"gates":[{"gate_id":"gate-a","title":"Gate A","status":"queued"}]}\n',
        )
        return Event("done")

    class DeferredArtifactWorklistWorkflow(Workflow):
        class State(BaseModel):
            pass

        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        create_gates = PythonStep(name="create_gates", handler=_create_gates)
        assess = PromptStep(
            name="assess",
            producer="assess.md",
            scope=gates,
            route_metadata={"passed": Route(summary="gate assessed")},
        )
        entry = create_gates
        transitions = {
            create_gates: {"done": assess},
            assess: {"passed": FINISH},
        }

    def _turn(request):
        item = request.context.item
        assert item is not None
        assert item.id == "gate-a"
        return Outcome(raw_output="ok", tag="passed")

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        DeferredArtifactWorklistWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    resolved_events = [payload for event_type, payload in runtime_events if event_type == "worklist_selection_resolved"]
    assert result.terminal == FINISH
    assert len(resolved_events) == 1
    assert resolved_events[0]["worklist_name"] == "gate"
    assert resolved_events[0]["current_item_id"] == "gate-a"
    assert resolved_events[0]["current_index"] == 0
    assert resolved_events[0]["lazy"] is True
    assert resolved_events[0]["source"].startswith("artifact:")


def test_non_scoped_explicit_worklist_access_emits_resolution_event_for_only_requested_worklist(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    def _inspect(ctx):
        selection = ctx.selection("gate")
        assert selection.current is not None
        assert selection.current.id == "gate-a"
        assert set(ctx._selections) == {"gate"}
        return Event("done")

    class ExplicitSelectionWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "gate-a", "title": "Gate A"},),
        )
        reviews = Worklist.from_items(
            name="review",
            items=({"id": "review-a", "title": "Review A"},),
        )
        inspect = PythonStep(name="inspect", handler=_inspect)
        entry = inspect
        transitions = {inspect: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        ExplicitSelectionWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    resolved_events = [payload for event_type, payload in runtime_events if event_type == "worklist_selection_resolved"]
    assert result.terminal == FINISH
    assert len(resolved_events) == 1
    assert resolved_events[0]["step_name"] == "inspect"
    assert resolved_events[0]["worklist_name"] == "gate"
    assert resolved_events[0]["current_item_id"] == "gate-a"
    assert resolved_events[0]["current_index"] == 0
    assert resolved_events[0]["lazy"] is True
    assert resolved_events[0]["source"] == "static"


def test_non_scoped_current_access_emits_resolution_event_for_only_requested_worklist(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    def _inspect(ctx):
        current = ctx.current("gate")
        assert current is not None
        assert current.id == "gate-a"
        assert set(ctx._selections) == {"gate"}
        return Event("done")

    class ExplicitCurrentWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "gate-a", "title": "Gate A"},),
        )
        reviews = Worklist.from_items(
            name="review",
            items=({"id": "review-a", "title": "Review A"},),
        )
        inspect = PythonStep(name="inspect", handler=_inspect)
        entry = inspect
        transitions = {inspect: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        ExplicitCurrentWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    resolved_events = [payload for event_type, payload in runtime_events if event_type == "worklist_selection_resolved"]
    assert result.terminal == FINISH
    assert len(resolved_events) == 1
    assert resolved_events[0]["step_name"] == "inspect"
    assert resolved_events[0]["worklist_name"] == "gate"
    assert resolved_events[0]["current_item_id"] == "gate-a"
    assert resolved_events[0]["current_index"] == 0
    assert resolved_events[0]["lazy"] is True
    assert resolved_events[0]["source"] == "static"


def test_missing_artifact_backed_worklist_fails_at_first_scoped_use(tmp_path: Path):
    class MissingArtifactWorklistWorkflow(Workflow):
        class State(BaseModel):
            pass

        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        assess = PromptStep(name="assess", producer="assess.md", scope=gates)
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        MissingArtifactWorklistWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match="worklist 'gate' could not resolve selection from artifact source",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_artifact_backed_worklist_scaffold_policy_creates_source_at_first_scoped_use(tmp_path: Path):
    class ScaffoldArtifactWorklistWorkflow(Workflow):
        class State(BaseModel):
            pass

        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
            missing="scaffold",
        )
        assess = PromptStep(
            name="assess",
            producer="assess.md",
            scope=gates,
            route_metadata={"done": Route(summary="scaffold checked")},
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        ScaffoldArtifactWorklistWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert json.loads((task_folder / "gates.json").read_text(encoding="utf-8")) == {"gates": []}


def test_worklist_source_ensure_can_scaffold_backing_data_at_first_use(tmp_path: Path):
    class _ScaffoldSource:
        mutable = False
        artifact_backed = False

        def __init__(self, path: Path) -> None:
            self.path = path

        def ensure(self, ctx) -> None:
            if self.path.exists():
                return
            self.path.write_text(
                json.dumps(
                    [{"id": "gate-a", "title": "Gate A"}],
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        def load(self, ctx) -> tuple[WorkItem[dict[str, str]], ...]:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return tuple(
                WorkItem(
                    id=str(entry["id"]),
                    title=str(entry["title"]),
                    payload=dict(entry),
                    dir_key=str(entry["id"]),
                )
                for entry in payload
            )

        def save(self, ctx, items) -> None:
            return None

        def validate(self, ctx, items) -> str | None:
            return None

    source_path = tmp_path / "scaffolded-gates.json"

    class ScaffoldedWorklistWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist(name="gate", source=_ScaffoldSource(source_path))
        assess = PromptStep(name="assess", producer="assess.md", scope=gates)
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        ScaffoldedWorklistWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert source_path.exists()


def test_resume_does_not_reload_unused_checkpointed_worklists(tmp_path: Path):
    class _EnsureSource:
        mutable = False
        artifact_backed = False

        def __init__(self, path: Path) -> None:
            self.path = path

        def ensure(self, ctx) -> None:
            if self.path.exists():
                return
            self.path.write_text(
                json.dumps(
                    [{"id": "gate-a", "title": "Gate A"}],
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        def load(self, ctx) -> tuple[WorkItem[dict[str, str]], ...]:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return tuple(
                WorkItem(
                    id=str(entry["id"]),
                    title=str(entry["title"]),
                    payload=dict(entry),
                    dir_key=str(entry["id"]),
                )
                for entry in payload
            )

        def save(self, ctx, items) -> None:
            return None

        def validate(self, ctx, items) -> str | None:
            return None

    def _pause(ctx):
        if ctx.input_response is None:
            return RequestInput("Continue?")
        return Event("done")

    source_path = tmp_path / "resume-gates.json"

    class ResumeEnsureWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist(name="gate", source=_EnsureSource(source_path))
        assess = PromptStep(name="assess", producer="assess.md", scope=gates)
        pause = PythonStep(name="pause", handler=_pause)
        entry = assess
        transitions = {
            assess: {"done": pause},
            pause: {"done": FINISH},
        }

    checkpoint_store = InMemoryCheckpointStore()
    task_folder, run_folder = _workspace(tmp_path)
    paused = Engine(
        ResumeEnsureWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == AWAIT_INPUT
    source_path.unlink()

    resumed = Engine(
        ResumeEnsureWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer="yes",
    )

    assert resumed.terminal == FINISH
    assert not source_path.exists()


def test_resume_reloads_checkpointed_worklist_on_first_access_only(tmp_path: Path):
    class _EnsureSource:
        mutable = False
        artifact_backed = False

        def __init__(self, path: Path) -> None:
            self.path = path

        def ensure(self, ctx) -> None:
            if self.path.exists():
                return
            self.path.write_text(
                json.dumps(
                    [{"id": "gate-a", "title": "Gate A"}],
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        def load(self, ctx) -> tuple[WorkItem[dict[str, str]], ...]:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return tuple(
                WorkItem(
                    id=str(entry["id"]),
                    title=str(entry["title"]),
                    payload=dict(entry),
                    dir_key=str(entry["id"]),
                )
                for entry in payload
            )

        def save(self, ctx, items) -> None:
            return None

        def validate(self, ctx, items) -> str | None:
            return None

    def _pause(ctx):
        if ctx.input_response is None:
            return RequestInput("Continue?")
        return Event("done")

    source_path = tmp_path / "resume-lazy-gates.json"

    class ResumeEnsureOnAccessWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist(name="gate", source=_EnsureSource(source_path))
        assess = PromptStep(name="assess", producer="assess.md", scope=gates)
        pause = PythonStep(name="pause", handler=_pause)
        entry = assess
        transitions = {
            assess: {"done": pause},
            pause: {"done": assess},
        }

    checkpoint_store = InMemoryCheckpointStore()
    task_folder, run_folder = _workspace(tmp_path)
    paused = Engine(
        ResumeEnsureOnAccessWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == AWAIT_INPUT
    source_path.unlink()

    def _turn(request):
        assert source_path.exists()
        item = request.context.item
        assert item is not None
        assert item.id == "gate-a"
        return Outcome(raw_output="ok", tag="done")

    resumed = Engine(
        ResumeEnsureOnAccessWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer="yes",
    )

    assert resumed.terminal == AWAIT_INPUT
    assert source_path.exists()


def test_worklist_refresh_uses_source_ensure_when_backing_data_is_missing(tmp_path: Path):
    class _EnsureSource:
        mutable = False
        artifact_backed = False

        def __init__(self, path: Path) -> None:
            self.path = path

        def ensure(self, ctx) -> None:
            if self.path.exists():
                return
            self.path.write_text(
                json.dumps(
                    [{"id": "gate-a", "title": "Gate A"}],
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        def load(self, ctx) -> tuple[WorkItem[dict[str, str]], ...]:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return tuple(
                WorkItem(
                    id=str(entry["id"]),
                    title=str(entry["title"]),
                    payload=dict(entry),
                    dir_key=str(entry["id"]),
                )
                for entry in payload
            )

        def save(self, ctx, items) -> None:
            return None

        def validate(self, ctx, items) -> str | None:
            return None

    source_path = tmp_path / "refresh-gates.json"

    def _refresh(ctx):
        source_path.unlink()
        selection = ctx.worklist("gate").refresh()
        assert selection.current is not None
        assert selection.current.id == "gate-a"
        assert source_path.exists()
        return Event("done")

    class RefreshEnsureWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist(name="gate", source=_EnsureSource(source_path))
        assess = PromptStep(name="assess", producer="assess.md", scope=gates)
        refresh = PythonStep(name="refresh", handler=_refresh)
        entry = assess
        transitions = {
            assess: {"done": refresh},
            refresh: {"done": FINISH},
        }

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        RefreshEnsureWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert source_path.exists()


def test_resume_restores_materialized_worklists_and_lazily_materializes_unused_ones(tmp_path: Path):
    def _pause(ctx):
        if ctx.input_response is None:
            return RequestInput("Continue?")
        return Event("done")

    def _create_gates(ctx):
        ctx.write(
            ctx.task_folder / "gates.json",
            '{"gates":[{"gate_id":"gate-a","title":"Gate A","status":"queued"}]}\n',
        )
        return Event("done")

    class ResumeLazyWorklistWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        articles = Worklist.from_param("articles")
        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        review = PromptStep(
            name="review",
            producer="review.md",
            scope=articles,
            route_metadata={"passed": Route(summary="article reviewed")},
        )
        pause = PythonStep(name="pause", handler=_pause)
        create_gates = PythonStep(name="create_gates", handler=_create_gates)
        assess = PromptStep(
            name="assess",
            producer="assess.md",
            scope=gates,
            route_metadata={"passed": Route(summary="gate assessed")},
        )
        entry = review
        transitions = {
            review: {"passed": pause},
            pause: {"done": create_gates},
            create_gates: {"done": assess},
            assess: {"passed": FINISH},
        }

    checkpoint_store = InMemoryCheckpointStore()
    task_folder, run_folder = _workspace(tmp_path)
    initial_provider = ScriptedLLMProvider(
        llm_turns=[lambda request: Outcome(raw_output="ok", tag="passed", payload={"item_id": request.context.item.id})]
    )
    paused = Engine(
        ResumeLazyWorklistWorkflow,
        provider=initial_provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_params={"articles": [{"id": "article-a", "title": "Article A"}]},
    )

    checkpoint = checkpoint_store.load()
    assert paused.terminal == AWAIT_INPUT
    assert checkpoint is not None
    assert checkpoint.worklist_selections is not None
    assert set(checkpoint.worklist_selections) == {"articles"}

    resumed = Engine(
        ResumeLazyWorklistWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[lambda request: Outcome(raw_output="ok", tag="passed", payload={"item_id": request.context.item.id})]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_params={"articles": [{"id": "article-a", "title": "Article A"}]},
        answer="yes",
    )

    assert resumed.terminal == FINISH
    assert (task_folder / "gates.json").exists()


def test_scoped_item_state_and_step_item_state_resume_from_checkpoint(tmp_path: Path):
    class ArticleItemState(BaseModel):
        attempts: int = 0

    class ReviewItemState(BaseModel):
        attempts: int = 0
        note: str | None = None

    def _advance_article(ctx):
        if ctx.current_worklist.advance():
            return Goto("review")
        return None

    def _scopedstateresumeworkflow_on_review(ctx):
        next_visits = ctx.state.resumed_visits
        if ctx.outcome.payload['item_id'] == 'beta':
            next_visits = int(ctx.outcome.payload['visits'])
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, str(ctx.outcome.payload['item_id'])], 'resumed_visits': next_visits})
        return None

    class ScopedStateResumeWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)
            resumed_visits: int | None = None

        articles = Worklist.from_param(
            "articles",
            status="status",
            item_state=ArticleItemState,
        )
        review = PromptStep(
            name="review",
            producer="review.md",
            scope=articles,
            item_state=ReviewItemState,
            route_metadata={"passed": Route(summary="article reviewed")},
        )
        entry = review
        transitions = {review: {"passed": Route.to(FINISH, on_taken=_advance_article)}}

    ScopedStateResumeWorkflow.review.after = _chain_hooks(_scopedstateresumeworkflow_on_review, ScopedStateResumeWorkflow.review.after)


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()

    def _alpha_turn(request):
        item = request.context.item
        assert item is not None
        assert item.id == "alpha"
        assert request.context.item_state.status == "pending"
        assert request.context.item_state.last_step == "review"
        assert request.context.step_item_state.visits == 1
        request.context.current_worklist.set_current_status("alpha-complete")
        request.context.item_state.attempts += 1
        request.context.step_item_state.attempts += 1
        request.context.step_item_state.note = "alpha"
        return Outcome(raw_output="ok", tag="passed", payload={"item_id": item.id, "visits": request.context.step_item_state.visits})

    def _beta_fail_turn(request):
        item = request.context.item
        assert item is not None
        assert item.id == "beta"
        assert request.context.item_state.status == "pending"
        assert request.context.item_state.last_step == "review"
        assert request.context.step_item_state.visits == 1
        request.context.current_worklist.set_current_status("beta-started")
        request.context.item_state.attempts += 1
        request.context.step_item_state.attempts += 1
        request.context.step_item_state.note = "checkpointed"
        raise RuntimeError("checkpoint me")

    failing_engine = Engine(
        ScopedStateResumeWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_alpha_turn, _beta_fail_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="checkpoint me"):
        failing_engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            workflow_params={
                "articles": [
                    {"id": "alpha", "title": "Alpha", "status": "pending"},
                    {"id": "beta", "title": "Beta", "status": "pending"},
                ]
            },
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.item_states is not None
    assert len(checkpoint.item_states) == 2
    assert any(payload["status"] == "beta-started" and payload["attempts"] == 1 for payload in checkpoint.item_states.values())
    assert checkpoint.step_item_states is not None
    assert "review" in checkpoint.step_item_states
    assert len(checkpoint.step_item_states["review"]) == 2
    assert any(
        payload["note"] == "checkpointed" and payload["attempts"] == 1 and payload["visits"] == 1 and payload["last_route"] is None
        for payload in checkpoint.step_item_states["review"].values()
    )

    def _beta_resume_turn(request):
        item = request.context.item
        assert item is not None
        assert item.id == "beta"
        assert request.context.item_state.status == "beta-started"
        assert request.context.item_state.last_step == "review"
        assert request.context.item_state.attempts == 1
        assert request.context.step_item_state.attempts == 1
        assert request.context.step_item_state.note == "checkpointed"
        assert request.context.step_item_state.visits == 2
        request.context.current_worklist.set_current_status("beta-complete")
        request.context.item_state.attempts += 1
        request.context.step_item_state.attempts += 1
        return Outcome(raw_output="ok", tag="passed", payload={"item_id": item.id, "visits": request.context.step_item_state.visits})

    resumed_engine = Engine(
        ScopedStateResumeWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_beta_resume_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    result = resumed_engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_params={
            "articles": [
                {"id": "alpha", "title": "Alpha", "status": "pending"},
                {"id": "beta", "title": "Beta", "status": "pending"},
            ]
        },
    )

    assert result.terminal == FINISH
    assert result.state.seen == ["alpha", "beta"]
    assert result.state.resumed_visits == 2


def test_work_item_session_resume_uses_dir_key_based_key_and_reuses_session(tmp_path: Path):
    class WorkItemSessionResumeWorkflow(Workflow):
        class State(BaseModel):
            pass

        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        reviewer = Session(continuity=Continuity.work_item(gates))
        assess = PromptStep(
            name="assess",
            producer="assess.md",
            scope=gates,
            session=reviewer,
            route_metadata={"passed": Route(summary="gate assessed")},
        )
        entry = assess
        transitions = {assess: {"passed": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        '{"gates":[{"gate_id":"gate-a","dir_key":"phase-1","title":"Gate A","status":"queued"}]}\n',
        encoding="utf-8",
    )
    checkpoint_store = InMemoryCheckpointStore()
    first_session_id: str | None = None

    def _failing_turn(request):
        nonlocal first_session_id
        first_session_id = request.session.session_id
        raise RuntimeError("checkpoint me")

    failing_engine = Engine(
        WorkItemSessionResumeWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_failing_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="checkpoint me"):
        failing_engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.session_bindings.active_keys_by_slot["reviewer"] == SessionKey(
        slot="reviewer",
        domain="work_item",
        value="gate:phase-1",
    )
    assert first_session_id is not None

    def _resumed_turn(request):
        assert request.session.session_id == first_session_id
        return Outcome(raw_output="ok", tag="passed")

    resumed = Engine(
        WorkItemSessionResumeWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_resumed_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert resumed.terminal == FINISH


def test_non_scoped_work_item_session_fails_when_no_current_item_exists(tmp_path: Path):
    class EmptyWorkItemSessionWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(name="gate", items=())
        reviewer = Session(continuity=Continuity.work_item(gates))
        publish = PromptStep(name="publish", producer="publish.md", session=reviewer)
        entry = publish
        transitions = {publish: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        EmptyWorkItemSessionWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"session 'reviewer' uses work-item continuity for worklist 'gate', but no current work item is available for step 'publish'",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_resume_ignores_legacy_null_worklist_selection_payloads(tmp_path: Path):
    from autoloop.runtime.stores.filesystem import FilesystemCheckpointStore

    class LegacyNullSelectionWorkflow(Workflow):
        class State(BaseModel):
            resumed: bool = False

        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )

        @staticmethod
        def _publish(ctx):
            assert ctx._selection_snapshots == {}
            assert ctx._selections == {}
            ctx.state = ctx.state.model_copy(update={"resumed": True})
            return Event("done")

        publish = PythonStep(name="publish", handler=_publish)
        entry = publish
        transitions = {publish: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_path = run_folder / "checkpoint.json"
    checkpoint_store = FilesystemCheckpointStore(checkpoint_path, LegacyNullSelectionWorkflow.State)
    checkpoint_store.save(
        Checkpoint(
            stage="publish",
            state=LegacyNullSelectionWorkflow.State(),
            session_bindings=SessionSnapshot(bindings=(), active_keys_by_slot={}),
        )
    )

    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    payload["worklist_selections"] = {"gate": None}
    checkpoint_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    result = Engine(
        LegacyNullSelectionWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).resume(
        task_id="task-legacy",
        run_id="run-legacy",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.resumed is True
    assert not (task_folder / "gates.json").exists()


def test_artifact_backed_worklist_duplicate_ids_fail_before_scoped_execution(tmp_path: Path):
    def _advance_gate(ctx):
        if ctx.current_worklist.advance():
            return Goto("assess")
        return None

    def _duplicategateworkflow_on_assess(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': ctx.state.seen + 1})
        return None

    class DuplicateGateWorkflow(Workflow):
        class State(BaseModel):
            seen: int = 0

        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        assess = PromptStep(
            name="assess",
            producer="assess.md",
            scope=gates,
            route_metadata={"passed": Route(summary="gate assessed")},
        )
        entry = assess
        transitions = {assess: {"passed": Route.to(FINISH, on_taken=_advance_gate)}}

    DuplicateGateWorkflow.assess.after = _chain_hooks(_duplicategateworkflow_on_assess, DuplicateGateWorkflow.assess.after)


    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        '{"gates":[{"gate_id":"dup","title":"Gate A","status":"queued"},{"gate_id":"dup","title":"Gate B","status":"queued"}]}\n',
        encoding="utf-8",
    )
    engine = Engine(
        DuplicateGateWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(WorkflowExecutionError, match="duplicate item id"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_llm_step_hooks_run_in_order_and_on_taken_follows_after_hooks(tmp_path: Path):
    seen_provider_state: list[list[str]] = []

    def before_ask(ctx):
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "before"]})

    def after_ask(ctx):
        assert ctx.state.seen == ["before", "handler"]
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "after"]})

    def on_taken(ctx):
        ctx.state.seen.append("on_taken")

    def _hookedllmworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, 'handler']})
        return None

    class HookedLLMWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        ask = PromptStep(name="ask", producer="ask.md", before=before_ask, after=after_ask)
        entry = ask
        transitions = {ask: {"done": Route.to(FINISH, on_taken=on_taken)}}

    HookedLLMWorkflow.ask.after = _chain_hooks(_hookedllmworkflow_on_ask, HookedLLMWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                seen_provider_state.append(list(request.context.state.seen)),
                Outcome(raw_output="ok", tag="done"),
            )[1]
        ]
    )
    result = Engine(
        HookedLLMWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "done"
    assert result.state.seen == ["before", "handler", "after", "on_taken"]
    assert seen_provider_state == [["before"]]


def test_system_step_hook_events_are_observable(tmp_path: Path):
    hook_events: list[tuple[str, str, str | None]] = []

    def before_publish(ctx):
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "before"]})

    def after_publish(ctx):
        assert ctx.outcome.tag == "done"
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "after"]})

    def on_taken(ctx):
        ctx.state.seen.append("on_taken")

    def _hookedsystemworkflow_on_publish(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, 'handler']})
        return Event('done')

    class HookedSystemWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        publish = PythonStep(name="publish", before=before_publish, after=after_publish, handler=_hookedsystemworkflow_on_publish)
        entry = publish
        transitions = {publish: {"done": Route.to(FINISH, on_taken=on_taken)}}


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        HookedSystemWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        hook_event_sink=lambda event_type, payload: hook_events.append(
            (event_type, str(payload.get("phase")), payload.get("route"))
        ),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.seen == ["before", "handler", "after", "on_taken"]
    assert hook_events == [
        ("hook_started", "before", None),
        ("hook_finished", "before", None),
        ("hook_started", "after", "done"),
        ("hook_finished", "after", "done"),
        ("hook_started", "on_taken", "done"),
        ("hook_finished", "on_taken", "done"),
    ]


def test_before_hook_route_short_circuits_without_provider_and_preserves_candidate_route_none(tmp_path: Path):
    def before_ask(ctx):
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "before"]})
        return Event("done")

    class BeforeHookRouteWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        ask = PromptStep(name="ask", producer="ask.md", before=before_ask)
        entry = ask
        transitions = {ask: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="unexpected", tag="done")])
    result = Engine(
        BeforeHookRouteWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.seen == ["before"]
    assert provider.calls == []
    assert result.last_transition is not None
    assert result.last_transition.candidate_route is None
    assert result.last_transition.final_route == "done"
    assert result.last_transition.provider_attributable is False
    assert result.last_transition.provider_attempted is False
    assert result.last_transition.source_hook == "before_ask"
    assert result.last_transition.source_phase == "before"


def test_before_hook_request_input_short_circuits_without_provider_and_preserves_last_route(tmp_path: Path):
    def before_ask(ctx):
        ctx.state.approval_status = "awaiting_input"
        return RequestInput("Approve the change?", input_schema=_ApprovalInput)

    def _beforehookrequestinputworkflow_on_ask(ctx):
        raise AssertionError('provider outcome handler should not run when before short-circuits')

    class BeforeHookRequestInputWorkflow(Workflow):
        class State(BaseModel):
            approval_status: str = "new"

        ask = PromptStep(name="ask", producer="ask.md", before=before_ask)
        entry = ask
        transitions = {ask: {"done": FINISH}}

    BeforeHookRequestInputWorkflow.ask.after = _chain_hooks(_beforehookrequestinputworkflow_on_ask, BeforeHookRequestInputWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="unexpected", tag="done")])
    paused = Engine(
        BeforeHookRequestInputWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == AWAIT_INPUT
    assert paused.state.approval_status == "awaiting_input"
    assert provider.calls == []
    assert paused.last_transition is not None
    assert paused.last_transition.candidate_route is None
    assert paused.last_transition.final_route is None
    assert paused.last_transition.runtime_control == "request_input"
    assert paused.last_transition.provider_attempted is False
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_input is not None
    assert paused.last_transition.pending_input_id == paused.checkpoint.pending_input.pending_input_id
    assert paused.checkpoint.pending_input.question == "Approve the change?"
    assert paused.checkpoint.pending_input.source_hook == "before_ask"
    assert paused.checkpoint.pending_input.source_phase == "before"
    assert paused.checkpoint.step_states is not None
    assert paused.checkpoint.step_states["ask"]["last_route"] is None


def test_before_verifier_route_short_circuits_verifier_and_preserves_candidate_route_none(tmp_path: Path):
    def before_verifier(ctx):
        return Event("approved")

    class BeforeVerifierRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            before_verifier=before_verifier,
        )
        entry = pair
        transitions = {pair: {"approved": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["draft copy"],
        verifier_turns=[Outcome(raw_output="unexpected", tag="approved")],
    )
    result = Engine(
        BeforeVerifierRouteWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert [call.kind for call in provider.calls] == ["producer"]
    assert result.last_transition is not None
    assert result.last_transition.candidate_route is None
    assert result.last_transition.final_route == "approved"
    assert result.last_transition.provider_attributable is False
    assert result.last_transition.provider_attempted is True
    assert result.last_transition.producer_attempted is True
    assert result.last_transition.verifier_attempted is False
    assert result.last_transition.source_hook == "before_verifier"
    assert result.last_transition.source_phase == "before_verifier"


def test_before_verifier_request_input_short_circuits_verifier_and_checkpoints_pending_input(tmp_path: Path):
    def before_verifier(ctx):
        ctx.state.approval_status = "awaiting_verifier_input"
        return RequestInput("Approve before verification?", input_schema=_ApprovalInput)

    def _beforeverifierrequestinputworkflow_on_pair(ctx):
        raise AssertionError("pair outcome handler should not run when before_verifier short-circuits")

    class BeforeVerifierRequestInputWorkflow(Workflow):
        class State(BaseModel):
            approval_status: str = "new"

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            before_verifier=before_verifier,
        )
        entry = pair
        transitions = {pair: {"approved": FINISH}}

    BeforeVerifierRequestInputWorkflow.pair.after_verifier = _chain_hooks(
        _beforeverifierrequestinputworkflow_on_pair,
        BeforeVerifierRequestInputWorkflow.pair.after_verifier,
    )

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["draft copy"],
        verifier_turns=[Outcome(raw_output="unexpected", tag="approved")],
    )
    paused = Engine(
        BeforeVerifierRequestInputWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == AWAIT_INPUT
    assert paused.state.approval_status == "awaiting_verifier_input"
    assert [call.kind for call in provider.calls] == ["producer"]
    assert paused.last_transition is not None
    assert paused.last_transition.candidate_route is None
    assert paused.last_transition.final_route is None
    assert paused.last_transition.runtime_control == "request_input"
    assert paused.last_transition.provider_attributable is False
    assert paused.last_transition.provider_attempted is True
    assert paused.last_transition.producer_attempted is True
    assert paused.last_transition.verifier_attempted is False
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_input is not None
    assert paused.last_transition.pending_input_id == paused.checkpoint.pending_input.pending_input_id
    assert paused.checkpoint.pending_input.question == "Approve before verification?"
    assert paused.checkpoint.pending_input.source_hook == "before_verifier"
    assert paused.checkpoint.pending_input.source_phase == "before_verifier"
    assert paused.checkpoint.step_states is not None
    assert paused.checkpoint.step_states["pair"]["last_route"] is None


def test_before_verifier_invalid_goto_preserves_state_and_failure_context(tmp_path: Path):
    def before_verifier(ctx):
        ctx.state.approval_status = "mutated before invalid goto"
        return Goto("missing_step", reason="Verifier should jump to a missing step.")

    class BeforeVerifierInvalidGotoWorkflow(Workflow):
        class State(BaseModel):
            approval_status: str = "new"

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            before_verifier=before_verifier,
        )
        entry = pair
        transitions = {pair: {"approved": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    provider = ScriptedLLMProvider(
        producer_turns=["draft copy"],
        verifier_turns=[Outcome(raw_output="unexpected", tag="approved")],
    )
    engine = Engine(
        BeforeVerifierInvalidGotoWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="declared workflow step"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.state.approval_status == "mutated before invalid goto"
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "runtime_control_validation"
    assert checkpoint.failure_context["runtime_control"] == "goto"
    assert checkpoint.failure_context["source_hook"] == "before_verifier"
    assert checkpoint.failure_context["source_phase"] == "before_verifier"
    assert [call.kind for call in provider.calls] == ["producer"]


def test_pair_hooks_before_verifier_preserve_state_mutations_on_success(tmp_path: Path):
    def after_producer(ctx):
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "after_producer"]})
        return None

    def before_verifier(ctx):
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "before_verifier"]})
        return None

    def _pairhookstateworkflow_on_pair(ctx):
        ctx.state = ctx.state.model_copy(update={"approved": bool(ctx.outcome.payload["approved"])})
        return None

    class PairHookStateWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)
            approved: bool = False

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            after_producer=after_producer,
            before_verifier=before_verifier,
        )
        entry = pair
        transitions = {pair: {"approved": FINISH}}

    PairHookStateWorkflow.pair.after_verifier = _chain_hooks(
        _pairhookstateworkflow_on_pair,
        PairHookStateWorkflow.pair.after_verifier,
    )

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["draft copy"],
        verifier_turns=[Outcome(raw_output="approved", tag="approved", payload={"approved": True})],
    )
    result = Engine(
        PairHookStateWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert [call.kind for call in provider.calls] == ["producer", "verifier"]
    assert result.state.seen == ["after_producer", "before_verifier"]
    assert result.state.approved is True
    assert result.last_transition is not None
    assert result.last_transition.provider_attempted is True
    assert result.last_transition.producer_attempted is True
    assert result.last_transition.verifier_attempted is True


def test_before_producer_route_short_circuits_without_provider_and_preserves_candidate_route_none(tmp_path: Path):
    def before_producer(ctx):
        return Event("approved")

    def _beforeproducerrouteworkflow_on_pair(ctx):
        raise AssertionError('pair outcome handler should not run when before_producer short-circuits')

    class BeforeProducerRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            before_producer=before_producer,
        )
        entry = pair
        transitions = {pair: {"approved": FINISH}}

    BeforeProducerRouteWorkflow.pair.after_verifier = _chain_hooks(_beforeproducerrouteworkflow_on_pair, BeforeProducerRouteWorkflow.pair.after_verifier)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["unexpected draft"],
        verifier_turns=[Outcome(raw_output="unexpected", tag="approved")],
    )
    result = Engine(
        BeforeProducerRouteWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert provider.calls == []
    assert result.last_transition is not None
    assert result.last_transition.candidate_route is None
    assert result.last_transition.final_route == "approved"
    assert result.last_transition.provider_attributable is False
    assert result.last_transition.provider_attempted is False
    assert result.last_transition.source_hook == "before_producer"
    assert result.last_transition.source_phase == "before_producer"


def test_before_producer_request_input_short_circuits_without_provider_and_checkpoints_pending_input(tmp_path: Path):
    def before_producer(ctx):
        ctx.state.approval_status = "awaiting_producer_input"
        return RequestInput("Approve the producer plan?", input_schema=_ApprovalInput)

    def _beforeproducerrequestinputworkflow_on_pair(ctx):
        raise AssertionError('pair outcome handler should not run when before_producer short-circuits')

    class BeforeProducerRequestInputWorkflow(Workflow):
        class State(BaseModel):
            approval_status: str = "new"

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            before_producer=before_producer,
        )
        entry = pair
        transitions = {pair: {"approved": FINISH}}

    BeforeProducerRequestInputWorkflow.pair.after_verifier = _chain_hooks(_beforeproducerrequestinputworkflow_on_pair, BeforeProducerRequestInputWorkflow.pair.after_verifier)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["unexpected draft"],
        verifier_turns=[Outcome(raw_output="unexpected", tag="approved")],
    )
    paused = Engine(
        BeforeProducerRequestInputWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == AWAIT_INPUT
    assert paused.state.approval_status == "awaiting_producer_input"
    assert provider.calls == []
    assert paused.last_transition is not None
    assert paused.last_transition.candidate_route is None
    assert paused.last_transition.final_route is None
    assert paused.last_transition.runtime_control == "request_input"
    assert paused.last_transition.provider_attempted is False
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_input is not None
    assert paused.last_transition.pending_input_id == paused.checkpoint.pending_input.pending_input_id
    assert paused.checkpoint.pending_input.question == "Approve the producer plan?"
    assert paused.checkpoint.pending_input.source_phase == "before_producer"
    assert paused.checkpoint.step_states is not None
    assert paused.checkpoint.step_states["pair"]["last_route"] is None


def test_engine_emits_scoped_hook_failure_events_with_step_execution_identity(tmp_path: Path):
    def before_review(ctx):
        raise RuntimeError("boom")

    def _scopedhookfailureworkflow_on_review(ctx):
        return None

    class ScopedHookFailureWorkflow(Workflow):
        class State(BaseModel):
            pass

        articles = Worklist.from_param("articles")
        review = PromptStep(name="review", producer="review.md", scope=articles, before=before_review)
        entry = review
        transitions = {review: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    hook_events: list[tuple[str, dict[str, object]]] = []
    engine = Engine(
        ScopedHookFailureWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        hook_event_sink=lambda event_type, payload: hook_events.append((event_type, dict(payload))),
    )

    with pytest.raises(WorkflowExecutionError, match="boom"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            workflow_params={"articles": [{"id": "alpha", "title": "Alpha"}]},
        )

    hook_failed = [payload for event_type, payload in hook_events if event_type == "hook_failed"]
    assert hook_failed == [
        {
            "step_name": "review",
            "visit": 1,
            "step_execution_id": "review:articles:alpha:1",
            "scope": "articles",
            "item_id": "alpha",
            "hook_name": "before_review",
            "phase": "before",
            "error": "boom",
        }
    ]


def test_after_hook_returning_route_string_reroutes_execution(tmp_path: Path):
    def after_ask(ctx):
        return "rerouted"

    def _hookretryworkflow_on_ask(ctx):
        return None

    class HookRetryWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            after=after_ask,
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"done": FINISH, "rerouted": FAIL}}


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="first", tag="done")])

    result = Engine(
        HookRetryWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FAIL
    assert result.last_event is not None
    assert result.last_event.tag == "rerouted"
    assert [call.attempt for call in provider.calls] == [1]


def test_after_hook_dynamic_invalid_route_fails_as_runtime_error(tmp_path: Path):
    def after_ask(ctx):
        return ctx.state.redirect_to

    def _hookinvalidrouteworkflow_on_ask(ctx):
        return None

    class HookInvalidRouteWorkflow(Workflow):
        class State(BaseModel):
            redirect_to: str = "missing_route"

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            after=after_ask,
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"done": FINISH, "failed": FAIL}}


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])

    with pytest.raises(WorkflowExecutionError, match="produced illegal route 'missing_route'"):
        Engine(
            HookInvalidRouteWorkflow,
            provider=provider,
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    assert len(provider.calls) == 1


def test_provider_after_hook_event_override_reroutes_execution(tmp_path: Path):
    def after_ask(ctx):
        return Event("failed", reason="nope")

    def _hookhardfailworkflow_on_ask(ctx):
        return None

    class HookHardFailWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            after=after_ask,
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"done": FINISH, "failed": FAIL}}


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])

    result = Engine(
        HookHardFailWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FAIL
    assert result.last_event is not None
    assert result.last_event.tag == "failed"
    assert result.last_event.reason == "nope"
    assert len(provider.calls) == 1


def test_workflow_step_after_hook_can_mutate_state_after_child_completion(tmp_path: Path):
    task_folder, run_folder = _workspace(tmp_path)
    child_result_path = task_folder / "wf_workflow_hook_override_workflow" / "launch" / "child_result.json"
    child_runs: list[str] = []

    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    def before_launch(ctx):
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "before"]})

    def after_launch(ctx):
        assert ctx.outcome.tag == "done"
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "after"]})

    class WorkflowHookOverrideWorkflow(SimpleWorkflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        launch = workflow_step(
            ChildWorkflow,
            message="Run child workflow",
            writes=[Json("child_result")],
            before=before_launch,
            after=after_launch,
        )

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_runs.append(message)
        child_run_root = task_folder / "child-runs" / f"child-{len(child_runs)}"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id=f"child-{len(child_runs)}",
            terminal=FINISH,
            status="success",
            last_event=Event("done"),
            output_metadata={},
            output_artifacts={},
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_root / "run",
            package_folder=child_run_root / "package",
            request_file=child_run_root / "request.md",
            run_meta_file=child_run_root / "run.json",
            events_file=child_run_root / "events.jsonl",
            checkpoint_file=child_run_root / "checkpoint.json",
            sessions_dir=child_run_root / "sessions",
            trace_file=child_run_root / "trace.jsonl",
            raw_dir=child_run_root / "raw",
            parent_file=child_run_root / "parent.json",
        )

    result = Engine(
        WorkflowHookOverrideWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_invoker=invoke_child,
    )

    assert result.terminal == FINISH
    assert result.state.seen == ["before", "after"]
    assert child_runs == ["Run child workflow"]
    assert child_result_path.exists()


@pytest.mark.parametrize(
    ("child_terminal", "child_event", "expected_terminal", "expected_tag"),
    [
        (FINISH, Event("done"), FINISH, "done"),
        (FAIL, Event("failed", reason="child failed"), FAIL, "failed"),
        (AWAIT_INPUT, Event("question", question="Need input?"), AWAIT_INPUT, "question"),
        (AWAIT_INPUT, Event("blocked", reason="Waiting on a dependency."), AWAIT_INPUT, "blocked"),
    ],
)
def test_workflow_step_maps_child_terminals_and_writes_outputs(
    tmp_path: Path,
    child_terminal: str,
    child_event: Event,
    expected_terminal: str,
    expected_tag: str,
):
    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    class ParentWorkflow(SimpleWorkflow):
        launch = workflow_step(
            ChildWorkflow,
            message="Run child workflow",
            writes=[Json("child_result"), Md("child_summary")],
            routes={"done": FINISH, "question": AWAIT_INPUT, "blocked": AWAIT_INPUT, "failed": FAIL},
        )

    task_folder, run_folder = _workspace(tmp_path)

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_run_root = task_folder / "child-runs" / expected_tag
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id=f"child-{expected_tag}",
            terminal=child_terminal,
            status="success" if child_terminal == FINISH else ("failed" if child_terminal == FAIL else "paused"),
            last_event=child_event,
            output_metadata={"score": 1},
            output_artifacts={"report": child_run_root / "report.md"},
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_root / "run",
            package_folder=child_run_root / "package",
            request_file=child_run_root / "request.md",
            run_meta_file=child_run_root / "run.json",
            events_file=child_run_root / "events.jsonl",
            checkpoint_file=child_run_root / "checkpoint.json",
            sessions_dir=child_run_root / "sessions",
            trace_file=child_run_root / "trace.jsonl",
            raw_dir=child_run_root / "raw",
            parent_file=child_run_root / "parent.json",
        )

    result = Engine(
        ParentWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_invoker=invoke_child,
    )

    workflow_root = task_folder / "wf_parent_workflow" / "launch"
    child_result_payload = json.loads((workflow_root / "child_result.json").read_text(encoding="utf-8"))
    child_summary = (workflow_root / "child_summary.md").read_text(encoding="utf-8")

    assert result.terminal == expected_terminal
    assert result.last_event is not None
    assert result.last_event.tag == expected_tag
    assert child_result_payload["terminal"] == child_terminal
    assert child_result_payload["last_event"] == child_event.tag
    assert "Child workflow: child_workflow" in child_summary
    assert "Output artifacts:" in child_summary


def test_workflow_step_rejects_child_question_without_question_payload(tmp_path: Path):
    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    class ParentWorkflow(SimpleWorkflow):
        launch = workflow_step(ChildWorkflow, message="Run child workflow", routes={"question": AWAIT_INPUT})

    task_folder, run_folder = _workspace(tmp_path)

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_run_root = task_folder / "child-runs" / "invalid-question"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id="child-invalid-question",
            terminal=AWAIT_INPUT,
            status="paused",
            last_event=Event("question"),
            output_metadata={},
            output_artifacts={},
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_root / "run",
            package_folder=child_run_root / "package",
            request_file=child_run_root / "request.md",
            run_meta_file=child_run_root / "run.json",
            events_file=child_run_root / "events.jsonl",
            checkpoint_file=child_run_root / "checkpoint.json",
            sessions_dir=child_run_root / "sessions",
            trace_file=child_run_root / "trace.jsonl",
            raw_dir=child_run_root / "raw",
            parent_file=child_run_root / "parent.json",
        )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"returned terminal 'AWAIT_INPUT'.*maps to route 'blocked'.*declared routes are: question",
    ):
        Engine(
            ParentWorkflow,
            provider=ScriptedLLMProvider(),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            workflow_invoker=invoke_child,
        )


def test_workflow_step_maps_child_question_from_projected_event_question_not_tag_name(tmp_path: Path):
    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    class ParentWorkflow(SimpleWorkflow):
        launch = workflow_step(ChildWorkflow, message="Run child workflow", routes={"question": AWAIT_INPUT})

    task_folder, run_folder = _workspace(tmp_path)

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_run_root = task_folder / "child-runs" / "projected-question"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id="child-projected-question",
            terminal=AWAIT_INPUT,
            status="paused",
            last_event=Event("clarify", reason="Need a decision.", question="Approve the rollout?"),
            output_metadata={},
            output_artifacts={},
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_root / "run",
            package_folder=child_run_root / "package",
            request_file=child_run_root / "request.md",
            run_meta_file=child_run_root / "run.json",
            events_file=child_run_root / "events.jsonl",
            checkpoint_file=child_run_root / "checkpoint.json",
            sessions_dir=child_run_root / "sessions",
            trace_file=child_run_root / "trace.jsonl",
            raw_dir=child_run_root / "raw",
            parent_file=child_run_root / "parent.json",
        )

    result = Engine(
        ParentWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_invoker=invoke_child,
    )

    assert result.terminal == AWAIT_INPUT
    assert result.last_event is not None
    assert result.last_event.tag == "question"
    assert result.last_event.reason == "Need a decision."
    assert result.last_event.question == "Approve the rollout?"


def test_workflow_step_requires_explicit_failed_route_for_child_fail(tmp_path: Path):
    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    class ParentWorkflow(SimpleWorkflow):
        launch = workflow_step(ChildWorkflow, message="Run child workflow", routes={"done": FINISH})

    task_folder, run_folder = _workspace(tmp_path)

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_run_root = task_folder / "child-runs" / "missing-failed-route"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id="child-missing-failed-route",
            terminal=FAIL,
            status="failed",
            last_event=Event("failed", reason="child failed"),
            output_metadata={},
            output_artifacts={},
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_root / "run",
            package_folder=child_run_root / "package",
            request_file=child_run_root / "request.md",
            run_meta_file=child_run_root / "run.json",
            events_file=child_run_root / "events.jsonl",
            checkpoint_file=child_run_root / "checkpoint.json",
            sessions_dir=child_run_root / "sessions",
            trace_file=child_run_root / "trace.jsonl",
            raw_dir=child_run_root / "raw",
            parent_file=child_run_root / "parent.json",
        )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"child workflow step 'launch' returned terminal 'FAIL'.*maps to route 'failed'.*declared routes are: done.*declare the route or change child-result mapping",
    ):
        Engine(
            ParentWorkflow,
            provider=ScriptedLLMProvider(),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            workflow_invoker=invoke_child,
        )


def test_workflow_step_requires_explicit_blocked_route_for_child_await_without_question(tmp_path: Path):
    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    class ParentWorkflow(SimpleWorkflow):
        launch = workflow_step(ChildWorkflow, message="Run child workflow", routes={"done": FINISH})

    task_folder, run_folder = _workspace(tmp_path)

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_run_root = task_folder / "child-runs" / "missing-blocked-route"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id="child-missing-blocked-route",
            terminal=AWAIT_INPUT,
            status="paused",
            last_event=Event("blocked", reason="Waiting on a dependency."),
            output_metadata={},
            output_artifacts={},
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_root / "run",
            package_folder=child_run_root / "package",
            request_file=child_run_root / "request.md",
            run_meta_file=child_run_root / "run.json",
            events_file=child_run_root / "events.jsonl",
            checkpoint_file=child_run_root / "checkpoint.json",
            sessions_dir=child_run_root / "sessions",
            trace_file=child_run_root / "trace.jsonl",
            raw_dir=child_run_root / "raw",
            parent_file=child_run_root / "parent.json",
        )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"child workflow step 'launch' returned terminal 'AWAIT_INPUT'.*maps to route 'blocked'.*declared routes are: done.*declare the route or change child-result mapping",
    ):
        Engine(
            ParentWorkflow,
            provider=ScriptedLLMProvider(),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            workflow_invoker=invoke_child,
        )


def test_prompt_step_rejects_removed_on_route_keyword():
    with pytest.raises(TypeError, match="on_route"):
        PromptStep(name="ask", producer="ask.md", on_route=lambda ctx: None)


def test_on_taken_runs_before_required_output_validation_and_can_heal_artifact(tmp_path: Path):
    def on_taken(ctx):
        ctx.artifacts.report.write_text("published report\n")

    def _overriderequiredoutputworkflow_on_ask(ctx):
        return None

    class OverrideRequiredOutputWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": Artifact.md("report.md")},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "done": Route.to(FINISH, required_writes=("report",), on_taken=on_taken),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        OverrideRequiredOutputWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert (
        task_folder / "wf_override_required_output_workflow" / "ask" / "report.md"
    ).read_text(encoding="utf-8") == "published report\n"


def test_route_hooks_can_reroute_across_a_chain_and_emit_redirect_events(tmp_path: Path):
    hook_events: list[tuple[str, str, str, str]] = []

    def after_ask(ctx):
        route = ctx.route.tag
        ctx.state.seen.append(f"after:{route}")
        if route == "draft":
            return "review"
        return None

    def on_review_taken(ctx):
        ctx.state.seen.append("on_taken:review")
        return Event("publish", reason="approved")

    def on_publish_taken(ctx):
        ctx.state.seen.append("on_taken:publish")

    def _routeredirectworkflow_on_ask(ctx):
        return None

    class RouteRedirectWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        ask = PromptStep(name="ask", producer="ask.md", after=after_ask, retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {
            ask: {
                "draft": Route.to(FINISH),
                "review": Route.to(FINISH, on_taken=on_review_taken),
                "publish": Route.to(FINISH, on_taken=on_publish_taken),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        RouteRedirectWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="draft")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        hook_event_sink=lambda event_type, payload: hook_events.append(
            (
                event_type,
                str(payload.get("phase")),
                str(payload.get("from_route")),
                str(payload.get("to_route")),
            )
        )
        if event_type == "hook_route_redirected"
        else None,
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "publish"
    assert result.state.seen == [
        "after:draft",
        "on_taken:review",
        "on_taken:publish",
    ]
    assert hook_events == [
        ("hook_route_redirected", "after", "draft", "review"),
        ("hook_route_redirected", "on_taken", "review", "publish"),
    ]


def test_engine_emits_scoped_after_hook_redirect_events_with_step_execution_identity(tmp_path: Path):
    def after_review(ctx):
        if ctx.route.tag == "draft":
            return "review"
        return None

    def on_review_taken(ctx):
        return "publish"

    def _scopedrouteredirectworkflow_on_review(ctx):
        return None

    class ScopedRouteRedirectWorkflow(Workflow):
        class State(BaseModel):
            pass

        articles = Worklist.from_param("articles")
        review = PromptStep(
            name="review",
            producer="review.md",
            scope=articles,
            after=after_review,
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = review
        transitions = {
            review: {
                "draft": Route.to(FINISH),
                "review": Route.to(FINISH, on_taken=on_review_taken),
                "publish": Route.to(FINISH),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    hook_events: list[dict[str, object]] = []
    result = Engine(
        ScopedRouteRedirectWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="draft")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        hook_event_sink=lambda event_type, payload: hook_events.append(dict(payload))
        if event_type == "hook_route_redirected"
        else None,
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_params={"articles": [{"id": "alpha", "title": "Alpha"}]},
    )

    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "publish"
    assert hook_events == [
        {
            "step_name": "review",
            "visit": 1,
            "step_execution_id": "review:articles:alpha:1",
            "scope": "articles",
            "item_id": "alpha",
            "hook": "after_review",
            "hook_name": "after_review",
            "phase": "after",
            "from_route": "draft",
            "to_route": "review",
        },
        {
            "step_name": "review",
            "visit": 1,
            "step_execution_id": "review:articles:alpha:1",
            "scope": "articles",
            "item_id": "alpha",
            "hook": "on_review_taken",
            "hook_name": "on_review_taken",
            "phase": "on_taken",
            "from_route": "review",
            "to_route": "publish",
        },
    ]


def test_route_redirected_final_route_drives_required_write_validation(tmp_path: Path):
    def after_ask(ctx):
        return "publish"

    def _finalroutevalidationworkflow_on_ask(ctx):
        return None

    class FinalRouteValidationWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": Artifact.md("report.md")},
            after=after_ask,
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "draft": Route.to(FINISH, required_writes=[]),
                "publish": Route.to(FINISH, required_writes=("report",)),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    with pytest.raises(WorkflowExecutionError, match=r"artifact validation failed.*route 'publish'"):
        Engine(
            FinalRouteValidationWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="draft")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_route_redirect_cycle_fails_after_max_hook_redirects(tmp_path: Path):
    hook_events: list[tuple[str, str]] = []

    def on_draft_taken(ctx):
        return "review"

    def on_review_taken(ctx):
        return "draft"

    def _redirectcycleworkflow_on_ask(ctx):
        return None

    class RedirectCycleWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {
            ask: {
                "draft": Route.to(FINISH, on_taken=on_draft_taken),
                "review": Route.to(FINISH, on_taken=on_review_taken),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    with pytest.raises(
        WorkflowExecutionError,
        match=r"Hook redirect limit exceeded for step 'ask'.*draft -> review -> draft",
    ):
        Engine(
            RedirectCycleWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="draft")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
            hook_event_sink=lambda event_type, payload: hook_events.append((payload["from_route"], payload["to_route"]))
            if event_type == "hook_route_redirected"
            else None,
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    assert len(hook_events) == Engine.max_hook_redirects + 1
    assert hook_events[:3] == [("draft", "review"), ("review", "draft"), ("draft", "review")]


def test_after_hook_request_input_checkpoints_pending_input_and_resume_validates_input(tmp_path: Path):
    def after(ctx):
        assert ctx.route is not None
        assert ctx.route.tag == "done"
        assert ctx.route.target == "FINISH"
        assert ctx.route.handoff is None
        if ctx.input_response is None:
            return RequestInput(
                "Approve the change?",
                reason="A human approval is required.",
                best_supposition="approve",
                input_schema=_ApprovalInput,
            )
        ctx.state.approval = ctx.input_response.approval
        return None

    def _requestinputworkflow_on_ask(ctx):
        return Event('done')

    class RequestInputWorkflow(Workflow):
        class State(BaseModel):
            approval: str | None = None

        ask = PythonStep(name="ask", after=after, handler=_requestinputworkflow_on_ask)
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        RequestInputWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    paused = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == AWAIT_INPUT
    assert paused.last_event is None
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_input is not None
    assert paused.checkpoint.pending_input.question == "Approve the change?"
    assert paused.checkpoint.pending_input.source_hook == "after"
    assert paused.checkpoint.pending_input.input_schema is not None
    assert paused.checkpoint.step_states is not None
    assert paused.checkpoint.step_states["ask"]["last_route"] is None

    resumed = engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer='{"approval":"approved"}',
    )

    assert resumed.terminal == FINISH
    assert resumed.state.approval == "approved"


def test_resumed_request_input_is_consumed_before_later_steps(tmp_path: Path):
    def after_ask(ctx):
        assert ctx.route is not None
        assert ctx.route.tag == "next"
        assert ctx.route.target == "confirm"
        assert ctx.route.handoff is None
        if ctx.input_response is None:
            return RequestInput("Approve the draft?", input_schema=_ApprovalInput)
        ctx.state.first_approval = ctx.input_response.approval
        return None

    def after_confirm(ctx):
        assert ctx.route is not None
        assert ctx.route.tag == "done"
        assert ctx.route.target == "FINISH"
        assert ctx.route.handoff is None
        if ctx.input_response is None:
            return RequestInput("Confirm the publication?", input_schema=_ApprovalInput)
        ctx.state.second_approval = ctx.input_response.approval
        return None

    def _multistageapprovalworkflow_on_ask(ctx):
        return Event('next')

    def _multistageapprovalworkflow_on_confirm(ctx):
        assert ctx.input_response is None
        return Event('done')

    class MultiStageApprovalWorkflow(Workflow):
        class State(BaseModel):
            first_approval: str | None = None
            second_approval: str | None = None

        ask = PythonStep(name="ask", after=after_ask, handler=_multistageapprovalworkflow_on_ask)
        confirm = PythonStep(name="confirm", after=after_confirm, handler=_multistageapprovalworkflow_on_confirm)
        entry = ask
        transitions = {ask: {"next": confirm}, confirm: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        MultiStageApprovalWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    first_pause = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert first_pause.terminal == AWAIT_INPUT
    assert first_pause.checkpoint is not None
    assert first_pause.checkpoint.pending_input is not None
    first_pending_input_id = first_pause.checkpoint.pending_input.pending_input_id
    assert first_pause.checkpoint.pending_input.question == "Approve the draft?"

    second_pause = engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer='{"approval":"approved"}',
    )

    assert second_pause.terminal == AWAIT_INPUT
    assert second_pause.state.first_approval == "approved"
    assert second_pause.state.second_approval is None
    assert second_pause.checkpoint is not None
    assert second_pause.checkpoint.pending_input is not None
    assert second_pause.checkpoint.pending_input.question == "Confirm the publication?"
    assert second_pause.checkpoint.pending_input.source_step == "confirm"
    assert second_pause.checkpoint.pending_input.pending_input_id != first_pending_input_id
    assert second_pause.checkpoint.step_states is not None
    assert second_pause.checkpoint.step_states["ask"]["last_route"] == "next"
    assert second_pause.checkpoint.step_states["confirm"]["last_route"] is None


def test_resume_invalid_pending_input_preserves_checkpoint_and_failure_context(tmp_path: Path):
    def after(ctx):
        assert ctx.route is not None
        assert ctx.route.tag == "done"
        assert ctx.route.target == "FINISH"
        assert ctx.route.handoff is None
        if ctx.input_response is None:
            return RequestInput("Approve the change?", input_schema=_ApprovalInput)
        return None

    def _requestinputworkflow_on_ask(ctx):
        return Event('done')

    class RequestInputWorkflow(Workflow):
        class State(BaseModel):
            approval: str | None = None

        ask = PythonStep(name="ask", after=after, handler=_requestinputworkflow_on_ask)
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        RequestInputWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    paused = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.checkpoint is not None

    with pytest.raises(WorkflowExecutionError, match="resumed input did not satisfy"):
        engine.resume(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            answer='{"approval": 7}',
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.pending_input is not None
    assert checkpoint.pending_input.question == "Approve the change?"
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "resume_input_validation"
    assert checkpoint.failure_context["pending_input_id"] == checkpoint.pending_input.pending_input_id


def test_after_producer_goto_short_circuits_verifier(tmp_path: Path):
    step_finishes = []

    def after_producer(ctx):
        assert ctx.outcome == "draft copy"
        return Goto("publish", reason="Producer output is already approved.")

    def _producergotoworkflow_on_pair(ctx):
        return None

    def _producergotoworkflow_on_publish(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, 'publish']})
        return Event('done')

    class ProducerGotoWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            after_producer=after_producer,
        )
        publish = PythonStep(name="publish", handler=_producergotoworkflow_on_publish)
        entry = pair
        transitions = {
            pair: {"approved": FINISH},
            publish: {"done": FINISH},
        }
    ProducerGotoWorkflow.pair.after_verifier = ProducerGotoWorkflow.pair.after

    class _Recorder:
        def before_step(self, event):
            pass

        def after_step(self, event):
            step_finishes.append(event)

        def on_terminal(self, event):
            pass


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(producer_turns=["draft copy"])
    result = Engine(
        ProducerGotoWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_extension_factories=(lambda binding: _Recorder(),),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.history == ("pair", "publish")
    assert result.state.seen == ["publish"]
    assert [call.kind for call in provider.calls] == ["producer"]
    pair_finish = next(event for event in step_finishes if event.step_name == "pair")
    assert pair_finish.candidate_route is None
    assert pair_finish.final_route is None
    assert pair_finish.runtime_control == "goto"
    assert pair_finish.target_step == "publish"
    assert pair_finish.provider_attempted is True
    assert pair_finish.producer_attempted is True
    assert pair_finish.verifier_attempted is False
    assert pair_finish.source_hook == "after_producer"
    assert pair_finish.source_phase == "after_producer"


def test_after_producer_request_input_checkpoints_pending_input_before_verifier(tmp_path: Path):
    def after_producer(ctx):
        assert ctx.outcome == "draft copy"
        if ctx.input_response is None:
            return RequestInput(
                "Approve the producer draft?",
                reason="Verifier review requires a human gate.",
                input_schema=_ApprovalInput,
            )
        ctx.state.approval = ctx.input_response.approval
        return None

    def _producerrequestinputworkflow_on_pair(ctx):
        return None

    class ProducerRequestInputWorkflow(Workflow):
        class State(BaseModel):
            approval: str | None = None

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            after_producer=after_producer,
        )
        entry = pair
        transitions = {pair: {"approved": FINISH}}

    ProducerRequestInputWorkflow.pair.after_verifier = ProducerRequestInputWorkflow.pair.after


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    provider = ScriptedLLMProvider(
        producer_turns=["draft copy", "draft copy"],
        verifier_turns=[Outcome(raw_output="approved", tag="approved")],
    )
    engine = Engine(
        ProducerRequestInputWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    paused = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == AWAIT_INPUT
    assert paused.last_event is None
    assert paused.last_transition is not None
    assert paused.last_transition.runtime_control == "request_input"
    assert paused.last_transition.provider_attempted is True
    assert paused.last_transition.producer_attempted is True
    assert paused.last_transition.verifier_attempted is False
    assert paused.last_transition.source_hook == "after_producer"
    assert paused.last_transition.source_phase == "after_producer"
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_input is not None
    assert paused.last_transition.pending_input_id == paused.checkpoint.pending_input.pending_input_id
    assert paused.checkpoint.pending_input.question == "Approve the producer draft?"
    assert paused.checkpoint.pending_input.source_hook == "after_producer"
    assert [call.kind for call in provider.calls] == ["producer"]

    resumed = engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer='{"approval":"approved"}',
    )

    assert resumed.terminal == FINISH
    assert resumed.state.approval == "approved"
    assert [call.kind for call in provider.calls] == ["producer", "producer", "verifier"]


def test_on_taken_goto_skips_declared_route_target_and_emits_runtime_control(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    def on_draft_taken(ctx):
        return Goto("publish", reason="The publish path is pre-approved.")

    def _gotoworkflow_on_ask(ctx):
        return None

    def _gotoworkflow_on_review(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, 'review']})
        return Event('done')

    def _gotoworkflow_on_publish(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, 'publish']})
        return Event('done')

    class GotoWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        review = PythonStep(name="review", handler=_gotoworkflow_on_review)
        publish = PythonStep(name="publish", handler=_gotoworkflow_on_publish)
        entry = ask
        transitions = {
            ask: {
                "draft": Route.to(review, on_taken=on_draft_taken),
            },
            review: {"done": FINISH},
            publish: {"done": FINISH},
        }


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        GotoWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="draft")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.history == ("ask", "publish")
    assert result.state.seen == ["publish"]
    assert [
        payload
        for event_type, payload in runtime_events
        if event_type == "hook_runtime_control"
    ] == [
        {
            "step_name": "ask",
            "visit": 1,
            "step_execution_id": "ask:1",
            "control": "goto",
            "hook": "on_draft_taken",
            "source_phase": "on_taken",
            "target_step": "publish",
            "reason": "The publish path is pre-approved.",
        }
    ]


def test_on_taken_goto_handoff_reaches_target_provider_step(tmp_path: Path):
    def on_draft_taken(ctx):
        return Goto("publish", reason="Ship it.", handoff="Use the pre-approved publish checklist.")

    def _gotohandoffworkflow_on_ask(ctx):
        return None

    def _gotohandoffworkflow_on_publish(ctx):
        return None

    class GotoHandoffWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        publish = PromptStep(name="publish", producer="publish.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {
            ask: {"draft": Route.to(FINISH, on_taken=on_draft_taken)},
            publish: {"done": FINISH},
        }


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="ok", tag="draft"),
            Outcome(raw_output="published", tag="done"),
        ]
    )
    result = Engine(
        GotoHandoffWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert [call.step_name for call in provider.calls] == ["ask", "publish"]
    assert provider.calls[1].route_handoff == "Use the pre-approved publish checklist."


def test_invalid_goto_after_state_mutation_preserves_state_and_failure_context(tmp_path: Path):
    def after(ctx):
        assert ctx.route is not None
        assert ctx.route.tag == "done"
        assert ctx.route.target == "FINISH"
        assert ctx.route.handoff is None
        ctx.state.note = "mutated before invalid goto"
        return Goto("missing_step", reason="This target does not exist.")

    def _invalidgotoworkflow_on_ask(ctx):
        return Event('done')

    class InvalidGotoWorkflow(Workflow):
        class State(BaseModel):
            note: str = "initial"

        ask = PythonStep(name="ask", after=after, handler=_invalidgotoworkflow_on_ask)
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        InvalidGotoWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="declared workflow step"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.state.note == "mutated before invalid goto"
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "runtime_control_validation"
    assert checkpoint.failure_context["runtime_control"] == "goto"
    assert checkpoint.failure_context["source_hook"] == "after"
    assert checkpoint.failure_context["source_phase"] == "after"


def test_invalid_goto_after_session_mutation_preserves_checkpoint_session_bindings(tmp_path: Path):
    def after(ctx):
        ctx.set_global_session("hook-mutated-session")
        return Goto("missing_step", reason="This target does not exist.")

    def _invalidgotosessionworkflow_on_ask(ctx):
        return Event("done")

    class InvalidGotoSessionWorkflow(Workflow):
        class State(BaseModel):
            note: str = "initial"

        ask = PythonStep(name="ask", after=after, handler=_invalidgotosessionworkflow_on_ask)
        entry = ask
        transitions = {ask: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        InvalidGotoSessionWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="declared workflow step"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert any(binding.session_id == "hook-mutated-session" for binding in checkpoint.session_bindings.bindings)
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "runtime_control_validation"


def test_on_taken_goto_checkpoints_target_before_next_step_dispatch(tmp_path: Path):
    def on_draft_taken(ctx):
        return Goto("publish", reason="Dispatch directly.")

    class FailingBeforePublishExtension:
        def before_step(self, event):
            if event.step_name == "publish":
                raise RuntimeError("stop before publish dispatch")

        def after_step(self, event):
            pass

        def on_terminal(self, event):
            pass

    def _gotocheckpointworkflow_on_ask(ctx):
        return None

    def _gotocheckpointworkflow_on_publish(ctx):
        return None

    class GotoCheckpointWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        publish = PromptStep(name="publish", producer="publish.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {
            ask: {"draft": Route.to(FINISH, on_taken=on_draft_taken)},
            publish: {"done": FINISH},
        }


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    with pytest.raises(RuntimeError, match="stop before publish dispatch"):
        Engine(
            GotoCheckpointWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="draft")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=checkpoint_store,
            runtime_extension_factories=(lambda binding: FailingBeforePublishExtension(),),
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "publish"


def test_on_taken_fail_preserves_mutated_state_and_emits_runtime_control(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    def on_done_taken(ctx):
        ctx.state.status = "hook-mutated"
        return Fail("Stop after route review.")

    def _failworkflow_on_ask(ctx):
        return None

    class FailWorkflow(Workflow):
        class State(BaseModel):
            status: str = "draft"

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {
            ask: {
                "done": Route.to(FINISH, on_taken=on_done_taken),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        FailWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FAIL
    assert result.state.status == "hook-mutated"
    assert result.last_event is None
    assert result.checkpoint is not None
    assert result.checkpoint.state.status == "hook-mutated"
    assert [
        payload
        for event_type, payload in runtime_events
        if event_type == "hook_runtime_control"
    ] == [
        {
            "step_name": "ask",
            "visit": 1,
            "step_execution_id": "ask:1",
            "control": "fail",
            "hook": "on_done_taken",
            "source_phase": "on_taken",
            "reason": "Stop after route review.",
        }
    ]


def test_route_hook_failure_preserves_chained_state_in_checkpoint(tmp_path: Path):
    def after_ask(ctx):
        ctx.state.bucket = "rerouted"
        return "review"

    def on_taken(ctx):
        raise RuntimeError("route hook exploded")

    def _routehookrollbackworkflow_on_ask(ctx):
        return None

    class RouteHookRollbackWorkflow(Workflow):
        class State(BaseModel):
            bucket: str = "draft"

        ask = PromptStep(name="ask", producer="ask.md", after=after_ask, retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {
            ask: {
                "draft": Route.to(FINISH),
                "review": Route.to(FINISH, on_taken=on_taken),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    with pytest.raises(WorkflowExecutionError, match="route hook exploded"):
        Engine(
            RouteHookRollbackWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="draft")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=checkpoint_store,
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.state is not None
    assert checkpoint.state.bucket == "rerouted"


def test_hidden_routes_are_runtime_legal_but_excluded_from_provider_choices(tmp_path: Path):
    from autoloop.runtime.static_graph import workflow_topology_payload

    def after_ask(ctx):
        return "human_escalation"

    def on_hidden_taken(ctx):
        ctx.state.seen.append("hidden-route-taken")

    def _hiddenrouteworkflow_on_ask(ctx):
        return None

    class HiddenRouteWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        ask = PromptStep(name="ask", producer="ask.md", after=after_ask, retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {
            ask: {
                "done": Route.to(FINISH),
                "human_escalation": Route.to(
                    FINISH,
                    on_taken=on_hidden_taken,
                    provider_visible=False,
                ),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    result = Engine(
        HiddenRouteWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    topology = workflow_topology_payload(compile_workflow(HiddenRouteWorkflow))
    ask_topology = next(step for step in topology["steps"] if step["name"] == "ask")
    hidden_route = next(route for route in ask_topology["routes"] if route["tag"] == "human_escalation")

    assert "done" in provider.calls[0].available_routes
    assert "human_escalation" not in provider.calls[0].available_routes
    assert "done" in provider.calls[0].routes
    assert "human_escalation" not in provider.calls[0].routes
    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "human_escalation"
    assert result.state.seen == ["hidden-route-taken"]
    assert hidden_route["provider_visible"] is False


def test_after_hook_re_resolves_artifact_paths_before_on_taken(tmp_path: Path):
    seen_paths: list[Path] = []

    def after_ask(ctx):
        ctx.state.bucket = "published"

    def on_taken(ctx):
        seen_paths.append(ctx.artifacts.report.path)
        ctx.artifacts.report.write_text("published report\n")

    def _routehookartifactworkflow_on_ask(ctx):
        return None

    class RouteHookArtifactWorkflow(Workflow):
        class State(BaseModel):
            bucket: str = "draft"

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": Artifact.md("{workflow_folder}/{state.bucket}/report.md")},
            after=after_ask,
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "publish": Route.to(FINISH, required_writes=("report",), on_taken=on_taken),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        RouteHookArtifactWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="publish")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "publish"
    assert result.state.bucket == "published"
    workflow_root = task_folder / "wf_route_hook_artifact_workflow"
    assert seen_paths == [workflow_root / "published" / "report.md"]
    assert not (workflow_root / "draft" / "report.md").exists()
    assert (workflow_root / "published" / "report.md").read_text(encoding="utf-8") == "published report\n"


def test_explicit_empty_required_writes_override_skips_artifact_level_required_defaults(tmp_path: Path):
    def _optionalrouterequirementworkflow_on_ask(ctx):
        return None

    class OptionalRouteRequirementWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": Artifact.md("report.md", required=True)},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "done": Route.to(FINISH, required_writes=[]),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    result = Engine(
        OptionalRouteRequirementWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert provider.calls[0].routes["done"].required_writes == ()
    assert provider.calls[0].routes["done"].explicit_required_writes == ()
    assert provider.calls[0].route_required_writes == {
        "done": (),
        "question": (),
    }


def test_after_hook_state_mutation_re_resolves_artifact_paths_before_final_output_validation(tmp_path: Path):
    def after_ask(ctx):
        ctx.state = ctx.state.model_copy(update={"bucket": "published"})

    def _reresolvedartifactworkflow_on_ask(ctx):
        ctx.artifacts.report.write_text('draft report\n')
        return None

    class ReResolvedArtifactWorkflow(Workflow):
        class State(BaseModel):
            bucket: str = "draft"

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": Artifact.md("{workflow_folder}/{state.bucket}/report.md")},
            after=after_ask,
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "publish": Route.to(FINISH, required_writes=("report",)),
            }
        }

    ReResolvedArtifactWorkflow.ask.after = _chain_hooks(_reresolvedartifactworkflow_on_ask, ReResolvedArtifactWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    with pytest.raises(ProviderExecutionError, match=r"artifact validation failed.*published/report.md"):
        Engine(
            ReResolvedArtifactWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="publish")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=checkpoint_store,
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["path"].endswith("/published/report.md")


def test_workflow_step_honors_hooks_and_can_participate_in_verifier_rework_loops(tmp_path: Path):
    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    def before_launch(ctx):
        ctx.state = ctx.state.model_copy(update={"before_count": ctx.state.before_count + 1})

    def after_launch(ctx):
        ctx.state = ctx.state.model_copy(update={"after_count": ctx.state.after_count + 1})

    class ParentWorkflow(SimpleWorkflow):
        class State(BaseModel):
            before_count: int = 0
            after_count: int = 0

        launch = workflow_step(
            ChildWorkflow,
            message="Run child workflow",
            writes=[Json("child_result")],
            before=before_launch,
            after=after_launch,
        )
        review = produce_verify_step(
            producer_prompt="Review the child result.",
            verifier_prompt="Accept if the child result is usable.",
            reads=["child_result"],
            routes={"needs_rework": "launch", "accepted": FINISH},
        )

    task_folder, run_folder = _workspace(tmp_path)
    child_runs: list[str] = []

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_runs.append(message)
        child_run_root = task_folder / "child-runs" / f"child-{len(child_runs)}"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id=f"child-{len(child_runs)}",
            terminal=FINISH,
            status="success",
            last_event=Event("done"),
            output_metadata={},
            output_artifacts={},
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_root / "run",
            package_folder=child_run_root / "package",
            request_file=child_run_root / "request.md",
            run_meta_file=child_run_root / "run.json",
            events_file=child_run_root / "events.jsonl",
            checkpoint_file=child_run_root / "checkpoint.json",
            sessions_dir=child_run_root / "sessions",
            trace_file=child_run_root / "trace.jsonl",
            raw_dir=child_run_root / "raw",
            parent_file=child_run_root / "parent.json",
        )

    provider = ScriptedLLMProvider(
        producer_turns=["draft review", "draft review again"],
        verifier_turns=[
            Outcome(raw_output="redo", tag="needs_rework"),
            Outcome(raw_output="accept", tag="accepted"),
        ],
    )
    result = Engine(
        ParentWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_invoker=invoke_child,
    )

    child_result_path = task_folder / "wf_parent_workflow" / "launch" / "child_result.json"

    compiled = compile_workflow(ParentWorkflow)

    assert result.terminal == FINISH
    assert result.history == ("launch", "review", "launch", "review")
    assert result.state.before_count == 2
    assert result.state.after_count == 2
    assert child_runs == ["Run child workflow", "Run child workflow"]
    assert child_result_path.exists()
    assert compiled.steps["launch"].kind == "workflow"
    assert isinstance(compiled.steps["launch"].step, ChildWorkflowStep)
    assert compiled.steps["launch"].python_handler is None
    assert "on_launch" not in ParentWorkflow.__dict__


def test_produce_verify_step_sends_split_phase_contracts_without_implicitly_requiring_producer_writes(tmp_path: Path):
    def after_assess(ctx):
        ctx.artifacts.review_report.write_text("review report\n")
        return None

    class ReviewWorkflow(SimpleWorkflow):
        main = Session()
        reviewer = Session()

        assess = produce_verify_step(
            producer_prompt="Draft the assessment.",
            verifier_prompt="Review the assessment.",
            producer_writes=[Md("draft")],
            verifier_writes=[Md("review_report")],
            routes={
                "rejected": Route.to(FINISH, required_writes=["review_report"]),
            },
            session=main,
            verifier_session=reviewer,
            after_verifier=after_assess,
        )

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["draft text"],
        verifier_turns=[Outcome(raw_output="reject", tag="rejected")],
    )

    result = Engine(
        ReviewWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert provider.calls[0].kind == "producer"
    assert provider.calls[0].available_routes == ()
    assert [ref.name for ref in provider.calls[0].writable_artifacts] == ["draft"]
    assert provider.calls[0].required_artifacts == ()
    assert provider.calls[1].kind == "verifier"
    assert [ref.name for ref in provider.calls[1].writable_artifacts] == ["review_report"]
    assert provider.calls[1].required_artifacts == ()
    assert provider.calls[1].available_routes == ("rejected", "question")


def test_produce_verify_step_verifier_contract_preserves_explicit_empty_route_override(tmp_path: Path):
    class ReviewWorkflow(SimpleWorkflow):
        assess = produce_verify_step(
            producer_prompt="Draft the assessment.",
            verifier_prompt="Review the assessment.",
            producer_writes=[Md("draft", required=True)],
            verifier_writes=[Md("review_report", required=True)],
            retry=1,
            routes={
                "approved": Route.to(FINISH, required_writes=[]),
            },
        )

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.draft.write_text("draft text\n"),
                "draft text\n",
            )[1]
        ],
        verifier_turns=[
            lambda request: (
                request.artifacts.review_report.write_text("review report\n"),
                Outcome(raw_output="approve", tag="approved"),
            )[1]
        ],
    )

    result = Engine(
        ReviewWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert provider.calls[0].kind == "producer"
    assert provider.calls[0].route_required_writes == {}
    assert provider.calls[1].kind == "verifier"
    assert provider.calls[1].routes["approved"].required_writes == ()
    assert provider.calls[1].routes["approved"].explicit_required_writes == ()
    assert provider.calls[1].route_required_writes == {
        "approved": (),
        "question": (),
    }


def test_produce_verify_step_verifier_session_override_uses_distinct_verifier_session_slot(tmp_path: Path):
    def after_assess(ctx):
        return None

    class ReviewWorkflow(SimpleWorkflow):
        main = Session()
        reviewer = Session()

        assess = produce_verify_step(
            producer_prompt="Draft the assessment.",
            verifier_prompt="Review the assessment.",
            producer_writes=[Md("draft")],
            verifier_writes=[Md("review_report")],
            routes={
                "approved": Route.to(FINISH, required_writes=[]),
            },
            session=main,
            verifier_session=reviewer,
            retry=1,
            after_verifier=after_assess,
        )

    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    producer_sessions: list[tuple[str | None, str | None]] = []
    verifier_sessions: list[tuple[str | None, str | None]] = []

    def produce(request):
        producer_sessions.append(
            (request.session.ref_name if request.session is not None else None, request.session.session_id if request.session is not None else None)
        )
        assert request.session is not None
        assert request.session.ref_name == "main"
        return ProducerResponse(
            raw_output="draft text",
            session=SessionBinding(key=request.session.key, session_id="producer-main"),
        )

    def verify(request):
        verifier_sessions.append(
            (request.session.ref_name if request.session is not None else None, request.session.session_id if request.session is not None else None)
        )
        assert request.session is not None
        assert request.session.ref_name == "reviewer"
        assert request.session.session_id != "producer-main"
        return OutcomeResponse(
            outcome=Outcome(raw_output="approve", tag="approved"),
            session=SessionBinding(key=request.session.key, session_id="reviewer-verified"),
        )

    result = Engine(
        ReviewWorkflow,
        provider=ScriptedLLMProvider(producer_turns=[produce], verifier_turns=[verify]),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(producer_sessions) == 1
    assert len(verifier_sessions) == 1
    assert producer_sessions[0][0] == "main"
    assert verifier_sessions[0][0] == "reviewer"
    assert producer_sessions[0][1] != verifier_sessions[0][1]
    main_binding = session_store.get("main")
    reviewer_binding = session_store.get("reviewer")
    assert main_binding is not None
    assert reviewer_binding is not None
    assert main_binding.session_id == "producer-main"
    assert reviewer_binding.session_id == "reviewer-verified"


def test_produce_verify_step_verifier_requires_fail_before_verifier_when_declared(tmp_path: Path):
    def after_assess(ctx):
        return None

    class ReviewWorkflow(SimpleWorkflow):
        assess = produce_verify_step(
            producer_prompt="Draft the assessment.",
            verifier_prompt="Review the assessment.",
            producer_writes=[Md("draft")],
            verifier_requires=["draft"],
            verifier_writes=[Md("review_report")],
            routes={
                "approved": Route.to(FINISH, required_writes=["review_report"]),
            },
            retry=1,
            after_verifier=after_assess,
        )

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["draft text"],
        verifier_turns=[Outcome(raw_output="approve", tag="approved")],
    )

    with pytest.raises(MissingArtifactError, match=r"required artifact 'draft' does not exist for step 'assess'"):
        Engine(
            ReviewWorkflow,
            provider=provider,
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    assert [call.kind for call in provider.calls] == ["producer"]


def test_produce_verify_step_validates_selected_route_required_writes_per_route(tmp_path: Path):
    def after_assess(ctx):
        ctx.artifacts.review_report.write_text("review report\n")
        return None

    class ReviewWorkflow(SimpleWorkflow):
        assess = produce_verify_step(
            producer_prompt="Draft the assessment.",
            verifier_prompt="Review the assessment.",
            producer_writes=[Md("draft")],
            verifier_writes=[Md("review_report")],
            retry=1,
            routes={
                "approved": Route.to(FINISH, required_writes=["draft", "review_report"]),
                "rejected": Route.to(FINISH, required_writes=["review_report"]),
            },
            after_verifier=after_assess,
        )

    task_folder, run_folder = _workspace(tmp_path)

    rejected_result = Engine(
        ReviewWorkflow,
        provider=ScriptedLLMProvider(
            producer_turns=["draft text"],
            verifier_turns=[Outcome(raw_output="reject", tag="rejected")],
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-rejected",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert rejected_result.terminal == FINISH

    with pytest.raises(ProviderExecutionError, match=r"artifact validation failed.*route 'approved'.*draft"):
        Engine(
            ReviewWorkflow,
            provider=ScriptedLLMProvider(
                producer_turns=["draft text"],
                verifier_turns=[Outcome(raw_output="approve", tag="approved")],
            ),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-1",
            run_id="run-approved",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_llm_and_classify_step_replay_across_reruns(tmp_path: Path) -> None:
    class Summary(BaseModel):
        title: str

    class ReplayWorkflow(SimpleWorkflow):
        summary = llm.step(prompt="Summarize the request.", returns=Summary)
        verdict = classify.step(prompt="Classify {summary.value}.", choices=["solid", "weak"])

        @python_step(routes={"solid": FINISH, "weak": FAIL})
        def route(ctx):
            return ctx.values.verdict

    task_folder, run_folder = _workspace(tmp_path)

    first_provider = ScriptedLLMProvider(operation_turns=['{"title":"ready"}', "solid"])
    first_result = Engine(
        ReplayWorkflow,
        provider=first_provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-replay",
        run_id="run-replay",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert first_result.terminal == FINISH
    assert [call.kind for call in first_provider.calls] == ["operation", "operation"]

    replay_provider = ScriptedLLMProvider()
    replay_result = Engine(
        ReplayWorkflow,
        provider=replay_provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-replay",
        run_id="run-replay",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert replay_result.terminal == FINISH
    assert replay_provider.calls == []


def test_python_step_feedforward_helpers_accept_plain_string_prompts_with_rendered_provider(tmp_path: Path) -> None:
    class Summary(BaseModel):
        title: str

    class HelperWorkflow(SimpleWorkflow):
        class State(BaseModel):
            title: str = ""
            risk: str = ""

        @python_step
        def produce(ctx):
            summary = llm("Generate a summary.", returns=Summary)
            risk = classify("Classify risk.", choices=["low", "medium", "high"])
            ctx.state = ctx.state.model_copy(update={"title": summary.title, "risk": risk})
            return None

    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub(raw_texts=['{"title":"Rendered summary"}', "medium"])

    result = Engine(
        HelperWorkflow,
        provider=_rendered_provider_with_operation_executor(transport),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-helper-rendered",
        run_id="run-helper-rendered",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.title == "Rendered summary"
    assert result.state.risk == "medium"
    assert [turn.turn_kind for turn in transport.turns] == ["operation", "operation"]
    assert "Generate a summary." in transport.turns[0].prompt_text
    assert "Classify risk." in transport.turns[1].prompt_text


def test_ctx_prompt_bindings_render_in_provider_and_operation_prompts(tmp_path: Path) -> None:
    class PromptBindingWorkflow(SimpleWorkflow):
        class Input(BaseModel):
            topic: str

        class Params(BaseModel):
            mode: str = "brief"

        class State(BaseModel):
            status: str = "draft"

        summary = step(
            "Message={ctx.message}; Topic={ctx.input.topic}; Mode={ctx.params.mode}; Status={ctx.state.status}",
            routes={"done": "review"},
        )
        review = produce_verify_step(
            producer_prompt="Produce {ctx.message}; topic={ctx.input.topic}; mode={ctx.params.mode}; status={ctx.state.status}",
            verifier_prompt="Verify {ctx.message}; topic={ctx.input.topic}; mode={ctx.params.mode}; status={ctx.state.status}",
            routes={"approved": "risk"},
        )
        risk = llm.step(
            prompt="Risk for {ctx.message}; topic={ctx.input.topic}; mode={ctx.params.mode}; status={ctx.state.status}",
            returns=str,
        )
        kind = classify.step(
            prompt="Classify {ctx.message} for {ctx.input.topic}",
            choices=["bug", "feature"],
        )

        @python_step(routes={"done": FINISH})
        def finish(ctx):
            assert ctx.values.risk == "medium"
            assert ctx.values.kind == "feature"
            return "done"

    task_folder, run_folder = _workspace(tmp_path)
    (run_folder / "request.md").write_text("Ship the release safely.\n", encoding="utf-8")
    captured: dict[str, object] = {"operations": []}
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                captured.__setitem__("step", request.prompt.text),
                Outcome(raw_output="done", tag="done"),
            )[1]
        ],
        producer_turns=[
            lambda request: (
                captured.__setitem__("producer", request.producer_prompt.text),
                "producer draft",
            )[1]
        ],
        verifier_turns=[
            lambda request: (
                captured.__setitem__("verifier", request.verifier_prompt.text),
                Outcome(raw_output="approved", tag="approved"),
            )[1]
        ],
        operation_turns=[
            lambda request: (
                cast(list[str], captured["operations"]).append(request.prompt.text),
                "medium",
            )[1],
            lambda request: (
                cast(list[str], captured["operations"]).append(request.prompt.text),
                "feature",
            )[1],
        ],
    )

    result = Engine(
        PromptBindingWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-ctx-prompts",
        run_id="run-ctx-prompts",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        params=PromptBindingWorkflow.Params(mode="brief"),
        workflow_input=PromptBindingWorkflow.Input(topic="release"),
    )

    assert result.terminal == FINISH
    assert captured["step"] == "Message=Ship the release safely.; Topic=release; Mode=brief; Status=draft"
    assert captured["producer"] == "Produce Ship the release safely.; topic=release; mode=brief; status=draft"
    assert captured["verifier"] == "Verify Ship the release safely.; topic=release; mode=brief; status=draft"
    operation_prompts = cast(list[str], captured["operations"])
    assert operation_prompts == [
        "Risk for Ship the release safely.; topic=release; mode=brief; status=draft",
        "Classify Ship the release safely. for release",
    ]
    rendered_prompts = [
        cast(str, captured["step"]),
        cast(str, captured["producer"]),
        cast(str, captured["verifier"]),
        *operation_prompts,
    ]
    assert all("{ctx." not in text for text in rendered_prompts)


def test_workflow_step_message_renders_ctx_bindings_before_child_invocation(tmp_path: Path) -> None:
    class ChildWorkflow(SimpleWorkflow):
        note = step("Child note.")

    class ParentWorkflow(SimpleWorkflow):
        class Input(BaseModel):
            topic: str

        launch = workflow_step(
            ChildWorkflow,
            message="Parent request: {ctx.message}; topic={ctx.input.topic}",
            input={"topic": "structured-topic"},
            routes={"done": FINISH},
        )

    task_folder, run_folder = _workspace(tmp_path)
    (run_folder / "request.md").write_text("Natural-language request\n", encoding="utf-8")
    seen: dict[str, object] = {}

    def invoke_child(workflow, *, message, parameters=None, input=None):
        seen["workflow"] = workflow
        seen["message"] = message
        seen["input"] = input
        child_run_root = task_folder / "child-runs" / "ctx-child"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id="child-ctx",
            terminal=FINISH,
            status="success",
            last_event=Event("done"),
            output_metadata={},
            output_artifacts={},
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_root / "run",
            package_folder=child_run_root / "package",
            request_file=child_run_root / "request.md",
            run_meta_file=child_run_root / "run.json",
            events_file=child_run_root / "events.jsonl",
            checkpoint_file=child_run_root / "checkpoint.json",
            sessions_dir=child_run_root / "sessions",
            trace_file=child_run_root / "trace.jsonl",
            raw_dir=child_run_root / "raw",
            parent_file=child_run_root / "parent.json",
        )

    result = Engine(
        ParentWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-ctx-child",
        run_id="run-ctx-child",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_input=ParentWorkflow.Input(topic="alpha"),
        workflow_invoker=invoke_child,
    )

    assert result.terminal == FINISH
    assert seen["workflow"] is ChildWorkflow
    assert seen["message"] == "Parent request: Natural-language request; topic=alpha"
    assert seen["input"] == {"topic": "structured-topic"}
    assert seen["message"] != "structured-topic"


def test_workflow_step_message_invalid_ctx_field_raises_workflow_execution_error(tmp_path: Path) -> None:
    class ChildWorkflow(SimpleWorkflow):
        note = step("Child note.")

    class ParentWorkflow(SimpleWorkflow):
        class Input(BaseModel):
            topic: str

        launch = workflow_step(
            ChildWorkflow,
            message="{ctx.input.missing}",
            routes={"done": FINISH},
        )

    task_folder, run_folder = _workspace(tmp_path)
    (run_folder / "request.md").write_text("Natural-language request\n", encoding="utf-8")

    def invoke_child(workflow, *, message, parameters=None, input=None):
        raise AssertionError("child invoker should not run when workflow-step message rendering fails")

    with pytest.raises(
        WorkflowExecutionError,
        match=r"workflow step 'launch' message placeholder \{ctx\.input\.missing\} references unknown runtime field 'missing'",
    ):
        Engine(
            ParentWorkflow,
            provider=ScriptedLLMProvider(),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-ctx-child-invalid",
            run_id="run-ctx-child-invalid",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            workflow_input=ParentWorkflow.Input(topic="alpha"),
            workflow_invoker=invoke_child,
        )


def test_python_step_feedforward_helpers_require_operation_executor_for_rendered_provider_in_active_loop(
    tmp_path: Path,
) -> None:
    class Summary(BaseModel):
        title: str

    class HelperWorkflow(SimpleWorkflow):
        class State(BaseModel):
            title: str = ""

        @python_step
        def produce(ctx):
            summary = llm("Generate a summary.", returns=Summary)
            ctx.state = ctx.state.model_copy(update={"title": summary.title})
            return None

    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub(raw_text='{"title":"Rendered summary"}')

    with pytest.raises(RuntimeError, match="requires an explicit operation_executor"):
        Engine(
            HelperWorkflow,
            provider=RenderedLLMProvider(transport),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-helper-rendered-missing-executor",
            run_id="run-helper-rendered-missing-executor",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    assert transport.turns == []


def test_operation_replay_fingerprint_mismatch_warns_and_reuses_cached_value_by_default(tmp_path: Path) -> None:
    class FirstWorkflow(SimpleWorkflow):
        name = "operation_replay"
        summary = llm.step(prompt="Summarize version one.", returns=str)

    class SecondWorkflow(SimpleWorkflow):
        name = "operation_replay"
        summary = llm.step(prompt="Summarize version two.", returns=str)

    task_folder, run_folder = _workspace(tmp_path)

    Engine(
        FirstWorkflow,
        provider=ScriptedLLMProvider(operation_turns=["first result"]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-mismatch",
        run_id="run-mismatch",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    runtime_events: list[tuple[str, dict[str, object]]] = []
    result = Engine(
        SecondWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-mismatch",
        run_id="run-mismatch",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert runtime_events[-1][0] == "operation_replay_fingerprint_mismatch"
    assert runtime_events[-1][1]["behavior"] == "warn"


def test_operation_replay_fingerprint_mismatch_fails_in_strict_mode(tmp_path: Path) -> None:
    class FirstWorkflow(SimpleWorkflow):
        name = "operation_replay"
        summary = llm.step(prompt="Summarize version one.", returns=str)

    class SecondWorkflow(SimpleWorkflow):
        name = "operation_replay"
        summary = llm.step(prompt="Summarize version two.", returns=str)

    task_folder, run_folder = _workspace(tmp_path)

    Engine(
        FirstWorkflow,
        provider=ScriptedLLMProvider(operation_turns=["first result"]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-mismatch-strict",
        run_id="run-mismatch-strict",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    with pytest.raises(ProviderExecutionError, match="operation replay fingerprint mismatch"):
        Engine(
            SecondWorkflow,
            provider=ScriptedLLMProvider(),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
            operation_replay_mismatch_behavior="fail",
        ).run(
            task_id="task-mismatch-strict",
            run_id="run-mismatch-strict",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_operation_replay_fingerprint_includes_provider_configuration(tmp_path: Path) -> None:
    class ConfiguredWorkflow(SimpleWorkflow):
        name = "operation_replay"
        summary = llm.step(prompt="Summarize version one.", returns=str)

    task_folder, run_folder = _workspace(tmp_path)

    Engine(
        ConfiguredWorkflow,
        provider=_rendered_provider_with_operation_executor(_ConfigurableRenderedTransport(model="gpt-5.5")),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-provider-mismatch",
        run_id="run-provider-mismatch",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    runtime_events: list[tuple[str, dict[str, object]]] = []
    result = Engine(
        ConfiguredWorkflow,
        provider=_rendered_provider_with_operation_executor(_ConfigurableRenderedTransport(model="gpt-5.4")),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-provider-mismatch",
        run_id="run-provider-mismatch",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert runtime_events[-1][0] == "operation_replay_fingerprint_mismatch"
    assert runtime_events[-1][1]["behavior"] == "warn"


@pytest.mark.parametrize(
    ("payload", "expected_attempts"),
    [
        ({"records": {"legacy": {"value": "stale"}}, "attempts": ["first"]}, ["first"]),
        (
            {
                "schema": "autoloop.operation_replay/v1",
                "records": {"legacy": {"value": "stale"}},
                "attempts": ["first", "second"],
            },
            ["first", "second"],
        ),
    ],
)
def test_operation_replay_store_migrates_only_schemaless_and_v1_payloads(
    tmp_path: Path,
    payload: dict[str, object],
    expected_attempts: list[str],
) -> None:
    replay_path = tmp_path / "operation_replay.json"
    replay_path.write_text(json.dumps(payload), encoding="utf-8")

    replay_store = _load_replay_store(replay_path)

    assert replay_store == {
        "schema": OPERATION_REPLAY_SCHEMA,
        "records": {},
        "attempts": expected_attempts,
    }


def test_operation_replay_store_rejects_unsupported_schema_versions(tmp_path: Path) -> None:
    replay_path = tmp_path / "operation_replay.json"
    replay_path.write_text(
        json.dumps(
            {
                "schema": "autoloop.operation_replay/v3",
                "records": {"legacy": {"value": "stale"}},
                "attempts": ["first"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="uses unsupported schema 'autoloop.operation_replay/v3'"):
        _load_replay_store(replay_path)


def test_inline_operation_provider_override_participates_in_replay_fingerprint(tmp_path: Path) -> None:
    first_override = _rendered_provider_with_operation_executor(
        _ConfigurableRenderedTransport(model="gpt-5.5", raw_text="first override")
    )
    second_override = _rendered_provider_with_operation_executor(
        _ConfigurableRenderedTransport(model="gpt-5.4", raw_text="second override")
    )
    override_provider_ref = {"provider": first_override}

    class OverrideWorkflow(SimpleWorkflow):
        name = "operation_replay_override"

        class State(BaseModel):
            summary: str = ""

        @python_step
        def produce(ctx):
            summary = llm("Summarize the override provider.", provider=override_provider_ref["provider"])
            ctx.state = ctx.state.model_copy(update={"summary": summary})
            return None

    task_folder, run_folder = _workspace(tmp_path)

    Engine(
        OverrideWorkflow,
        provider=_rendered_provider_with_operation_executor(_ConfigurableRenderedTransport(model="ambient")),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-provider-override-mismatch",
        run_id="run-provider-override-mismatch",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    override_provider_ref["provider"] = second_override
    runtime_events: list[tuple[str, dict[str, object]]] = []
    result = Engine(
        OverrideWorkflow,
        provider=_rendered_provider_with_operation_executor(_ConfigurableRenderedTransport(model="ambient")),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-provider-override-mismatch",
        run_id="run-provider-override-mismatch",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.summary == "first override"
    assert runtime_events[-1][0] == "operation_replay_fingerprint_mismatch"
    assert runtime_events[-1][1]["behavior"] == "warn"
    assert len(first_override._transport.turns) == 1
    assert len(second_override._transport.turns) == 0


def test_resume_restores_recorded_values_for_following_python_step(tmp_path: Path) -> None:
    class Summary(BaseModel):
        title: str

    class ResumeWorkflow(SimpleWorkflow):
        class State(BaseModel):
            published_title: str = ""

        summary = llm.step(prompt="Summarize the request.", returns=Summary)

        @python_step(routes={"question": AWAIT_INPUT, "done": "publish"})
        def gate(ctx):
            if ctx.answer is None:
                return Event("question", question="Proceed?")
            return "done"

        @python_step
        def publish(ctx):
            ctx.state = ctx.state.model_copy(update={"published_title": ctx.values.summary.title})
            return None

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()

    paused_result = Engine(
        ResumeWorkflow,
        provider=ScriptedLLMProvider(operation_turns=['{"title":"Ready to publish"}']),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).run(
        task_id="task-resume-values",
        run_id="run-resume-values",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused_result.terminal == AWAIT_INPUT
    assert paused_result.checkpoint is not None
    assert paused_result.checkpoint.values == {"summary": {"title": "Ready to publish"}}

    resumed_result = Engine(
        ResumeWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).resume(
        task_id="task-resume-values",
        run_id="run-resume-values",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer="yes",
    )

    assert resumed_result.terminal == FINISH
    assert resumed_result.state.published_title == "Ready to publish"


def test_after_hook_effects_complete_and_advance_persist_status_and_exhaust(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    def after_assess(ctx):
        return Effects.complete_and_advance(exhausted="done")

    class EffectsWorkflow(Workflow):
        board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        assess = PromptStep(name="assess", producer="assess.md", scope=gates, after=after_assess)
        entry = assess
        transitions = {
            assess: {
                "accepted": assess,
                "done": FINISH,
            }
        }

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        json.dumps(
            {
                "gates": [
                    {"gate_id": "alpha", "title": "Alpha", "status": "queued"},
                    {"gate_id": "beta", "title": "Beta", "status": "queued"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = Engine(
        EffectsWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                Outcome(raw_output="ok-1", tag="accepted"),
                Outcome(raw_output="ok-2", tag="accepted"),
            ]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-effects",
        run_id="run-effects",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    payload = json.loads((task_folder / "gates.json").read_text(encoding="utf-8"))

    assert result.terminal == FINISH
    assert result.history == ("assess", "assess")
    assert [item["status"] for item in payload["gates"]] == ["completed", "completed"]
    assert [event_type for event_type, _ in runtime_events].count("worklist_status_set") == 2
    assert runtime_events[-1][0] == "worklist_exhausted"


def test_python_step_effect_refresh_reloads_worklist_source(tmp_path: Path):
    def _refreshworkflow_on_start(ctx):
        assert ctx.current("gate") is not None
        assert ctx.current("gate").status == "queued"
        payload = ctx.read_json(ctx.task_folder / "gates.json")
        assert isinstance(payload, dict)
        payload["gates"][0]["status"] = "ready"
        ctx.write_json(ctx.task_folder / "gates.json", payload)
        return Effects(
            worklists=(WorklistEffect(worklist="gate", refresh=True),),
            event="done",
        )

    def _refreshworkflow_on_finish(ctx):
        assert ctx.current("gate") is not None
        assert ctx.current("gate").status == "ready"
        return Event("done")

    class RefreshWorkflow(Workflow):
        board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        start = PythonStep(name="start", handler=_refreshworkflow_on_start)
        finish = PythonStep(name="finish", handler=_refreshworkflow_on_finish)
        entry = start
        transitions = {
            start: {"done": finish},
            finish: {"done": FINISH},
        }

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        '{"gates":[{"gate_id":"alpha","title":"Alpha","status":"queued"}]}\n',
        encoding="utf-8",
    )

    result = Engine(
        RefreshWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-refresh",
        run_id="run-refresh",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.history == ("start", "finish")


def test_python_step_may_return_direct_worklist_effect(tmp_path: Path):
    def _directeffectworkflow_on_assess(ctx):
        assert ctx.current("gate") is not None
        return WorklistEffect.complete_and_advance(worklist="gate", exhausted="done")

    class DirectEffectWorkflow(Workflow):
        board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        assess = PythonStep(name="assess", handler=_directeffectworkflow_on_assess)
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        '{"gates":[{"gate_id":"alpha","title":"Alpha","status":"queued"}]}\n',
        encoding="utf-8",
    )

    result = Engine(
        DirectEffectWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-direct-effect",
        run_id="run-direct-effect",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    payload = json.loads((task_folder / "gates.json").read_text(encoding="utf-8"))

    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "done"
    assert payload["gates"][0]["status"] == "completed"


def test_route_hook_may_return_direct_worklist_effect_for_active_scoped_worklist(tmp_path: Path):
    def _complete_current_item(_ctx):
        return WorklistEffect.complete_and_advance(exhausted="done")

    class DirectRouteHookEffectWorkflow(Workflow):
        board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        assess = PromptStep(name="assess", producer="assess.md", scope=gates)
        entry = assess
        transitions = {assess: {"done": Route.to(FINISH, on_taken=_complete_current_item)}}

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        '{"gates":[{"gate_id":"alpha","title":"Alpha","status":"queued"}]}\n',
        encoding="utf-8",
    )

    result = Engine(
        DirectRouteHookEffectWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-direct-route-hook-effect",
        run_id="run-direct-route-hook-effect",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    payload = json.loads((task_folder / "gates.json").read_text(encoding="utf-8"))

    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "done"
    assert payload["gates"][0]["status"] == "completed"


def test_effect_without_active_worklist_fails_clearly(tmp_path: Path):
    def _invalideffectsworkflow_on_start(ctx):
        return Effects.advance()

    class InvalidEffectsWorkflow(Workflow):
        start = PythonStep(name="start", handler=_invalideffectsworkflow_on_start)
        entry = start
        transitions = {start: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)

    with pytest.raises(WorkflowExecutionError, match="without an active worklist"):
        Engine(
            InvalidEffectsWorkflow,
            provider=ScriptedLLMProvider(),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-invalid-effects",
            run_id="run-invalid-effects",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_python_step_effect_then_routes_without_worklist_mutation(tmp_path: Path):
    def _theneffectsworkflow_on_start(ctx):
        return Effects.then("next")

    def _theneffectsworkflow_on_finish(ctx):
        return Event("done")

    class ThenEffectsWorkflow(Workflow):
        start = PythonStep(name="start", handler=_theneffectsworkflow_on_start)
        finish = PythonStep(name="finish", handler=_theneffectsworkflow_on_finish)
        entry = start
        transitions = {
            start: {"next": finish},
            finish: {"done": FINISH},
        }

    task_folder, run_folder = _workspace(tmp_path)

    result = Engine(
        ThenEffectsWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-then-effects",
        run_id="run-then-effects",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.history == ("start", "finish")
    assert result.last_event is not None
    assert result.last_event.tag == "done"


def test_after_hook_effect_event_takes_precedence_over_exhausted_route(tmp_path: Path):
    def after_assess(_ctx):
        return Effects(
            worklists=(WorklistEffect.complete_and_advance(exhausted="done"),),
            event="publish",
        )

    def finish_handler(_ctx):
        return Event("done")

    class EffectsPrecedenceWorkflow(Workflow):
        board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        assess = PromptStep(name="assess", producer="assess.md", scope=gates, after=after_assess)
        publish = PythonStep(name="publish", handler=finish_handler)
        entry = assess
        transitions = {
            assess: {"accepted": FINISH, "publish": publish, "done": FINISH},
            publish: {"done": FINISH},
        }

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        '{"gates":[{"gate_id":"alpha","title":"Alpha","status":"queued"}]}\n',
        encoding="utf-8",
    )

    result = Engine(
        EffectsPrecedenceWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="accepted")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-effects-precedence",
        run_id="run-effects-precedence",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    payload = json.loads((task_folder / "gates.json").read_text(encoding="utf-8"))

    assert result.terminal == FINISH
    assert result.history == ("assess", "publish")
    assert result.last_event is not None
    assert result.last_event.tag == "done"
    assert payload["gates"][0]["status"] == "completed"


@pytest.mark.parametrize(
    ("control_kind", "expected_terminal", "expected_history", "expected_last_tag"),
    [
        ("request_input", AWAIT_INPUT, ("assess",), None),
        ("goto", FINISH, ("assess", "publish"), "done"),
        ("fail", FAIL, ("assess",), "failed"),
    ],
)
def test_after_hook_effect_runtime_controls_match_direct_controls(
    tmp_path: Path,
    control_kind,
    expected_terminal,
    expected_history,
    expected_last_tag,
):
    def make_control():
        if control_kind == "request_input":
            return RequestInput("Need approval?", reason="Await operator input.")
        if control_kind == "goto":
            return Goto("publish", reason="Skip directly to publication.")
        if control_kind == "fail":
            return Fail("Stop after capturing the gate status.")
        raise AssertionError(f"unexpected control kind {control_kind!r}")

    def run_variant(*, use_effect: bool):
        def publish_handler(_ctx):
            return Event("done")

        def after_assess(ctx):
            ctx.current_worklist.set_current_status("completed")
            return make_control()

        def after_assess_effect(_ctx):
            return Effects(
                worklists=(WorklistEffect.complete_current(),),
                event=make_control(),
            )

        after_hook = after_assess_effect if use_effect else after_assess
        after_hook.__name__ = "control_hook"

        class ControlWorkflow(Workflow):
            board = Artifact.json("{task_folder}/gates.json", required=True)
            gates = Worklist.from_artifact(
                name="gate",
                artifact=board,
                collection="gates",
                item_id="gate_id",
                title="title",
                status="status",
            )
            assess = PromptStep(name="assess", producer="assess.md", scope=gates, after=after_hook)
            publish = PythonStep(name="publish", handler=publish_handler)
            entry = assess
            transitions = {
                assess: {"accepted": FINISH},
                publish: {"done": FINISH},
            }

        ControlWorkflow.__name__ = f"ControlWorkflow_{control_kind}_{'effect' if use_effect else 'direct'}"
        ControlWorkflow.__qualname__ = ControlWorkflow.__name__

        variant_root = tmp_path / ("effect" if use_effect else "direct")
        variant_root.mkdir()
        task_folder, run_folder = _workspace(variant_root)
        (task_folder / "gates.json").write_text(
            '{"gates":[{"gate_id":"alpha","title":"Alpha","status":"queued"}]}\n',
            encoding="utf-8",
        )

        result = Engine(
            ControlWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="accepted")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-effect-controls",
            run_id="run-effect-controls",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

        payload = json.loads((task_folder / "gates.json").read_text(encoding="utf-8"))
        return result, payload

    direct_result, direct_payload = run_variant(use_effect=False)
    effect_result, effect_payload = run_variant(use_effect=True)

    assert direct_result.terminal == expected_terminal
    assert effect_result.terminal == expected_terminal
    assert direct_result.history == expected_history
    assert effect_result.history == expected_history
    assert direct_payload["gates"][0]["status"] == "completed"
    assert effect_payload["gates"][0]["status"] == "completed"

    if expected_terminal == AWAIT_INPUT:
        assert direct_result.last_transition.source_hook == "control_hook"
        assert effect_result.last_transition.source_hook == "control_hook"
        assert direct_result.last_transition.source_phase == "after"
        assert effect_result.last_transition.source_phase == "after"
        assert direct_result.checkpoint is not None
        assert effect_result.checkpoint is not None
        assert direct_result.checkpoint.pending_input is not None
        assert effect_result.checkpoint.pending_input is not None
        assert direct_result.checkpoint.pending_input.question == "Need approval?"
        assert effect_result.checkpoint.pending_input.question == "Need approval?"
    elif control_kind == "goto":
        assert direct_result.last_transition.source_hook == "handler"
        assert effect_result.last_transition.source_hook == "handler"
        assert direct_result.last_transition.source_phase == "python_step"
        assert effect_result.last_transition.source_phase == "python_step"
        assert direct_result.checkpoint is None
        assert effect_result.checkpoint is None
    elif control_kind == "fail":
        assert direct_result.last_transition.source_hook == "control_hook"
        assert effect_result.last_transition.source_hook == "control_hook"
        assert direct_result.last_transition.source_phase == "after"
        assert effect_result.last_transition.source_phase == "after"
        assert direct_result.last_transition.runtime_control == "fail"
        assert effect_result.last_transition.runtime_control == "fail"
        assert direct_result.last_event is None
        assert effect_result.last_event is None
    else:
        assert direct_result.last_event is not None
        assert effect_result.last_event is not None
        assert direct_result.last_event.tag == expected_last_tag
        assert effect_result.last_event.tag == expected_last_tag


def test_validation_step_valid_routes_to_default_done_and_emits_runtime_event(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    class ValidateWorkflow(SimpleWorkflow):
        draft = Artifact.md("{task_folder}/draft.md", required=True, name="draft")
        feedback = Md("validation_feedback")

        @validation_step(name="validate", feedback=feedback, requires=[draft])
        def validate(ctx):
            return ValidationResult.valid()

        entry = validate

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "draft.md").write_text("ready\n", encoding="utf-8")

    compiled = compile_workflow(ValidateWorkflow)
    result = Engine(
        compiled,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-validate-valid",
        run_id="run-validate-valid",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert compiled.steps["validate"].writes == ("validate.validation_feedback",)
    assert runtime_events[-1][0] == "validation_step_passed"
    assert runtime_events[-1][1]["feedback_artifact"] == str(
        task_folder / "wf_validate_workflow" / "validate" / "validation_feedback.md"
    )


def test_validation_step_invalid_writes_feedback_and_routes_repair(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    class ValidateWorkflow(SimpleWorkflow):
        draft = Artifact.md("{task_folder}/draft.md", required=True, name="draft")
        feedback = Md("validation_feedback")

        @validation_step(
            name="validate",
            feedback=feedback,
            requires=[draft],
            routes={"repair": FINISH},
        )
        def validate(ctx):
            return ValidationResult.invalid(
                "Fix the draft.",
                details=("Add a summary.", "Resolve open TODOs."),
            )

        entry = validate

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "draft.md").write_text("draft\n", encoding="utf-8")

    result = Engine(
        ValidateWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-validate-invalid",
        run_id="run-validate-invalid",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    feedback_path = task_folder / "wf_validate_workflow" / "validate" / "validation_feedback.md"

    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "repair"
    assert result.last_event.reason == "Fix the draft."
    assert result.last_event.handoff == f"Review feedback artifact: {feedback_path}"
    assert feedback_path.read_text(encoding="utf-8") == (
        "# Validation Feedback\n\n"
        "Fix the draft.\n\n"
        "## Details\n"
        "- Add a summary.\n"
        "- Resolve open TODOs.\n"
    )
    assert runtime_events[-1][0] == "validation_step_failed_repairable"
    assert runtime_events[-1][1]["feedback_artifact"] == str(feedback_path)


def test_validation_step_exception_uses_failed_route_when_configured(tmp_path: Path):
    class ValidateWorkflow(SimpleWorkflow):
        draft = Artifact.md("{task_folder}/draft.md", required=True, name="draft")
        feedback = Md("validation_feedback")

        @validation_step(name="validate", feedback=feedback, requires=[draft], failed=FAIL)
        def validate(ctx):
            raise RuntimeError("validator exploded")

        entry = validate

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "draft.md").write_text("draft\n", encoding="utf-8")

    result = Engine(
        ValidateWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-validate-exception",
        run_id="run-validate-exception",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FAIL
    assert result.last_event is not None
    assert result.last_event.tag == "failed"
    assert result.last_event.reason == "RuntimeError: validator exploded"
