from __future__ import annotations

from pydantic import BaseModel

from botpipe.core import AWAIT_INPUT, Artifact, FAIL, FINISH, GLOBAL, Session, Workflow
from botpipe.core.steps import PromptStep, PythonStep


def _open_orbit(ctx) -> None:
    ctx.open_session("orbit", scope="cluster-1")


def _capture_survey_note(ctx) -> None:
    if ctx.artifacts is not None:
        ctx.state.note = ctx.artifacts.notes.read_text().strip()


def _archive(ctx) -> str:
    ctx.state.archived = True
    return "archived"


class ToyRuntimeWorkflow(Workflow):
    name = "toy_runtime_workflow"

    class State(BaseModel):
        note: str = ""
        archived: bool = False

    orbit = Session()

    request = Artifact("{{ task.folder }}/request.md")
    notes = Artifact("{{ task.folder }}/toy/notes.md")
    transcript = Artifact("{{ run.folder }}/toy_transcript.log")

    survey = PromptStep(
        name="survey",
        producer="toy/survey.md",
        session=orbit,
        requires=[request],
        writes={"notes": notes},
        log_artifacts=[transcript],
        before=_open_orbit,
        after=_capture_survey_note,
    )
    archive = PythonStep(name="archive", handler=_archive)

    entry = survey

    transitions = {
        GLOBAL: {
            "blocked": AWAIT_INPUT,
            "failed": FAIL,
            "question": AWAIT_INPUT,
        },
        survey: {
            "surveyed": archive,
        },
        archive: {
            "archived": FINISH,
        },
    }
