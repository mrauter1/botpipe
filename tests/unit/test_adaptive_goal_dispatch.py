from __future__ import annotations

import json

from botpipe.workflows.adaptive_goal.contracts import (
    ActionRequest,
    Blackboard,
    CapabilitySpec,
    CriterionJudgment,
    CriterionState,
    MissionCriterion,
    MissionSpec,
    RubricFinding,
    RubricItem,
)
from botpipe.workflows.adaptive_goal.dispatch import _dispatch_message


def _setup():
    criterion = MissionCriterion(
        id="visual_quality",
        description="The current page is visually strong.",
        verifier="verify.visual",
        verification_mode="judgment",
        rubric=[
            RubricItem(
                id="hierarchy",
                description="The page has strong hierarchy.",
                importance="gate",
            )
        ],
    )
    mission = MissionSpec(
        id="dispatch-test",
        objective="Produce a strong page.",
        criteria=[criterion],
    )
    judgment = CriterionJudgment(
        verdict="not_satisfied",
        summary="Hierarchy needs work.",
        reasoning="The hero and secondary cards compete for attention.",
        findings=[
            RubricFinding(
                rubric_item_id="hierarchy",
                status="not_satisfied",
                reasoning="The hero does not dominate the first viewport.",
            )
        ],
        recommended_actions=["Strengthen the hero hierarchy."],
    )
    blackboard = Blackboard(
        mission_id=mission.id,
        criteria={
            "visual_quality": CriterionState(
                status="fail",
                judgment=judgment,
                reason=judgment.reasoning,
                evidence=["qa/desktop.png"],
            )
        },
        started_at="2026-08-31T00:00:00+00:00",
        updated_at="2026-08-31T00:00:00+00:00",
    )
    action_capability = CapabilitySpec(
        id="design",
        kind="action",
        workflow="design_site",
        description="Improve the design.",
        helps=["visual_quality"],
    )
    verifier_capability = CapabilitySpec(
        id="verify.visual",
        kind="verifier",
        workflow="verify_visual",
        description="Judge visual quality.",
        verifies=["visual_quality"],
    )
    return mission, blackboard, action_capability, verifier_capability


def _payload(message: str) -> dict:
    return json.loads(message.split("\n\n", 1)[1])


def test_action_worker_receives_previous_verifier_reasoning() -> None:
    mission, blackboard, capability, _ = _setup()
    action = ActionRequest(
        kind="capability",
        capability_id="design",
        objective="Repair the hierarchy.",
        target_criteria=["visual_quality"],
        rationale="The verifier identified a hierarchy defect.",
    )

    payload = _payload(
        _dispatch_message(
            ctx=None,
            action=action,
            mission=mission,
            blackboard=blackboard,
            capability=capability,
        )
    )
    target = payload["target_criteria"][0]
    assert target["previous_judgment"]["verdict"] == "not_satisfied"
    assert "compete for attention" in target["previous_judgment"]["reasoning"]


def test_reverifier_does_not_receive_previous_judgment() -> None:
    mission, blackboard, _, capability = _setup()
    action = ActionRequest(
        kind="verifier",
        capability_id="verify.visual",
        objective="Judge the current page independently.",
        target_criteria=["visual_quality"],
        rationale="Current verification is stale.",
    )

    payload = _payload(
        _dispatch_message(
            ctx=None,
            action=action,
            mission=mission,
            blackboard=blackboard,
            capability=capability,
        )
    )
    target = payload["target_criteria"][0]
    assert "previous_judgment" not in target
    assert "previous_runtime_reason" not in target
    assert target["rubric"][0]["id"] == "hierarchy"
