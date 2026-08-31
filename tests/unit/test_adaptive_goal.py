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
    Blackboard,
    CapabilityRegistry,
    CapabilitySpec,
    CriterionState,
    MissionCriterion,
    MissionSpec,
    evaluate_acceptance,
    fingerprint_paths,
    terminal_unsatisfied_criteria,
    validate_registry_against_mission,
)
from botpipe.workflows.adaptive_goal.verification import _criterion_observed_paths


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
    get_workflow_definition(AdaptiveGoalWorkflow)
    get_workflow_definition(AdHocExecutorWorkflow)


def test_directory_observed_pattern_hashes_nested_files(tmp_path: Path) -> None:
    nested = tmp_path / "site" / "assets" / "css"
    nested.mkdir(parents=True)
    target = nested / "main.css"
    target.write_text("body { color: black; }", encoding="utf-8")

    first = fingerprint_paths(tmp_path, ["site/**"])
    target.write_text("body { color: white; }", encoding="utf-8")
    second = fingerprint_paths(tmp_path, ["site/**"])

    assert first != second


def test_fingerprint_ignores_symlink_that_escapes_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("one", encoding="utf-8")
    link_dir = tmp_path / "site"
    link_dir.mkdir()
    link = link_dir / "outside.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")

    first = fingerprint_paths(tmp_path, ["site/**"])
    outside.write_text("two", encoding="utf-8")
    second = fingerprint_paths(tmp_path, ["site/**"])

    assert first == second


def test_verifier_may_broaden_but_not_narrow_operator_observed_paths() -> None:
    mission = _mission()
    criterion = mission.criterion_map()["visual_quality"]
    capability = _registry().capability_map()["verify.visual"]

    from botpipe.workflows.adaptive_goal.contracts import VerifierCapabilityResult

    result = VerifierCapabilityResult(
        status="observed",
        verifier_id="verify.visual",
        summary="checked",
        observations={"visual_quality": {"score": 90}},
        observed_paths={"visual_quality": ["site/index.html"]},
    )

    observed = _criterion_observed_paths(
        criterion=criterion,
        capability=capability,
        verifier_result=result,
    )
    assert "site/**" in observed
    assert "site/index.html" in observed


def test_terminal_unsatisfied_policy_is_distinct_from_repairable_failure() -> None:
    mission = _mission()
    now = "2026-08-30T00:00:00+00:00"
    blackboard = Blackboard(
        mission_id=mission.id,
        criteria={
            "visual_quality": CriterionState(status="fail"),
            "active_business": CriterionState(status="fail"),
        },
        started_at=now,
        updated_at=now,
    )

    assert terminal_unsatisfied_criteria(mission, blackboard) == ["active_business"]
