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
    SessionLifecycle,
    SystemStep,
    SUCCESS,
    Workflow,
)
from autoloop_v3.workflow.compiler import compile_workflow
from autoloop_v3.workflow.errors import MissingArtifactError
from autoloop_v3.workflow.primitives import Event, Outcome
from autoloop_v3.workflow.providers.fake import ScriptedLLMProvider
from autoloop_v3.workflow.stores import InMemoryCheckpointStore, InMemorySessionStore


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()
    return task_folder, run_folder


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
        def on_ask(state: State, outcome: Outcome):
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


def test_on_start_and_session_lifecycle_open_sessions_before_execution(tmp_path: Path):
    class StartSessionWorkflow(Workflow):
        class State(BaseModel):
            session_id: str = ""
            auxiliary: str = ""

        main = Session(lifecycle=SessionLifecycle.ON_START)
        auxiliary_slot = Session()
        ask = LLMStep(name="ask", producer="ask.md", session=main)
        entry = ask
        transitions = {ask: {"done": SUCCESS}}

        def on_start(self, ctx):
            ctx.open_session(self.auxiliary_slot)

        @staticmethod
        def on_ask(state: State, outcome: Outcome):
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
        def on_ask(state: State, outcome: Outcome):
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
        def on_ask(state: State, outcome: Outcome):
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


def test_missing_required_artifact_raises_and_checkpoints(tmp_path: Path):
    class MissingInputWorkflow(Workflow):
        class State(BaseModel):
            pass

        request = Artifact("{task_folder}/request.txt")
        ask = LLMStep(name="ask", producer="ask.md", requires=[request])
        entry = ask
        transitions = {ask: {"done": SUCCESS}}

        @staticmethod
        def on_ask(state: State, outcome: Outcome):
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
        def on_use_a(state: State, outcome: Outcome):
            return state.model_copy(update={"seen": [*state.seen, outcome.payload["session_id"]]})

        @staticmethod
        def on_activate_b(state: State, ctx):
            ctx.open_session("phase_session", scope="phase-b")
            return state, Event("phase-b")

        @staticmethod
        def on_use_b(state: State, outcome: Outcome):
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
        def on_ask(state: State, outcome: Outcome):
            return state

    first = compile_workflow(DeterministicWorkflow)
    second = compile_workflow(DeterministicWorkflow)

    assert first is second
