"""Autoloop-v1 workflow package shell."""

from __future__ import annotations

from pydantic import BaseModel

from workflow import Artifact, Context, FAIL, GLOBAL, PAUSE, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event


class AutoloopV1(Workflow):
    """Bootstrap shell for the Autoloop-v1 workflow package."""

    name = "autoloop_v1"

    class State(BaseModel):
        status: str = "ready"

    request = Artifact("{task_folder}/request.md")
    bootstrap = SystemStep(name="bootstrap", requires=[request])

    entry = bootstrap

    transitions = {
        GLOBAL: {
            "question": PAUSE,
            "blocked": PAUSE,
            "failed": FAIL,
        },
        bootstrap: {
            "ready": SUCCESS,
        },
    }

    @staticmethod
    def on_bootstrap(state: State, ctx: Context) -> tuple[State, Event]:
        return state.model_copy(update={"status": "ready"}), Event("ready")
