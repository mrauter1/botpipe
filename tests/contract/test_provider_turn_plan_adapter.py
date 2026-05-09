from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

import botlane.simple as simple
from botlane.core.context import Context, context_runtime
from botlane.core.engine import Engine
from botlane.core.primitives import Outcome
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.providers.rendered import RenderedLLMProvider
from botlane.core.providers.turns import ProviderTurnResult, RenderedProviderTurn
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
    runtime = context_runtime(context)
    runtime.set_worklist_selection_resolver(lambda worklist_name: (_ for _ in ()).throw(AssertionError(worklist_name)))
    step_state_store = engine._ensure_step_state_store({}, step)
    engine._increment_step_runtime_state(step_state_store)
    runtime.set_step_state_store(step_state_store)
    runtime.set_values(context._values)
    runtime.set_meta({"step": {"name": step.name, "kind": step.kind, "visits": 1, "last_route": None}})
    return step, context


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
