from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from botpipe.core.discovery import get_workflow_definition
from botpipe.workflows.ad_hoc_executor import AdHocExecutorWorkflow
from botpipe.workflows.adaptive_goal import AdaptiveGoalWorkflow
from botpipe.workflows.adaptive_goal.contracts import (
    ActionRequest,
    Blackboard,
    CapabilityRegistry,
    CapabilitySpec,
    CriterionJudgment,
    CriterionState,
    DeterministicRule,
    MissionCriterion,
    MissionSpec,
    RubricFinding,
    RubricItem,
    VerifierCapabilityResult,
    evaluate_verification,
    fingerprint_paths,
    terminal_unsatisfied_criteria,
    validate_registry_against_mission,
)
from botpipe.workflows.adaptive_goal.verification import _criterion_observed_paths


def _visual_rubric() -> list[RubricItem]:
    return [
        RubricItem(
            id="hierarchy",
            description="Visual hierarchy makes the proposition immediately understandable.",
            importance="gate",
        ),
        RubricItem(
            id="appropriateness",
            description="The design is credible and appropriate for the business.",
            importance="major",
        ),
    ]


def _mission() -> MissionSpec:
    return MissionSpec(
        id="site-redesign",
        objective="Produce a verified redesign.",
        criteria=[
            MissionCriterion(
                id="visual_quality",
                description="Visual quality is genuinely strong.",
                verifier="verify.visual",
                verification_mode="judgment",
                rubric=_visual_rubric(),
                observed_paths=["site/**"],
            ),
            MissionCriterion(
                id="active_business",
                description="Business is currently active.",
                verifier="verify.activity",
                verification_mode="deterministic",
                deterministic_rules=[
                    DeterministicRule(metric="active", operator="truthy")
                ],
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
                description="Judge visual quality against the authored rubric.",
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


def _visual_judgment(
    *,
    verdict: str = "satisfied",
    hierarchy: str = "satisfied",
    appropriateness: str = "satisfied",
    rating: int | None = 4,
) -> CriterionJudgment:
    return CriterionJudgment(
        verdict=verdict,
        summary="Visual rubric evaluated.",
        reasoning="The page was assessed against hierarchy and industry appropriateness.",
        findings=[
            RubricFinding(
                rubric_item_id="hierarchy",
                status=hierarchy,
                reasoning="Hierarchy finding.",
                evidence=["qa/desktop.png"],
            ),
            RubricFinding(
                rubric_item_id="appropriateness",
                status=appropriateness,
                reasoning="Appropriateness finding.",
                evidence=["qa/desktop.png"],
            ),
        ],
        rating=rating,
        confidence="high",
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


def test_judgment_verdict_is_not_derived_from_optional_rating() -> None:
    criterion = _mission().criterion_map()["visual_quality"]

    verdict, _ = evaluate_verification(
        criterion,
        judgment=_visual_judgment(verdict="not_satisfied", rating=5),
        metrics={},
    )
    assert verdict == "fail"

    verdict, _ = evaluate_verification(
        criterion,
        judgment=_visual_judgment(verdict="satisfied", rating=1),
        metrics={},
    )
    assert verdict == "pass"


def test_judgment_requires_complete_rubric_coverage() -> None:
    criterion = _mission().criterion_map()["visual_quality"]
    judgment = _visual_judgment().model_copy(deep=True)
    judgment.findings = judgment.findings[:1]

    verdict, reason = evaluate_verification(
        criterion,
        judgment=judgment,
        metrics={},
    )
    assert verdict == "blocked"
    assert reason is not None and "missing rubric findings" in reason


def test_satisfied_judgment_cannot_contradict_gate_finding() -> None:
    criterion = _mission().criterion_map()["visual_quality"]
    verdict, reason = evaluate_verification(
        criterion,
        judgment=_visual_judgment(
            verdict="satisfied",
            hierarchy="partially_satisfied",
        ),
        metrics={},
    )
    assert verdict == "blocked"
    assert reason is not None and "gate findings" in reason


def test_deterministic_criteria_still_support_true_hard_checks() -> None:
    criterion = _mission().criterion_map()["active_business"]

    verdict, _ = evaluate_verification(
        criterion,
        judgment=None,
        metrics={"active": True},
    )
    assert verdict == "pass"

    verdict, reason = evaluate_verification(
        criterion,
        judgment=None,
        metrics={"active": False},
    )
    assert verdict == "fail"
    assert reason is not None


def test_hybrid_requires_both_judgment_and_hard_check() -> None:
    criterion = MissionCriterion(
        id="mobile_quality",
        description="Mobile experience is qualitatively strong and has no horizontal overflow.",
        verifier="verify.mobile",
        verification_mode="hybrid",
        rubric=[
            RubricItem(
                id="usability",
                description="Mobile layout is coherent and usable.",
                importance="gate",
            )
        ],
        deterministic_rules=[
            DeterministicRule(metric="horizontal_overflow", operator="falsy")
        ],
    )
    judgment = CriterionJudgment(
        verdict="satisfied",
        summary="Mobile experience is strong.",
        reasoning="The rendered mobile layout is coherent.",
        findings=[
            RubricFinding(
                rubric_item_id="usability",
                status="satisfied",
                reasoning="Controls and hierarchy remain usable.",
            )
        ],
    )

    verdict, _ = evaluate_verification(
        criterion,
        judgment=judgment,
        metrics={"horizontal_overflow": False},
    )
    assert verdict == "pass"

    verdict, _ = evaluate_verification(
        criterion,
        judgment=judgment,
        metrics={"horizontal_overflow": True},
    )
    assert verdict == "fail"


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

    result = VerifierCapabilityResult(
        status="evaluated",
        verifier_id="verify.visual",
        summary="checked",
        judgments={"visual_quality": _visual_judgment()},
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
