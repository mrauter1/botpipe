from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, get_args

from pydantic import BaseModel

import botlane.simple as simple
from botlane.core.compiler import compile_workflow
from botlane.core.context import Context
from botlane.core.engine import Engine
from botlane.core.primitives import Outcome
from botlane.core.providers.models import StepProviderUsage, TokenUsage
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.providers.rendered import RenderedLLMProvider
from botlane.core.providers.turns import ProviderTurnResult, RenderedProviderTurn
from botlane.core.stores.protocols import SessionBinding
from botlane.core.step_plans import ProduceVerifyStepPlan, PromptStepPlan, ProviderTurnKind
from botlane.core.stores import InMemoryCheckpointStore, InMemorySessionStore


@dataclass
class _SequencedTransport:
    raw_texts: list[str]
    seen_turns: list[RenderedProviderTurn]

    async def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        self.seen_turns.append(turn)
        if not self.raw_texts:
            raise AssertionError("unexpected extra provider turn")
        return ProviderTurnResult(raw_text=self.raw_texts.pop(0), session=None)


@dataclass
class _ResultTransport:
    responses: list[ProviderTurnResult | Callable[[RenderedProviderTurn], ProviderTurnResult]]
    seen_turns: list[RenderedProviderTurn]

    async def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        self.seen_turns.append(turn)
        if not self.responses:
            raise AssertionError("unexpected extra provider turn")
        response = self.responses.pop(0)
        return response(turn) if callable(response) else response


def _build_step_context(engine: Engine, tmp_path: Path, *, step_name: str) -> tuple[object, Context]:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / f"wf_{engine.compiled.workflow_name}"
    run_folder = tmp_path / "run"
    package_folder = tmp_path / "package"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    run_folder.mkdir(parents=True, exist_ok=True)
    package_folder.mkdir(parents=True, exist_ok=True)

    step = engine.compiled.steps[step_name]
    context = Context(
        root=tmp_path,
        task_id="task-provider-turn-plan",
        run_id="run-provider-turn-plan",
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
    context._execution_frame.set_worklist_selection_resolver(
        lambda worklist_name: (_ for _ in ()).throw(AssertionError(worklist_name))
    )
    step_state_store = engine._ensure_step_state_store({}, step)
    engine._increment_step_runtime_state(step_state_store)
    context._execution_frame.set_step_state(step_state_store)
    context._execution_frame.set_values(context._values)
    context._execution_frame.set_meta({"step": {"name": step.name, "kind": step.kind, "visits": 1, "last_route": None}})
    return step, context


def test_compiler_emits_provider_turn_plans_for_provider_backed_steps() -> None:
    class ProviderWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        ask = simple.step("Ask the provider.", name="ask", routes={"next": "review"})
        review = simple.produce_verify_step(
            producer_prompt="Draft the report.",
            verifier_prompt="Review the report.",
            name="review",
            routes={"accepted": simple.FINISH},
        )

    compiled = compile_workflow(ProviderWorkflow)

    assert isinstance(compiled.steps["ask"], PromptStepPlan)
    assert compiled.steps["ask"].turn.kind == "llm"
    assert isinstance(compiled.steps["review"], ProduceVerifyStepPlan)
    assert compiled.steps["review"].producer.kind == "producer"
    assert compiled.steps["review"].verifier.kind == "verifier"
    assert set(get_args(ProviderTurnKind)) == {"llm", "producer", "verifier"}
    assert "operation" not in get_args(ProviderTurnKind)


def test_prompt_provider_turn_plan_keeps_rendered_transport_boundary(tmp_path: Path) -> None:
    class PromptWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        review = simple.step("Review the document.", name="review", routes={"done": simple.FINISH})

    seen_turns: list[RenderedProviderTurn] = []
    provider = RenderedLLMProvider(_SequencedTransport(raw_texts=['{"tag":"done"}'], seen_turns=seen_turns))
    engine = Engine(
        PromptWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-provider-turn-plan",
        run_id="run-provider-turn-plan",
        task_folder=tmp_path / "task",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert len(seen_turns) == 1
    assert isinstance(seen_turns[0], RenderedProviderTurn)
    assert seen_turns[0].turn_kind == "step"
    assert seen_turns[0].expected_response == "outcome_json"


def test_produce_verify_provider_turn_plan_keeps_rendered_transport_boundary(tmp_path: Path) -> None:
    class PairWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        review = simple.produce_verify_step(
            producer_prompt="Draft the report.",
            verifier_prompt="Review the report.",
            name="review",
            producer_writes=[simple.Md("draft")],
            verifier_writes=[simple.Md("decision")],
            routes={"accepted": simple.FINISH, "needs_rework": simple.SELF},
        )

    seen_turns: list[RenderedProviderTurn] = []
    provider = RenderedLLMProvider(
        _SequencedTransport(
            raw_texts=[
                "Draft content",
                '{"tag":"accepted"}',
            ],
            seen_turns=seen_turns,
        )
    )
    engine = Engine(
        PairWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-provider-turn-plan",
        run_id="run-provider-turn-plan",
        task_folder=tmp_path / "task",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert [turn.turn_kind for turn in seen_turns] == ["producer", "verifier"]
    assert all(isinstance(turn, RenderedProviderTurn) for turn in seen_turns)
    assert seen_turns[0].expected_response == "raw_text"
    assert seen_turns[1].expected_response == "outcome_json"


def test_rendered_prompt_provider_turn_plan_retries_and_persists_session(tmp_path: Path) -> None:
    class PromptWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        main = simple.Session()
        review = simple.step("Review the document.", name="review", session=main, routes={"done": simple.FINISH})

    seen_turns: list[RenderedProviderTurn] = []

    def _illegal_route(turn: RenderedProviderTurn) -> ProviderTurnResult:
        assert turn.session is not None
        return ProviderTurnResult(
            raw_text='{"tag":"unexpected"}',
            session=SessionBinding(key=turn.session.key, session_id="retry-attempt-1"),
        )

    def _accepted(turn: RenderedProviderTurn) -> ProviderTurnResult:
        assert turn.session is not None
        return ProviderTurnResult(
            raw_text='{"tag":"done"}',
            session=SessionBinding(key=turn.session.key, session_id="retry-attempt-2"),
        )

    provider = RenderedLLMProvider(_ResultTransport(responses=[_illegal_route, _accepted], seen_turns=seen_turns))
    session_store = InMemorySessionStore()
    engine = Engine(
        PromptWorkflow,
        provider=provider,
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-provider-turn-retry",
        run_id="run-provider-turn-retry",
        task_folder=tmp_path / "task",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert len(seen_turns) == 2
    assert all(turn.turn_kind == "step" for turn in seen_turns)
    assert seen_turns[0].session is not None
    assert seen_turns[1].session is not None
    assert seen_turns[1].session.session_id == seen_turns[0].session.session_id
    final_binding = session_store.get("main")
    assert final_binding is not None
    assert final_binding.session_id == "retry-attempt-2"


def test_rendered_pair_provider_turn_plan_preserves_outputs_usage_and_sessions(tmp_path: Path) -> None:
    seen_events: list[tuple[str, str | None, str | None, StepProviderUsage | None]] = []

    class _RawOutputExtension:
        def bind(self, binding: object):
            class _Bound:
                def before_step(self, event: object) -> None:
                    return None

                def after_step(self, event: object) -> None:
                    seen_events.append(
                        (
                            event.step_name,
                            event.producer_raw_output,
                            event.verifier_raw_output,
                            event.provider_usage,
                        )
                    )

                def on_terminal(self, event: object) -> None:
                    return None

            return _Bound()

    class PairWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        main = simple.Session()
        review = simple.produce_verify_step(
            producer_prompt="Draft the report.",
            verifier_prompt="Review the report.",
            name="review",
            session=main,
            producer_writes=[simple.Md("draft")],
            routes={"accepted": simple.FINISH},
        )
        extensions = (_RawOutputExtension(),)

    seen_turns: list[RenderedProviderTurn] = []
    producer_usage = TokenUsage(input_tokens=5, output_tokens=7, total_tokens=12, source="fake")
    verifier_usage = TokenUsage(input_tokens=11, output_tokens=3, total_tokens=14, source="fake")

    def _producer(turn: RenderedProviderTurn) -> ProviderTurnResult:
        assert turn.session is not None
        return ProviderTurnResult(
            raw_text="Draft content",
            session=SessionBinding(key=turn.session.key, session_id="producer-attempt-1"),
            usage=producer_usage,
        )

    def _verifier(turn: RenderedProviderTurn) -> ProviderTurnResult:
        assert turn.session is not None
        assert turn.session.session_id == "producer-attempt-1"
        return ProviderTurnResult(
            raw_text='{"tag":"accepted"}',
            session=SessionBinding(key=turn.session.key, session_id="verifier-attempt-1"),
            usage=verifier_usage,
        )

    provider = RenderedLLMProvider(_ResultTransport(responses=[_producer, _verifier], seen_turns=seen_turns))
    session_store = InMemorySessionStore()
    engine = Engine(
        PairWorkflow,
        provider=provider,
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-provider-turn-pair",
        run_id="run-provider-turn-pair",
        task_folder=tmp_path / "task",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert [turn.turn_kind for turn in seen_turns] == ["producer", "verifier"]
    assert seen_events == [
        (
            "review",
            "Draft content",
            '{"tag":"accepted"}',
            StepProviderUsage(producer=producer_usage, verifier=verifier_usage),
        )
    ]
    final_binding = session_store.get("main")
    assert final_binding is not None
    assert final_binding.session_id == "verifier-attempt-1"


def test_route_finalization_exposes_route_decision_for_finish_routes(tmp_path: Path) -> None:
    class PromptWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        review = simple.step("Review the document.", name="review", routes={"done": simple.FINISH})

    engine = Engine(
        PromptWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output='{"tag":"done"}', tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )
    step, context = _build_step_context(engine, tmp_path, step_name="review")

    result = asyncio.run(engine.step_dispatcher.execute_async(step, context, context.state, ()))

    assert result.route_decision is not None
    assert result.action == result.route_decision.action
    assert result.route_decision.final_route == "done"
    assert result.route_decision.contract is not None
    assert result.route_decision.contract.tag == "done"
    assert type(result.route_decision.action).__name__ == "Finish"
    assert type(result.action).__name__ == "Finish"
    assert not hasattr(result, "finalization")


def test_route_finalization_exposes_route_decision_for_await_input_routes(tmp_path: Path) -> None:
    class QuestionWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        review = simple.step(
            "Review the document.",
            name="review",
            routes={"question": simple.AWAIT_INPUT},
        )

    engine = Engine(
        QuestionWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                Outcome(
                    raw_output='{"tag":"question","route_fields":{"questions":["Need approval?"]}}',
                    tag="question",
                    route_fields={"questions": ["Need approval?"]},
                )
            ]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )
    step, context = _build_step_context(engine, tmp_path, step_name="review")

    result = asyncio.run(engine.step_dispatcher.execute_async(step, context, context.state, ()))

    assert result.route_decision is not None
    assert result.action == result.route_decision.action
    assert result.route_decision.final_route == "question"
    assert result.route_decision.contract is not None
    assert result.route_decision.contract.tag == "question"
    assert result.pending_input is not None
    assert type(result.route_decision.action).__name__ == "AwaitInput"
    assert type(result.action).__name__ == "AwaitInput"
    assert result.route_decision.action.pending_input == result.pending_input
    assert result.action.pending_input == result.pending_input
    assert not hasattr(result, "finalization")
