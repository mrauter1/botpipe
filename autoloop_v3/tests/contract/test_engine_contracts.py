from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from autoloop_v3.workflow import (
    Artifact,
    Engine,
    GLOBAL,
    LLMStep,
    PairStep,
    Session,
    SystemStep,
    SUCCESS,
    Workflow,
)
from autoloop_v3.workflow.compiler import compile_workflow
from autoloop_v3.workflow.errors import MissingArtifactError, WorkflowExecutionError
from autoloop_v3.workflow.observers import ProviderTurnEvent, StepCompletedEvent, TerminalEvent
from autoloop_v3.workflow.primitives import Event, Outcome
from autoloop_v3.workflow.providers.fake import ScriptedLLMProvider
from autoloop_v3.workflow.providers.models import OutcomeResponse, ProducerResponse
from autoloop_v3.workflow.stores import InMemoryCheckpointStore, InMemorySessionStore
from autoloop_v3.workflow.stores.protocols import SessionBinding

PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()
    return task_folder, run_folder


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[object] = []

    def record(self, event: object) -> None:
        self.events.append(event)


def test_observer_core_modules_remain_autoloop_agnostic():
    engine_text = (PACKAGE_ROOT / "workflow" / "engine.py").read_text(encoding="utf-8")
    observer_text = (PACKAGE_ROOT / "workflow" / "observers.py").read_text(encoding="utf-8")
    corpus = f"{engine_text}\n{observer_text}"

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
    class PairWorkflow(Workflow):
        class State(BaseModel):
            draft_text: str = ""

        main = Session()
        request = Artifact("{task_folder}/request.txt")
        draft = Artifact("{run_folder}/draft.txt")
        raw_log = Artifact("{run_folder}/pair.log")
        pair = PairStep(
            name="pair",
            session=main,
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            requires=[request],
            produces={"draft": draft},
            log_artifacts=[raw_log],
        )
        finish = SystemStep(name="finish")
        entry = pair
        transitions = {pair: {"pair_ok": finish}, finish: {"done": SUCCESS}}

        def on_start(self, ctx):
            ctx.open_session(self.main)

        @staticmethod
        def on_pair(state: State, outcome: Outcome, artifacts):
            return state.model_copy(update={"draft_text": artifacts.draft.read_text()})

        @staticmethod
        def on_finish(state: State, ctx):
            return state, Event("done")

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
    )

    assert result.terminal == SUCCESS
    assert result.state.draft_text == "artifact draft"
    assert (run_folder / "pair.log").read_text(encoding="utf-8") == "producer raw\n"
    assert result.history == ("pair", "finish")


def test_pair_and_llm_handlers_remain_optional(tmp_path: Path):
    class OptionalHandlerWorkflow(Workflow):
        class State(BaseModel):
            finished: bool = False

        main = Session()
        request = Artifact("{task_folder}/request.txt")
        pair = PairStep(name="pair", producer="pair/producer.md", verifier="pair/verifier.md", requires=[request], session=main)
        ask = LLMStep(name="ask", producer="ask.md", session=main)
        finish = SystemStep(name="finish")
        entry = pair
        transitions = {pair: {"pair_ok": ask}, ask: {"done": finish}, finish: {"complete": SUCCESS}}

        def on_start(self, ctx):
            ctx.open_session(self.main)

        @staticmethod
        def on_finish(state: State, ctx):
            return state.model_copy(update={"finished": True}), Event("complete")

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
    )

    assert result.terminal == SUCCESS
    assert result.state.finished is True
    assert result.history == ("pair", "ask", "finish")


def test_llm_step_contract_logs_outcome_raw_output_and_uses_global_route(tmp_path: Path):
    class LLMWorkflow(Workflow):
        class State(BaseModel):
            tag_seen: str = ""

        request = Artifact("{task_folder}/request.txt")
        raw_log = Artifact("{run_folder}/llm.log")
        ask = LLMStep(name="ask", producer="ask.md", requires=[request], log_artifacts=[raw_log])
        entry = ask
        transitions = {
            ask: {"done": SUCCESS},
            GLOBAL: {"failed": "FAIL"},
        }

        @staticmethod
        def on_ask(state: State, outcome: Outcome, artifacts):
            return state.model_copy(update={"tag_seen": outcome.tag})

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "request.txt").write_text("request", encoding="utf-8")

    engine = Engine(
        LLMWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="bad\n", tag="failed")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
    )

    assert result.terminal == "FAIL"
    assert result.state.tag_seen == "failed"
    assert (run_folder / "llm.log").read_text(encoding="utf-8") == "bad\n"


def test_execution_observers_receive_provider_step_and_success_terminal_events(tmp_path: Path):
    class ObservedWorkflow(Workflow):
        class State(BaseModel):
            pair_tag: str = ""
            llm_tag: str = ""

        main = Session()
        request = Artifact("{task_folder}/request.txt")
        pair = PairStep(name="pair", producer="pair/producer.md", verifier="pair/verifier.md", requires=[request], session=main)
        ask = LLMStep(name="ask", producer="ask.md", session=main)
        finish = SystemStep(name="finish")
        entry = pair
        transitions = {pair: {"pair_ok": ask}, ask: {"llm_ok": finish}, finish: {"done": SUCCESS}}

        def on_start(self, ctx):
            ctx.open_session(self.main)

        @staticmethod
        def on_pair(state: State, outcome: Outcome, artifacts):
            return state.model_copy(update={"pair_tag": outcome.tag})

        @staticmethod
        def on_ask(state: State, outcome: Outcome, artifacts):
            return state.model_copy(update={"llm_tag": outcome.tag})

        @staticmethod
        def on_finish(state: State, ctx):
            return state, Event("done")

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "request.txt").write_text("request", encoding="utf-8")

    first = RecordingObserver()
    second = RecordingObserver()
    engine = Engine(
        ObservedWorkflow,
        provider=ScriptedLLMProvider(
            producer_turns=[
                lambda request: ProducerResponse(
                    raw_output="producer raw",
                    session=SessionBinding(
                        ref_name=request.session.ref_name,
                        scope=request.session.scope,
                        session_id=request.session.session_id,
                        metadata={"source": "producer-response"},
                    ),
                    metadata={"turn": "producer"},
                )
            ],
            verifier_turns=[
                lambda request: OutcomeResponse(
                    outcome=Outcome(raw_output="verified", tag="pair_ok"),
                    session=SessionBinding(
                        ref_name=request.session.ref_name,
                        scope=request.session.scope,
                        session_id=request.session.session_id,
                        metadata={"source": "verifier-response"},
                    ),
                    metadata={"turn": "verifier"},
                )
            ],
            llm_turns=[
                lambda request: OutcomeResponse(
                    outcome=Outcome(raw_output="llm raw", tag="llm_ok"),
                    session=SessionBinding(
                        ref_name=request.session.ref_name,
                        scope=request.session.scope,
                        session_id=request.session.session_id,
                        metadata={"source": "llm-response"},
                    ),
                    metadata={"turn": "llm"},
                )
            ],
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        observers=(first, second),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
    )

    provider_events = [event for event in first.events if isinstance(event, ProviderTurnEvent)]
    step_events = [event for event in first.events if isinstance(event, StepCompletedEvent)]
    terminal_events = [event for event in first.events if isinstance(event, TerminalEvent)]

    assert result.terminal == SUCCESS
    assert [(event.category, event.turn_kind, event.step_name) for event in provider_events] == [
        ("provider_turn", "producer", "pair"),
        ("provider_turn", "verifier", "pair"),
        ("provider_turn", "llm", "ask"),
    ]
    assert [(event.category, event.step_name, event.destination) for event in step_events] == [
        ("step_completed", "pair", "ask"),
        ("step_completed", "ask", "finish"),
        ("step_completed", "finish", SUCCESS),
    ]
    assert len(terminal_events) == 1
    assert terminal_events[0].terminal_kind == "success"
    assert terminal_events[0].history == ("pair", "ask", "finish")
    assert provider_events[0].prompt_path == "pair/producer.md"
    assert provider_events[1].outcome is not None and provider_events[1].outcome.tag == "pair_ok"
    assert provider_events[2].raw_output == "llm raw"
    assert provider_events[0].workflow_name == "ObservedWorkflow"
    assert provider_events[0].task_id == "task-1"
    assert provider_events[0].run_id == "run-1"
    assert provider_events[0].state.pair_tag == ""
    assert provider_events[0].request_session is not None and provider_events[0].request_session.ref_name == "main"
    assert provider_events[0].response_session is not None
    assert provider_events[0].response_session.metadata == {"source": "producer-response"}
    assert provider_events[0].metadata == {"turn": "producer"}
    assert provider_events[1].request_session is not None
    assert provider_events[1].request_session.metadata == {"source": "producer-response"}
    assert provider_events[1].response_session is not None
    assert provider_events[1].response_session.metadata == {"source": "verifier-response"}
    assert provider_events[1].metadata == {"turn": "verifier"}
    assert provider_events[2].request_session is not None
    assert provider_events[2].request_session.metadata == {"source": "verifier-response"}
    assert provider_events[2].response_session is not None
    assert provider_events[2].response_session.metadata == {"source": "llm-response"}
    assert provider_events[2].metadata == {"turn": "llm"}
    assert step_events[0].workflow_name == "ObservedWorkflow"
    assert step_events[0].task_id == "task-1"
    assert step_events[0].run_id == "run-1"
    assert step_events[0].state_before.pair_tag == ""
    assert step_events[0].state_after.pair_tag == "pair_ok"
    assert step_events[1].state_before.pair_tag == "pair_ok"
    assert step_events[1].state_after.llm_tag == "llm_ok"
    assert step_events[2].state_after.llm_tag == "llm_ok"
    assert terminal_events[0].workflow_name == "ObservedWorkflow"
    assert terminal_events[0].task_id == "task-1"
    assert terminal_events[0].run_id == "run-1"
    assert terminal_events[0].state is not None
    assert terminal_events[0].state.llm_tag == "llm_ok"
    assert len(first.events) == len(second.events)
    assert [type(event) for event in first.events] == [type(event) for event in second.events]


def test_system_step_contract_bypasses_middleware(tmp_path: Path):
    class SystemWorkflow(Workflow):
        class State(BaseModel):
            completed: bool = False

        begin = SystemStep(name="begin")
        entry = begin
        transitions = {begin: {"done": SUCCESS}}

        @staticmethod
        def on_begin(state: State, ctx):
            return state.model_copy(update={"completed": True}), Event("done")

        @staticmethod
        def on_outcome(state: State, outcome: Outcome):
            raise AssertionError("middleware must not run for system steps")

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        SystemWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
    )

    assert result.terminal == SUCCESS
    assert result.state.completed is True


def test_on_start_opens_sessions_before_execution(tmp_path: Path):
    class StartSessionWorkflow(Workflow):
        class State(BaseModel):
            session_id: str = ""
            auxiliary: str = ""

        main = Session()
        auxiliary_slot = Session()
        ask = LLMStep(name="ask", producer="ask.md", session=main)
        entry = ask
        transitions = {ask: {"done": SUCCESS}}

        def on_start(self, ctx):
            ctx.open_session(self.main)
            ctx.open_session(self.auxiliary_slot)

        @staticmethod
        def on_ask(state: State, outcome: Outcome, artifacts):
            return state.model_copy(update={"session_id": outcome.payload["session_id"]})

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
    )

    snapshot = session_store.snapshot()
    assert result.state.session_id.startswith("main:global:")
    assert snapshot.active_scopes == {"main": None, "auxiliary_slot": None}


def test_missing_session_binding_fails_instead_of_auto_opening(tmp_path: Path):
    class MissingSessionWorkflow(Workflow):
        class State(BaseModel):
            pass

        main = Session()
        ask = LLMStep(name="ask", producer="ask.md", session=main)
        entry = ask
        transitions = {ask: {"done": SUCCESS}}

        @staticmethod
        def on_ask(state: State, outcome: Outcome, artifacts):
            return state

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    session_store = InMemorySessionStore()
    engine = Engine(
        MissingSessionWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=session_store,
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="session slot 'main'"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert checkpoint.session_bindings.active_scopes == {}


def test_middleware_pause_skips_handler_and_resume_injects_answer_once(tmp_path: Path):
    class PauseWorkflow(Workflow):
        class State(BaseModel):
            handler_calls: int = 0
            answer_seen: str | None = None
            answer_visible_in_system: str | None = None

        ask = LLMStep(name="ask", producer="ask.md")
        finish = SystemStep(name="finish")
        entry = ask
        transitions = {ask: {"answered": finish, "question": "PAUSE"}, finish: {"done": SUCCESS}}

        @staticmethod
        def on_ask(state: State, outcome: Outcome, artifacts):
            return state.model_copy(
                update={
                    "handler_calls": state.handler_calls + 1,
                    "answer_seen": outcome.payload.get("answer"),
                }
            )

        @staticmethod
        def on_finish(state: State, ctx):
            return state.model_copy(update={"answer_visible_in_system": ctx.answer}), Event("done")

        @staticmethod
        def on_outcome(state: State, outcome: Outcome):
            if outcome.tag == "question":
                return Event("question", reason=outcome.reason, question=outcome.question)
            return None

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
    )

    assert paused.terminal == "PAUSE"
    assert paused.state.handler_calls == 0
    assert paused.checkpoint.pending_question == "What value?"

    resumed = engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        answer="42",
    )

    assert resumed.terminal == SUCCESS
    assert resumed.state.handler_calls == 1
    assert resumed.state.answer_seen == "42"
    assert resumed.state.answer_visible_in_system is None
    assert checkpoint_store.load() is None


def test_handler_exception_saves_failure_checkpoint(tmp_path: Path):
    class ExplodingWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = LLMStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": SUCCESS}}

        @staticmethod
        def on_ask(state: State, outcome: Outcome, artifacts):
            raise RuntimeError("boom")

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        ExplodingWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(RuntimeError, match="boom"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"


def test_execution_observers_receive_pause_fail_and_fatal_terminal_events(tmp_path: Path):
    class PauseWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = LLMStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"question": "PAUSE"}}

        @staticmethod
        def on_outcome(state: State, outcome: Outcome):
            return Event("question", question=outcome.question)

    class FailWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = LLMStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"failed": "FAIL"}}

    class FatalWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = LLMStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": SUCCESS}}

        @staticmethod
        def on_ask(state: State, outcome: Outcome, artifacts):
            raise RuntimeError("boom")

    task_folder, run_folder = _workspace(tmp_path)

    pause_observer = RecordingObserver()
    paused = Engine(
        PauseWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="Need answer", tag="question", question="What value?")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        observers=(pause_observer,),
    ).run(task_id="task-1", run_id="run-1", task_folder=task_folder, run_folder=run_folder)

    fail_observer = RecordingObserver()
    failed = Engine(
        FailWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="bad", tag="failed")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        observers=(fail_observer,),
    ).run(task_id="task-2", run_id="run-2", task_folder=task_folder, run_folder=run_folder)

    fatal_observer = RecordingObserver()
    fatal_checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        FatalWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=fatal_checkpoint_store,
        observers=(fatal_observer,),
    )

    with pytest.raises(RuntimeError, match="boom"):
        engine.run(task_id="task-3", run_id="run-3", task_folder=task_folder, run_folder=run_folder)

    pause_terminal = [event for event in pause_observer.events if isinstance(event, TerminalEvent)]
    fail_terminal = [event for event in fail_observer.events if isinstance(event, TerminalEvent)]
    fatal_terminal = [event for event in fatal_observer.events if isinstance(event, TerminalEvent)]

    assert paused.terminal == "PAUSE"
    assert len(pause_terminal) == 1
    assert pause_terminal[0].terminal_kind == "pause"
    assert pause_terminal[0].workflow_name == "PauseWorkflow"
    assert pause_terminal[0].task_id == "task-1"
    assert pause_terminal[0].run_id == "run-1"
    assert pause_terminal[0].checkpoint is not None
    assert pause_terminal[0].checkpoint.stage == "ask"
    assert pause_terminal[0].checkpoint.pending_question == "What value?"
    assert pause_terminal[0].state is not None
    assert pause_terminal[0].last_event is not None and pause_terminal[0].last_event.question == "What value?"
    assert pause_terminal[0].exception_type is None
    assert pause_terminal[0].exception_message is None

    assert failed.terminal == "FAIL"
    assert len(fail_terminal) == 1
    assert fail_terminal[0].terminal_kind == "fail"
    assert fail_terminal[0].workflow_name == "FailWorkflow"
    assert fail_terminal[0].task_id == "task-2"
    assert fail_terminal[0].run_id == "run-2"
    assert fail_terminal[0].checkpoint is not None
    assert fail_terminal[0].checkpoint.stage == "ask"
    assert fail_terminal[0].state is not None
    assert fail_terminal[0].last_event is not None and fail_terminal[0].last_event.tag == "failed"
    assert fail_terminal[0].exception_type is None
    assert fail_terminal[0].exception_message is None

    assert len(fatal_terminal) == 1
    assert fatal_terminal[0].terminal_kind == "fatal"
    assert fatal_terminal[0].workflow_name == "FatalWorkflow"
    assert fatal_terminal[0].task_id == "task-3"
    assert fatal_terminal[0].run_id == "run-3"
    assert fatal_terminal[0].checkpoint is not None
    assert fatal_terminal[0].checkpoint.stage == "ask"
    assert fatal_terminal[0].state is not None
    assert fatal_terminal[0].history == ("ask",)
    assert fatal_terminal[0].exception_type == "RuntimeError"
    assert fatal_terminal[0].exception_message == "boom"
    assert fatal_checkpoint_store.load() is not None


def test_missing_required_artifact_raises_and_checkpoints(tmp_path: Path):
    class MissingInputWorkflow(Workflow):
        class State(BaseModel):
            pass

        request = Artifact("{task_folder}/request.txt")
        ask = LLMStep(name="ask", producer="ask.md", requires=[request])
        entry = ask
        transitions = {ask: {"done": SUCCESS}}

        @staticmethod
        def on_ask(state: State, outcome: Outcome, artifacts):
            return state

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
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"


def test_observers_do_not_alter_execution_semantics(tmp_path: Path):
    class ObserverIsolationWorkflow(Workflow):
        class State(BaseModel):
            seen: str = ""

        main = Session()
        ask = LLMStep(name="ask", producer="ask.md", session=main)
        entry = ask
        transitions = {ask: {"done": SUCCESS}}

        def on_start(self, ctx):
            ctx.open_session(self.main)

        @staticmethod
        def on_ask(state: State, outcome: Outcome, artifacts):
            return state.model_copy(update={"seen": outcome.payload["tag_seen"]})

    class MutatingObserver:
        def record(self, event: object) -> None:
            if isinstance(event, ProviderTurnEvent):
                event.state.seen = "observer"
                if event.outcome is not None:
                    event.outcome.payload["tag_seen"] = "observer"
                if event.response_session is not None:
                    event.response_session.metadata["note"] = "observer"
                event.metadata["phase"] = "observer"
            if isinstance(event, StepCompletedEvent):
                event.state_before.seen = "observer"
                event.state_after.seen = "observer"
            if isinstance(event, TerminalEvent) and event.state is not None:
                event.state.seen = "observer"
            raise RuntimeError("observer boom")

    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    engine = Engine(
        ObserverIsolationWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: OutcomeResponse(
                    outcome=Outcome(raw_output="ok", tag="done", payload={"tag_seen": "done"}),
                    session=SessionBinding(
                        ref_name=request.session.ref_name,
                        scope=request.session.scope,
                        session_id=request.session.session_id,
                        metadata={"note": "original"},
                    ),
                    metadata={"phase": "llm"},
                )
            ]
        ),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
        observers=(MutatingObserver(),),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
    )

    snapshot = session_store.snapshot()
    assert result.terminal == SUCCESS
    assert result.state.seen == "done"
    assert snapshot.bindings[0].metadata == {"note": "original"}


def test_phase_scoped_sessions_follow_active_scope_switches(tmp_path: Path):
    class ScopedWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        phase_session = Session()
        activate_a = SystemStep(name="activate_a")
        use_a = LLMStep(name="use_a", producer="use.md", session=phase_session)
        activate_b = SystemStep(name="activate_b")
        use_b = LLMStep(name="use_b", producer="use.md", session=phase_session)
        finish = SystemStep(name="finish")
        entry = activate_a
        transitions = {
            activate_a: {"phase-a": use_a},
            use_a: {"next": activate_b},
            activate_b: {"phase-b": use_b},
            use_b: {"done": finish},
            finish: {"end": SUCCESS},
        }

        @staticmethod
        def on_activate_a(state: State, ctx):
            ctx.open_session("phase_session", scope="phase-a")
            return state, Event("phase-a")

        @staticmethod
        def on_use_a(state: State, outcome: Outcome, artifacts):
            return state.model_copy(update={"seen": [*state.seen, outcome.payload["session_id"]]})

        @staticmethod
        def on_activate_b(state: State, ctx):
            ctx.open_session("phase_session", scope="phase-b")
            return state, Event("phase-b")

        @staticmethod
        def on_use_b(state: State, outcome: Outcome, artifacts):
            return state.model_copy(update={"seen": [*state.seen, outcome.payload["session_id"]]})

        @staticmethod
        def on_finish(state: State, ctx):
            return state, Event("end")

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
    )

    assert result.terminal == SUCCESS
    assert len(result.state.seen) == 2
    assert result.state.seen[0].startswith("phase_session:phase-a:")
    assert result.state.seen[1].startswith("phase_session:phase-b:")
    assert result.state.seen[0] != result.state.seen[1]


def test_compiled_workflow_is_deterministic():
    class DeterministicWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = LLMStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": SUCCESS}}

        @staticmethod
        def on_ask(state: State, outcome: Outcome, artifacts):
            return state

    first = compile_workflow(DeterministicWorkflow)
    second = compile_workflow(DeterministicWorkflow)

    assert first is second


def test_step_named_start_executes_without_being_treated_as_lifecycle_hook(tmp_path: Path):
    class StartNamedWorkflow(Workflow):
        class State(BaseModel):
            handler_calls: int = 0

        start = LLMStep(name="start", producer="start.md")
        entry = start
        transitions = {start: {"done": SUCCESS}}

        @staticmethod
        def on_start(state: State, outcome: Outcome, artifacts):
            return state.model_copy(update={"handler_calls": state.handler_calls + 1})

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
    )

    assert result.terminal == SUCCESS
    assert result.state.handler_calls == 1


def test_step_named_outcome_executes_without_being_treated_as_global_middleware(tmp_path: Path):
    class OutcomeNamedWorkflow(Workflow):
        class State(BaseModel):
            handler_calls: int = 0

        outcome = LLMStep(name="outcome", producer="outcome.md")
        entry = outcome
        transitions = {outcome: {"done": SUCCESS}}

        @staticmethod
        def on_outcome(state: State, outcome: Outcome, artifacts):
            return state.model_copy(update={"handler_calls": state.handler_calls + 1})

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
    )

    assert result.terminal == SUCCESS
    assert result.state.handler_calls == 1


def test_step_named_verdict_executes_without_being_treated_as_global_middleware(tmp_path: Path):
    class VerdictNamedWorkflow(Workflow):
        class State(BaseModel):
            handler_calls: int = 0

        verdict = LLMStep(name="verdict", producer="verdict.md")
        entry = verdict
        transitions = {verdict: {"done": SUCCESS}}

        @staticmethod
        def on_verdict(state: State, outcome: Outcome, artifacts):
            return state.model_copy(update={"handler_calls": state.handler_calls + 1})

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
    )

    assert result.terminal == SUCCESS
    assert result.state.handler_calls == 1
