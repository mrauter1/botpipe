"""Autoloop-v1 workflow package."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.extensions import SessionPaths
    from autoloop_v3.stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from extensions import SessionPaths
    from stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags

from workflow import Artifact, FAIL, GLOBAL, PAUSE, PairStep, Session, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event, Outcome

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

    plan = PairStep(
        name="plan",
        session=plan_session,
        producer="prompts/plan_producer.md",
        verifier="prompts/plan_verifier.md",
        requires=[request],
        produces={"phase_plan": phase_plan},
    )
    activate_next_phase = SystemStep(name="activate_next_phase")
    implement = PairStep(
        name="implement",
        session=phase_session,
        producer="prompts/implement_producer.md",
        verifier="prompts/implement_verifier.md",
        requires=[phase_plan],
        produces={"impl_notes": impl_notes},
    )
    test = PairStep(
        name="test",
        session=phase_session,
        producer="prompts/test_producer.md",
        verifier="prompts/test_verifier.md",
        produces={"test_strat": test_strat},
    )

    extensions = (
        SessionPaths(AutoloopV1SessionPathStrategy()),
        AutoloopV1Parity(),
    )

    entry = plan

    transitions = merge_transitions(
        global_routes(pause_on_outcome_tags("question", "blocked"), failed=FAIL),
        {
            GLOBAL: {"failed": FAIL},
            plan: {
                "plan_ready": activate_next_phase,
                "needs_replan": plan,
            },
            activate_next_phase: {
                "phase_selected": implement,
                "workflow_complete": SUCCESS,
            },
            implement: {
                "implemented": test,
                "needs_replan": plan,
            },
            test: {
                "phase_passed": activate_next_phase,
                "needs_replan": plan,
            },
        },
    )

    def on_start(self, ctx) -> None:
        ctx.open_session("plan_session")

    @staticmethod
    def on_plan(state: State, outcome: Outcome, artifacts):
        if outcome.tag not in {"plan_ready", "needs_replan"}:
            return state
        phases = _load_phase_plan(artifacts.phase_plan.read_text())
        return state.model_copy(update={"phases": phases, "phase_index": -1, "phase": None})

    @staticmethod
    def on_activate_next_phase(state: State, ctx) -> tuple[State, Event]:
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
