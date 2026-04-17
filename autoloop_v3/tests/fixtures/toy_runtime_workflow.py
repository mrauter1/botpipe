from __future__ import annotations

from pydantic import BaseModel

from workflow import Artifact, Context, FAIL, GLOBAL, LLMStep, PAUSE, SUCCESS, Session, SystemStep, Workflow
from workflow.primitives import Event, Outcome, ResolvedArtifacts


class ToyRuntimeWorkflow(Workflow):
    name = "toy_runtime_workflow"

    class State(BaseModel):
        note: str = ""
        archived: bool = False

    orbit = Session()

    request = Artifact("{task_folder}/request.md")
    notes = Artifact("{task_folder}/toy/notes.md")
    transcript = Artifact("{run_folder}/toy_transcript.log")

    survey = LLMStep(
        name="survey",
        producer="toy/survey.md",
        session=orbit,
        requires=[request],
        produces={"notes": notes},
        log_artifacts=[transcript],
    )
    archive = SystemStep(name="archive")

    entry = survey

    transitions = {
        GLOBAL: {
            "blocked": PAUSE,
            "failed": FAIL,
            "question": PAUSE,
        },
        survey: {
            "surveyed": archive,
        },
        archive: {
            "archived": SUCCESS,
        },
    }

    def on_start(self, ctx: Context) -> None:
        ctx.open_session(self.orbit, scope="cluster-1")

    @staticmethod
    def on_survey(state: State, outcome: Outcome, artifacts: ResolvedArtifacts) -> State:
        return state.model_copy(update={"note": artifacts.notes.read_text().strip()})

    @staticmethod
    def on_archive(state: State, ctx: Context) -> tuple[State, Event]:
        return state.model_copy(update={"archived": True}), Event("archived")

    @staticmethod
    def on_outcome(state: State, outcome: Outcome) -> Event | None:
        if outcome.tag in {"blocked", "failed", "question"}:
            return Event(outcome.tag, reason=outcome.reason, question=outcome.question)
        return None
