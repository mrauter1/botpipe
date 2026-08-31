from __future__ import annotations

from pathlib import Path

from botpipe.core.context import ChildWorkflowResult
from botpipe.core.engine import Engine
from botpipe.core.primitives import Event, FINISH, Outcome
from botpipe.core.providers.fake import ScriptedLLMProvider
from botpipe.core.stores import InMemoryCheckpointStore, InMemorySessionStore
from botpipe.workflows.adaptive_goal import (
    AcceptanceRule,
    AdaptiveGoalInput,
    AdaptiveGoalWorkflow,
    CapabilityRegistry,
    CapabilitySpec,
    MissionCriterion,
    MissionSpec,
)
from botpipe.workflows.adaptive_goal.contracts import (
    ActionCapabilityResult,
    ActionRequest,
    Blackboard,
    GlobalAuditDecision,
    VerifierCapabilityResult,
)


def _child_result(
    *,
    task_folder: Path,
    workflow_folder: Path,
    workflow_name: str,
    run_id: str,
) -> ChildWorkflowResult:
    run_folder = workflow_folder / "run"
    sessions = run_folder / "sessions"
    raw = run_folder / "raw"
    sessions.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    request_file = run_folder / "request.md"
    request_file.write_text("child", encoding="utf-8")
    return ChildWorkflowResult(
        workflow_name=workflow_name,
        run_id=run_id,
        terminal=FINISH,
        status="success",
        last_event=Event("done"),
        output_metadata={},
        output_artifacts={},
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=workflow_folder,
        request_file=request_file,
        run_meta_file=run_folder / "run.json",
        events_file=run_folder / "events.jsonl",
        checkpoint_file=run_folder / "checkpoint.json",
        sessions_dir=sessions,
        trace_file=run_folder / "trace.jsonl",
        raw_dir=raw,
        parent_file=workflow_folder / "parent.json",
    )


def test_adaptive_runtime_invalidates_changed_verified_subject_and_reverifies(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<h1>initial</h1>", encoding="utf-8")

    mission = MissionSpec(
        id="adaptive-runtime-test",
        objective="Satisfy visual and content quality.",
        criteria=[
            MissionCriterion(
                id="visual_quality",
                description="Visual quality is high.",
                verifier="verify.visual",
                acceptance=[AcceptanceRule(metric="score", operator="ge", value=85)],
                observed_paths=["site/**"],
            ),
            MissionCriterion(
                id="content_quality",
                description="Content is complete.",
                verifier="verify.content",
                acceptance=[AcceptanceRule(metric="complete", operator="truthy")],
                observed_paths=["site/**"],
            ),
        ],
    )
    registry = CapabilityRegistry(
        capabilities=[
            CapabilitySpec(
                id="verify.visual",
                kind="verifier",
                workflow="verify_visual",
                description="Verify visual quality.",
                verifies=["visual_quality"],
                observed_paths=["site/**"],
            ),
            CapabilitySpec(
                id="improve.content",
                kind="action",
                workflow="improve_content",
                description="Improve page content.",
                helps=["content_quality"],
                may_invalidate=["visual_quality", "content_quality"],
                side_effect="workspace",
            ),
            CapabilitySpec(
                id="verify.content",
                kind="verifier",
                workflow="verify_content",
                description="Verify content quality.",
                verifies=["content_quality"],
                observed_paths=["site/**"],
            ),
        ]
    )
    workflow_input = AdaptiveGoalInput(
        mission=mission,
        registry=registry,
        max_actions=10,
    )

    actions = [
        ActionRequest(
            kind="verifier",
            capability_id="verify.visual",
            objective="Verify the current visual quality.",
            target_criteria=["visual_quality"],
            rationale="Visual quality is unknown.",
        ),
        ActionRequest(
            kind="capability",
            capability_id="improve.content",
            objective="Add the missing content.",
            target_criteria=["content_quality"],
            rationale="Content quality is unresolved.",
        ),
        ActionRequest(
            kind="verifier",
            capability_id="verify.visual",
            objective="Reverify visual quality after the content change.",
            target_criteria=["visual_quality"],
            rationale="The prior visual receipt is stale.",
        ),
        ActionRequest(
            kind="verifier",
            capability_id="verify.content",
            objective="Verify the completed content.",
            target_criteria=["content_quality"],
            rationale="Content work is ready for verification.",
        ),
    ]
    provider = ScriptedLLMProvider(
        llm_turns=[
            *[
                Outcome(
                    raw_output="",
                    tag="selected",
                    payload=action.model_dump(mode="json"),
                )
                for action in actions
            ],
            Outcome(
                raw_output="",
                tag="audited",
                payload=GlobalAuditDecision(
                    status="complete",
                    summary="All mission requirements are satisfied.",
                ).model_dump(mode="json"),
            ),
        ]
    )

    child_index = 0
    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()

    def invoke_child(workflow, *, message, parameters=None, input=None):
        nonlocal child_index
        child_index += 1
        workflow_name = str(workflow)
        child_folder = tmp_path / "child-runs" / f"{child_index}-{workflow_name}"
        child_folder.mkdir(parents=True, exist_ok=True)

        if workflow_name == "verify_visual":
            (child_folder / "verification_result.json").write_text(
                VerifierCapabilityResult(
                    status="observed",
                    verifier_id="verify.visual",
                    summary="Visual quality measured.",
                    observations={"visual_quality": {"score": 90}},
                    evidence=["visual-test"],
                    observed_paths={"visual_quality": ["site/**"]},
                ).model_dump_json(indent=2),
                encoding="utf-8",
            )
        elif workflow_name == "improve_content":
            (site / "index.html").write_text(
                "<h1>improved</h1><p>complete content</p>",
                encoding="utf-8",
            )
            (child_folder / "capability_result.json").write_text(
                ActionCapabilityResult(
                    status="completed",
                    summary="Content improved.",
                    evidence=["site/index.html"],
                    changed_paths=["site/index.html"],
                ).model_dump_json(indent=2),
                encoding="utf-8",
            )
        elif workflow_name == "verify_content":
            (child_folder / "verification_result.json").write_text(
                VerifierCapabilityResult(
                    status="observed",
                    verifier_id="verify.content",
                    summary="Content quality measured.",
                    observations={"content_quality": {"complete": True}},
                    evidence=["content-test"],
                    observed_paths={"content_quality": ["site/**"]},
                ).model_dump_json(indent=2),
                encoding="utf-8",
            )
        else:
            raise AssertionError(f"unexpected child workflow {workflow_name!r}")

        return _child_result(
            task_folder=task_folder,
            workflow_folder=child_folder,
            workflow_name=workflow_name,
            run_id=f"child-{child_index}",
        )

    result = Engine(
        AdaptiveGoalWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_input=workflow_input,
        workflow_invoker=invoke_child,
        max_steps=0,
    )

    assert result.terminal == FINISH
    assert result.state.status == "complete"

    blackboard_path = task_folder / "wf_adaptive_goal" / "blackboard.json"
    blackboard = Blackboard.model_validate_json(
        blackboard_path.read_text(encoding="utf-8")
    )
    assert blackboard.criteria["visual_quality"].status == "pass"
    assert blackboard.criteria["content_quality"].status == "pass"
    assert blackboard.action_count == 4

    second_action = blackboard.recent_actions[1]
    assert "visual_quality" in second_action.invalidated_criteria
    assert provider.calls[-1].step_name == "final_audit"
