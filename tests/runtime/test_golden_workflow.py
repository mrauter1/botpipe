from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from botlane import Outcome
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from botlane.runtime.inspection import load_run_history, load_run_record, load_run_topology
from botlane.runtime.runner import RunnerOptions, run_workflow_package


def _clear_workflow_modules() -> None:
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if name == "workflows" or name.startswith("workflows.") or name == "botlane.workflows" or name.startswith("botlane.workflows."):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_generated_workflow_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def _runner_options(root: Path, **kwargs: object) -> RunnerOptions:
    kwargs.setdefault(
        "runtime_config",
        RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
    )
    return RunnerOptions(root=root, **kwargs)


def _write_golden_workflow_package(root: Path) -> None:
    package_dir = root / "workflows" / "golden_surface"
    prompts_dir = package_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        "from .workflow import GoldenSurfaceWorkflow\nfrom .params import Params\n__all__ = ['GoldenSurfaceWorkflow', 'Params']\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text('name = "golden_surface"\n', encoding="utf-8")
    (package_dir / "params.py").write_text(
        """
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Params(BaseModel):
    mode: Literal["publish", "fail"] = "publish"
    gates: list[dict[str, str]] = Field(
        default_factory=lambda: [{"id": "gate-1", "title": "Launch gate"}]
    )
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (prompts_dir / "prepare.md").write_text("Prepare the release packet.\n", encoding="utf-8")
    (prompts_dir / "review_producer.md").write_text("Draft the approval packet.\n", encoding="utf-8")
    (prompts_dir / "review_verifier.md").write_text("Verify the approval packet.\n", encoding="utf-8")
    (package_dir / "workflow.py").write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from botlane import (
    FINISH,
    Fail,
    Goto,
    Json,
    Md,
    Prompt,
    RequestInput,
    Route,
    StateVar,
    Workflow,
    Worklist,
    classify,
    llm,
    produce_verify_step,
    python_step,
    step,
)

from .params import Params


class ApprovalInput(BaseModel):
    approved: bool
    note: str | None = None


class PrepPacket(BaseModel):
    mode: str
    prepared: bool


class GateState(BaseModel):
    attempts: int = 0
    local_notes: str | None = None


class GoldenSurfaceWorkflow(Workflow):
    name = "golden_surface"
    Params = Params

    class State(BaseModel):
        approval_granted: bool = False
        approval_note: str | None = None
        publication_summary: str | None = None
        final_status: str | None = None

    gates = Worklist.from_param("gates", item_id="id", title="title", item_state=GateState)
    prep_packet = Json("prep_packet", PrepPacket, required=True)

    prepare = step(
        prompt=Prompt.file("prompts/prepare.md"),
        writes=[prep_packet],
    )

    @staticmethod
    def _redirect_hidden(ctx):
        return "request_approval"

    @staticmethod
    def _request_approval(ctx):
        return RequestInput(
            "Approve publication?",
            reason="Verifier escalated the release gate.",
            best_supposition="approve",
            input_schema=ApprovalInput,
        )

    @staticmethod
    def _after_review(ctx):
        ctx.step_state.selected_risk_level = "high"
        if ctx.input_response is None:
            assert ctx.step_item_state.visits == 1
            ctx.item_state.attempts += 1
            ctx.item_state.local_notes = "needs director signoff"
            ctx.step_item_state.approval_passes += 1
            return "human_escalation"
        assert ctx.step_item_state.visits == 2
        assert ctx.step_item_state.approval_passes == 1
        assert ctx.item_state.attempts == 1
        assert ctx.item_state.local_notes == "needs director signoff"
        assert ctx.step_state.selected_risk_level == "high"
        ctx.state.approval_granted = bool(ctx.input_response.approved)
        ctx.state.approval_note = ctx.input_response.note
        return Goto("decision", reason="Approval captured.")

    review = produce_verify_step(
        producer_prompt=Prompt.file("prompts/review_producer.md"),
        verifier_prompt=Prompt.file("prompts/review_verifier.md"),
        requires=[prepare.prep_packet],
        producer_writes=[Md("draft", required=True)],
        verifier_writes=[Md("review_report", required=True)],
        scope=gates,
        state={"selected_risk_level": StateVar("low")},
        item_state={
            "approval_passes": StateVar(0),
        },
        after_verifier=_after_review,
        routes={
            "approved": Route.to("decision", required_writes=["draft", "review_report"]),
            "human_escalation": Route.to("decision", provider_visible=False, on_taken=_redirect_hidden),
            "request_approval": Route.to("decision", provider_visible=False, on_taken=_request_approval),
        },
    )

    decision = classify.step(
        prompt="Choose publish or abort for {review.draft}.",
        choices=["publish", "abort"],
    )

    @staticmethod
    def _after_finalize(ctx):
        assert ctx.route.tag == "done"
        if ctx.values.decision == "abort":
            return Fail("Publication aborted after final review.")
        return None

    @python_step(name="finalize", routes={"done": FINISH}, after=_after_finalize)
    def finalize(state, ctx):
        summary = llm("Write the release summary.", returns=str)
        ctx.state = state.model_copy(
            update={
                "publication_summary": summary,
                "final_status": ctx.values.decision,
            }
        )
        return "done"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _run_dir(root: Path, *, task_id: str, run_id: str) -> Path:
    return root / ".autoloop" / "tasks" / task_id / "wf_golden_surface" / "runs" / run_id


def test_golden_workflow_exercises_runtime_controls_resume_topology_and_history(tmp_path: Path) -> None:
    _write_golden_workflow_package(tmp_path)

    first_provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.prep_packet.write_json({"mode": request.context.params.mode, "prepared": True}),
                Outcome(raw_output="prepared", tag="done"),
            )[1],
        ],
        producer_turns=[
            lambda request: (
                request.artifacts.draft.write_text("draft packet\\n"),
                "draft packet\\n",
            )[1]
        ],
        verifier_turns=[
            lambda request: (
                request.artifacts.review_report.write_text("verified packet\\n"),
                Outcome(raw_output="approved", tag="approved", reason="ready"),
            )[1]
        ],
    )

    paused = run_workflow_package(
        "golden_surface",
        provider=first_provider,
        options=_runner_options(
            tmp_path,
            task_id="golden-task-publish",
            run_id="golden-run-publish",
            message="Prepare the release.",
            workflow_params={"mode": "publish"},
        ),
    )

    run_dir = _run_dir(tmp_path, task_id="golden-task-publish", run_id="golden-run-publish")
    assert paused.terminal == "AWAIT_INPUT"
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_input is not None
    assert paused.checkpoint.pending_input.question == "Approve publication?"
    assert paused.checkpoint.pending_input.input_schema is not None
    assert (run_dir / "topology.json").exists()
    assert (run_dir / "topology.mmd").exists()
    assert (run_dir / "route_table.md").exists()
    assert (run_dir / "artifact_contracts.json").exists()
    assert (run_dir / "prompt_refs.json").exists()
    assert (run_dir / "state_contracts.json").exists()
    assert (run_dir / "session_contracts.json").exists()
    assert (run_dir / "compile_report.md").exists()
    assert all(
        route_tag not in first_provider.calls[2].available_routes
        for route_tag in ("human_escalation", "request_approval")
    )

    record = load_run_record(
        tmp_path,
        workflow_name="golden_surface",
        task_id="golden-task-publish",
        run_id="golden-run-publish",
    )
    topology = load_run_topology(record)
    review_topology = next(step for step in topology["steps"] if step["name"] == "review")
    approved_route = next(route for route in review_topology["routes"] if route["tag"] == "approved")
    hidden_route = next(route for route in review_topology["routes"] if route["tag"] == "human_escalation")

    assert approved_route["explicit_required_writes"] == ["review.draft", "review.review_report"]
    assert approved_route["effective_required_writes"] == ["review.draft", "review.review_report"]
    assert hidden_route["provider_visible"] is False

    resume_provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.draft.write_text("draft packet\\n"),
                "draft packet\\n",
            )[1]
        ],
        verifier_turns=[
            lambda request: (
                request.artifacts.review_report.write_text("verified packet\\n"),
                Outcome(raw_output="approved", tag="approved", reason="ready"),
            )[1]
        ],
        operation_turns=["publish", "Release summary ready."],
    )

    resumed = run_workflow_package(
        "golden_surface",
        provider=resume_provider,
        options=_runner_options(
            tmp_path,
            task_id="golden-task-publish",
            run_id="golden-run-publish",
            resume=True,
            answer='{"approved": true, "note": "needs director signoff"}',
        ),
    )

    assert resumed.terminal == "FINISH"
    assert resumed.state.approval_granted is True
    assert resumed.state.approval_note == "needs director signoff"
    assert resumed.state.publication_summary == "Release summary ready."
    assert resumed.state.final_status == "publish"

    history = load_run_history(record)
    review_routes = history.routes(step="review", scope="gates", item_id="gate-1")
    review_telemetry = history.step_telemetry("review", scope="gates", item_id="gate-1")

    assert [route["runtime_control"] for route in review_routes] == ["request_input", "goto"]
    assert review_routes[0]["terminal"] == "AWAIT_INPUT"
    assert review_routes[1]["target_step"] == "decision"
    assert review_telemetry["status"] == "completed"
    assert review_telemetry["completed"] is True


def test_golden_workflow_fail_path_emits_direct_fail_runtime_control(tmp_path: Path) -> None:
    _write_golden_workflow_package(tmp_path)

    first_provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.prep_packet.write_json({"mode": request.context.params.mode, "prepared": True}),
                Outcome(raw_output="prepared", tag="done"),
            )[1],
        ],
        producer_turns=[
            lambda request: (
                request.artifacts.draft.write_text("draft packet\\n"),
                "draft packet\\n",
            )[1]
        ],
        verifier_turns=[
            lambda request: (
                request.artifacts.review_report.write_text("verified packet\\n"),
                Outcome(raw_output="approved", tag="approved", reason="ready"),
            )[1]
        ],
    )
    paused = run_workflow_package(
        "golden_surface",
        provider=first_provider,
        options=_runner_options(
            tmp_path,
            task_id="golden-task-fail",
            run_id="golden-run-fail",
            message="Prepare the release.",
            workflow_params={"mode": "fail"},
        ),
    )

    assert paused.terminal == "AWAIT_INPUT"

    resume_provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.draft.write_text("draft packet\\n"),
                "draft packet\\n",
            )[1]
        ],
        verifier_turns=[
            lambda request: (
                request.artifacts.review_report.write_text("verified packet\\n"),
                Outcome(raw_output="approved", tag="approved", reason="ready"),
            )[1]
        ],
        operation_turns=["abort", "Release summary ready."],
    )

    failed = run_workflow_package(
        "golden_surface",
        provider=resume_provider,
        options=_runner_options(
            tmp_path,
            task_id="golden-task-fail",
            run_id="golden-run-fail",
            resume=True,
            answer='{"approved": true, "note": "needs director signoff"}',
        ),
    )

    record = load_run_record(
        tmp_path,
        workflow_name="golden_surface",
        task_id="golden-task-fail",
        run_id="golden-run-fail",
    )
    history = load_run_history(record)
    finalize_routes = history.routes(step="finalize")

    assert failed.terminal == "FAIL"
    assert failed.state.final_status == "abort"
    assert failed.state.publication_summary == "Release summary ready."
    assert finalize_routes[-1]["runtime_control"] == "fail"
    assert finalize_routes[-1]["terminal"] == "FAIL"
