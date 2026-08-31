from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from botpipe.core.discovery import get_workflow_definition
from botpipe.workflows.ad_hoc_executor import AdHocExecutorWorkflow
from botpipe.workflows.adaptive_goal import AdaptiveGoalWorkflow
from botpipe.workflows.adaptive_goal.contracts import (
    AcceptanceRule,
    ActionRequest,
    CapabilityRegistry,
    CapabilitySpec,
    MissionCriterion,
    MissionSpec,
    evaluate_acceptance,
    fingerprint_paths,
    validate_registry_against_mission,
)


def _mission() -> MissionSpec:
    return MissionSpec(
        id="site-redesign",
        objective="Produce a verified redesign.",
        criteria=[
            MissionCriterion(
                id="visual_quality",
                description="Visual quality reaches the target.",
                verifier="verify.visual",
                acceptance=[AcceptanceRule(metric="score", operator="ge", value=85)],
                observed_paths=["site/**"],
            ),
            MissionCriterion(
                id="active_business",
                description="Business is currently active.",
                verifier="verify.activity",
                acceptance=[AcceptanceRule(metric="active", operator="truthy")],
                failure_policy="terminal_unsatisfied",
                ttl_seconds=86400,
            ),
        ],
    )


def _registry() -> CapabilityRegistry:
    return CapabilityRegistry(
        capabilities=[
            CapabilitySpec(
                id="design",
                kind="action",
                workflow="design_site",
                description="Improve the site design.",
                helps=["visual_quality"],
                may_invalidate=["visual_quality"],
                side_effect="workspace",
            ),
            CapabilitySpec(
                id="verify.visual",
                kind="verifier",
                workflow="verify_visual",
                description="Measure visual quality.",
                verifies=["visual_quality"],
                observed_paths=["site/**"],
            ),
            CapabilitySpec(
                id="verify.activity",
                kind="verifier",
                workflow="verify_activity",
                description="Verify current business activity.",
                verifies=["active_business"],
            ),
        ]
    )


def test_registry_must_cover_designated_verifiers() -> None:
    mission = _mission()
    registry = _registry()
    validate_registry_against_mission(mission, registry)

    broken = registry.model_copy(deep=True)
    broken.capabilities = [
        item for item in broken.capabilities if item.id != "verify.activity"
    ]
    with pytest.raises(ValueError, match="unknown verifier"):
        validate_registry_against_mission(mission, broken)


def test_acceptance_is_runtime_owned_and_deterministic() -> None:
    criterion = _mission().criterion_map()["visual_quality"]
    passed, failures = evaluate_acceptance(criterion, {"score": 91})
    assert passed is True
    assert failures == []

    passed, failures = evaluate_acceptance(criterion, {"score": 82})
    assert passed is False
    assert failures
    assert "expected ge 85" in failures[0]


def test_fingerprint_changes_when_observed_subject_changes(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    page = site / "index.html"
    page.write_text("<h1>one</h1>", encoding="utf-8")

    first = fingerprint_paths(tmp_path, ["site/**"])
    assert first is not None

    page.write_text("<h1>two</h1>", encoding="utf-8")
    second = fingerprint_paths(tmp_path, ["site/**"])
    assert second is not None
    assert second != first


def test_fingerprint_changes_when_missing_subject_is_created(tmp_path: Path) -> None:
    first = fingerprint_paths(tmp_path, ["site/**"])
    assert first is not None

    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "index.html").write_text("hello", encoding="utf-8")
    second = fingerprint_paths(tmp_path, ["site/**"])
    assert second != first


def test_action_request_rejects_illegal_capability_shape() -> None:
    with pytest.raises(ValidationError):
        ActionRequest(
            kind="capability",
            objective="Do work",
            rationale="Needed",
            target_criteria=["visual_quality"],
        )

    with pytest.raises(ValidationError):
        ActionRequest(
            kind="ad_hoc",
            capability_id="design",
            objective="Do work",
            rationale="Needed",
            target_criteria=["visual_quality"],
        )


def test_workflow_packages_lower_through_current_botpipe_authoring_surface() -> None:
    # This is intentionally a lightweight contract smoke test. The adaptive
    # implementation must remain above botpipe/core and compile through the
    # ordinary public workflow discovery/lowering path.
    get_workflow_definition(AdaptiveGoalWorkflow)
    get_workflow_definition(AdHocExecutorWorkflow)
