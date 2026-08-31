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
    ActionRequest,
    Blackboard,
    GlobalAuditDecision,
    VerifierCapabilityResult,
)


def _child_result(
    *,
    task_folder: Path,
    workflow_folder: Path,
) -> ChildWorkflowResult:
    run_folder = workflow_folder / "run"
    sessions = run_folder / "sessions"
    raw = run_folder / "raw"
    sessions.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    request_file = run_folder / "request.md"
    request_file.write_text("child", encoding="utf-8")
    return ChildWorkflowResult(
        workflow_name="verify_activity",
        run_id="child-activity",
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


def test_single_orchestrator_blocked_claim_does_not_end_mission(tmp_path: Path) -> None:
    mission = MissionSpec(
        id="blocked-recovery",
        objective="Verify the business is active.",
        criteria=[
            MissionCriterion(
                id="active_business",
                description="The business is active.",
                verifier="verify.activity",
                acceptance=[AcceptanceRule(metric="active", operator="truthy")],
            )
        ],
    )
    registry = CapabilityRegistry(
        capabilities=[
            CapabilitySpec(
                id="verify.activity",
                kind="verifier",
                workflow="verify_activity",
                description="Verify business activity.",
                verifies=["active_business"],
            )
        ]
    )
    blocked_action = ActionRequest(
        kind="blocked",
        objective="No useful action appears available.",
        rationale="The orchestrator is temporarily uncertain.",
    )
    verify_action = ActionRequest(
        kind="verifier",
        capability_id="verify.activity",
        objective="Check current activity evidence.",
        target_criteria=["active_business"],
        rationale="The designated verifier can resolve the uncertainty.",
    )
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(
                raw_output="",
                tag="selected",
                payload=blocked_action.model_dump(mode="json"),
            ),
            Outcome(
                raw_output="",
                tag="selected",
                payload=verify_action.model_dump(mode="json"),
            ),
            Outcome(
                raw_output="",
                tag="audited",
                payload=GlobalAuditDecision(
                    status="complete",
                    summary="The mission is satisfied.",
                ).model_dump(mode="json"),
            ),
        ]
    )

    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()

    def invoke_child(workflow, *, message, parameters=None, input=None):
        assert str(workflow) == "verify_activity"
        child_folder = tmp_path / "child-activity"
        child_folder.mkdir(parents=True, exist_ok=True)
        (child_folder / "verification_result.json").write_text(
            VerifierCapabilityResult(
                status="observed",
                verifier_id="verify.activity",
                summary="Activity verified.",
                observations={"active_business": {"active": True}},
                evidence=["activity-test"],
            ).model_dump_json(indent=2),
            encoding="utf-8",
        )
        return _child_result(
            task_folder=task_folder,
            workflow_folder=child_folder,
        )

    result = Engine(
        AdaptiveGoalWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-blocked",
        run_id="run-blocked",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_input=AdaptiveGoalInput(
            mission=mission,
            registry=registry,
            max_same_action_repeats=3,
        ),
        workflow_invoker=invoke_child,
        max_steps=0,
    )

    assert result.state.status == "complete"
    blackboard = Blackboard.model_validate_json(
        (task_folder / "wf_adaptive_goal" / "blackboard.json").read_text(
            encoding="utf-8"
        )
    )
    assert blackboard.recent_actions[0].outcome == "rejected"
    assert blackboard.action_count == 2
