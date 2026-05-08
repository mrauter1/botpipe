"""Botlane-v1 workflow package."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from botlane import Event, FAIL, FINISH, Outcome, Prompt, Session, Workflow, produce_verify_step, python_step
from botlane.core import Artifact
from botlane.extensions import SessionPaths

from .conventions import BotlaneV1SessionPathStrategy, phase_dir_key
from .parity import BotlaneV1Parity


class Phase(BaseModel):
    id: str
    dir_key: str


def _after_plan(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    if outcome.tag not in {"plan_ready", "needs_replan"}:
        return None
    phases = _load_phase_plan(ctx.artifacts.phase_plan.read_text())
    ctx.state.phases = phases
    ctx.state.phase_index = -1
    ctx.state.phase = None
    return None


class BotlaneV1(Workflow):
    """Minimal Botlane-v1 workflow rebuilt on the general runtime."""

    name = "botlane_v1"

    class State(BaseModel):
        phases: list[Phase] = Field(default_factory=list)
        phase_index: int = -1
        phase: Phase | None = None

    plan_session = Session(open=True)
    phase_session = Session()

    request = Artifact("{run_folder}/request.md")
    phase_plan = Artifact("{task_folder}/plan/phase_plan.yaml")
    impl_notes = Artifact("{task_folder}/implement/phases/{state.phase.dir_key}/implementation_notes.md")
    test_strat = Artifact("{task_folder}/test/phases/{state.phase.dir_key}/test_strategy.md")

    plan = produce_verify_step(
        producer_prompt=Prompt.file("prompts/plan_producer.md"),
        verifier_prompt=Prompt.file("prompts/plan_verifier.md"),
        session=plan_session,
        requires=[request],
        producer_writes=[phase_plan],
        routes={"plan_ready": "activate_next_phase", "needs_replan": "plan"},
        after_verifier=_after_plan,
    )
    implement = produce_verify_step(
        producer_prompt=Prompt.file("prompts/implement_producer.md"),
        verifier_prompt=Prompt.file("prompts/implement_verifier.md"),
        session=phase_session,
        requires=[phase_plan],
        producer_writes=[impl_notes],
        routes={"implemented": "test", "needs_replan": "plan"},
    )
    test = produce_verify_step(
        producer_prompt=Prompt.file("prompts/test_producer.md"),
        verifier_prompt=Prompt.file("prompts/test_verifier.md"),
        session=phase_session,
        producer_writes=[test_strat],
        routes={"phase_passed": "activate_next_phase", "needs_replan": "plan"},
    )

    extensions = (
        SessionPaths(BotlaneV1SessionPathStrategy()),
        BotlaneV1Parity(),
    )

    @python_step(
        name="activate_next_phase",
        routes={"phase_selected": "implement", "workflow_complete": FINISH},
    )
    def activate_next_phase(ctx):
        next_index = ctx.state.phase_index + 1
        if next_index >= len(ctx.state.phases):
            return "workflow_complete"
        phase = ctx.state.phases[next_index]
        ctx.open_session("phase_session", scope=phase.id)
        ctx.state.phase_index = next_index
        ctx.state.phase = phase
        return "phase_selected"

    entry = plan


def _load_phase_plan(raw: str) -> list[Phase]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("phase plan must be a JSON object")
    phases = payload.get("phases")
    if not isinstance(phases, list):
        raise ValueError("phase plan must define a phases list")
    resolved: list[Phase] = []
    for item in phases:
        if not isinstance(item, dict):
            raise ValueError("phase entries must be objects")
        phase_id = item.get("phase_id")
        if not isinstance(phase_id, str) or not phase_id.strip():
            raise ValueError("phase entries must define a non-empty phase_id")
        normalized = phase_id.strip()
        resolved.append(Phase(id=normalized, dir_key=phase_dir_key(normalized)))
    return resolved
