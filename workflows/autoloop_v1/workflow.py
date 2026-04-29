"""Autoloop-v1 workflow package."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.extensions import SessionPaths
    from autoloop_v3.stdlib.control import event_on_outcome_tags
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from extensions import SessionPaths
    from stdlib.control import event_on_outcome_tags

from autoloop import Event, FAIL, FINISH, Outcome, Prompt, Session, Workflow, produce_verify_step, python_step
from core import Artifact

from .conventions import AutoloopV1SessionPathStrategy, phase_dir_key
from .parity import AutoloopV1Parity


class Phase(BaseModel):
    id: str
    dir_key: str


class AutoloopV1(Workflow):
    """Minimal Autoloop-v1 workflow rebuilt on the general runtime."""

    name = "autoloop_v1"

    class State(BaseModel):
        phases: list[Phase] = Field(default_factory=list)
        phase_index: int = -1
        phase: Phase | None = None

    plan_session = Session()
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
        SessionPaths(AutoloopV1SessionPathStrategy()),
        AutoloopV1Parity(),
    )

    def on_start(self, ctx) -> None:
        ctx.open_session("plan_session")

    @staticmethod
    def on_plan(state: State, outcome: Outcome, artifacts):
        if outcome.tag not in {"plan_ready", "needs_replan"}:
            return state
        phases = _load_phase_plan(artifacts.phase_plan.read_text())
        return state.model_copy(update={"phases": phases, "phase_index": -1, "phase": None})

    @python_step(
        name="activate_next_phase",
        routes={"phase_selected": "implement", "workflow_complete": FINISH},
    )
    def activate_next_phase(state: State, ctx):
        next_index = state.phase_index + 1
        if next_index >= len(state.phases):
            return state, Event("workflow_complete")
        phase = state.phases[next_index]
        ctx.open_session("phase_session", scope=phase.id)
        return state.model_copy(update={"phase_index": next_index, "phase": phase}), Event("phase_selected")

    @staticmethod
    def on_implement(state: State, outcome: Outcome, artifacts):
        return state

    @staticmethod
    def on_test(state: State, outcome: Outcome, artifacts):
        return state

    entry = plan

    on_outcome = staticmethod(event_on_outcome_tags("question", "blocked", "failed"))


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
