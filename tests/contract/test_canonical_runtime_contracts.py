from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from autoloop import FINISH, Md, Prompt, Route, Workflow, produce_verify_step, step
from core.engine import Engine
from core.primitives import Outcome
from core.providers.fake import ScriptedLLMProvider
from core.stores import InMemoryCheckpointStore, InMemorySessionStore


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()
    return task_folder, run_folder


def test_canonical_step_contract_uses_finish_and_required_writes(tmp_path: Path) -> None:
    class StepWorkflow(Workflow):
        draft = step(
            prompt=Prompt.inline("Write the draft."),
            writes=[Md("report", required=True)],
        )

    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.report.write_text("report\n"),
                Outcome(raw_output="done", tag="done"),
            )[1]
        ]
    )
    task_folder, run_folder = _workspace(tmp_path)

    result = Engine(
        StepWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-step",
        run_id="run-step",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    call = provider.calls[0]
    assert result.terminal == FINISH
    assert call.kind == "step"
    assert call.available_routes == ("done", "question", "blocked", "failed")
    assert call.route_required_writes == {
        "done": (),
        "question": (),
        "blocked": (),
        "failed": (),
    }
    assert not hasattr(call, "route_required_" + "outputs")


def test_canonical_produce_verify_contract_splits_phase_writes_and_verifier_routes(tmp_path: Path) -> None:
    class Decision(BaseModel):
        approved: bool = True

    class ReviewWorkflow(Workflow):
        review = produce_verify_step(
            producer_prompt=Prompt.inline("Draft the report."),
            verifier_prompt=Prompt.inline("Verify the report."),
            producer_writes=[Md("draft", required=True)],
            verifier_writes=[Md("review_report", required=True)],
            routes={
                "approved": Route.to(FINISH, required_writes=["draft", "review_report"]),
            },
        )

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.draft.write_text("draft\n"),
                "producer raw\n",
            )[1]
        ],
        verifier_turns=[
            lambda request: (
                request.artifacts.review_report.write_text("approved\n"),
                Outcome(raw_output="verified", tag="approved", payload=Decision().model_dump()),
            )[1]
        ],
    )
    task_folder, run_folder = _workspace(tmp_path)

    result = Engine(
        ReviewWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-review",
        run_id="run-review",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    producer_call, verifier_call = provider.calls

    assert result.terminal == FINISH
    assert producer_call.kind == "producer"
    assert producer_call.available_routes == ()
    assert [ref.name for ref in producer_call.writable_artifacts] == ["draft"]
    assert producer_call.route_required_writes == {}
    assert verifier_call.kind == "verifier"
    assert verifier_call.available_routes == ("approved", "question", "blocked", "failed")
    assert [ref.name for ref in verifier_call.writable_artifacts] == ["review_report"]
    assert verifier_call.route_required_writes == {
        "approved": ("review.draft", "review.review_report"),
        "question": (),
        "blocked": (),
        "failed": (),
    }
    assert not hasattr(verifier_call, "route_required_" + "outputs")
