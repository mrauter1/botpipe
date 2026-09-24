from __future__ import annotations

import pytest

from labs.workflows.publication_validation import (
    validate_change_candidates,
    validate_company_publication,
    validate_company_task_summaries,
    validate_incident_publication,
    validate_investigation_summary,
    validate_lifecycle_recommendations,
    validate_portfolio_publication,
    validate_release_publication,
    validate_security_child_result,
    validate_security_publication,
)


def investigation_summary(*, ready: bool = True) -> dict[str, object]:
    return {
        "investigation_kind": "security_remediation",
        "authoritative_artifacts": ["evidence_pack", "investigation_summary"],
        "ready_for_downstream_assessment": ready,
        "source_count": 2,
        "finding_count": 1,
        "unresolved_gap_count": 0,
        "key_findings": ["The vulnerable path is reachable."],
    }


def test_release_and_incident_publication_reject_missing_domain_facts() -> None:
    assert validate_release_publication(
        {
            "recommended_decision": "conditional_go",
            "blocking_issue_count": 1,
            "executed_checks": ["unit tests"],
            "unexecuted_checks": ["production smoke"],
        }
    ) == {
        "recommended_decision": "conditional_go",
        "blocking_issue_count": 1,
        "executed_checks": ["unit tests"],
        "unexecuted_checks": ["production smoke"],
    }
    with pytest.raises(ValueError, match="recommended_decision"):
        validate_release_publication({"blocking_issue_count": 0})

    assert (
        validate_incident_publication(
            {
                "recommended_posture": "urgent",
                "primary_hypothesis": "A queue consumer stalled.",
                "hardening_backlog_items": 3,
            }
        )["hardening_backlog_items"]
        == 3
    )
    with pytest.raises(ValueError, match="hardening_backlog_items"):
        validate_incident_publication(
            {
                "recommended_posture": "urgent",
                "primary_hypothesis": "Cause",
                "hardening_backlog_items": -1,
            }
        )


def test_investigation_and_security_publication_keep_readiness_and_counts() -> None:
    evidence = investigation_summary()
    validated = validate_investigation_summary(
        evidence, expected_kind="security_remediation"
    )
    assert validated["source_count"] == 2
    security = validate_security_publication(
        evidence,
        {
            "selected_remediation": "Reject unsigned requests.",
            "verification_ready": True,
            "rollout_ready": False,
            "authoritative_artifacts": ["remediation_plan", "verification_evidence"],
        },
    )
    assert security["selected_remediation"] == "Reject unsigned requests."
    with pytest.raises(ValueError, match="not ready"):
        validate_security_publication(
            investigation_summary(ready=False),
            {
                "selected_remediation": "Fix",
                "verification_ready": True,
                "rollout_ready": True,
                "authoritative_artifacts": ["plan"],
            },
        )


def test_security_child_requires_native_completed_ready_evidence_result() -> None:
    child = {
        "workflow_name": "investigation_request_to_evidence_pack",
        "outcome": "completed",
        "artifact_names": [
            "investigation_scope_brief.md",
            "evidence_pack.md",
            "source_register.json",
            "evidence_gaps.md",
            "investigation_summary.json",
        ],
        "phases": [
            {
                "name": "assemble_evidence_pack",
                "outcome": "accepted",
                "details": {
                    "ready_for_downstream_assessment": True,
                    "source_count": 2,
                    "key_findings": ["Finding"],
                },
            }
        ],
    }
    assert (
        validate_security_child_result(child)["ready_for_downstream_assessment"] is True
    )
    child["phases"][0]["details"]["ready_for_downstream_assessment"] = False  # type: ignore[index]
    with pytest.raises(ValueError, match="not ready"):
        validate_security_child_result(child)


def test_portfolio_validators_enforce_full_coverage_and_scoped_changes() -> None:
    recommendations = [
        {"workflow_name": "alpha", "lifecycle_posture": "keep", "priority": "P2"},
        {"workflow_name": "beta", "lifecycle_posture": "merge", "priority": "P1"},
    ]
    assert validate_lifecycle_recommendations(
        recommendations, allowed_workflows=["alpha", "beta"]
    ) == {"alpha": "keep", "beta": "merge"}
    changes = {
        "change_candidates": [
            {
                "candidate_id": "merge-alpha-beta",
                "action": "merge",
                "priority": "P1",
                "why_now": "They duplicate one another.",
                "evidence_sources": ["run-health"],
                "next_step_hint": "Review the proposed boundary.",
                "workflow_names": ["alpha", "beta"],
            }
        ]
    }
    assert validate_change_candidates(
        changes, analyzed_workflows=["alpha", "beta"]
    ) == ["merge-alpha-beta"]
    with pytest.raises(ValueError, match="at least two"):
        changes["change_candidates"][0]["workflow_names"] = ["alpha"]  # type: ignore[index]
        validate_change_candidates(changes, analyzed_workflows=["alpha", "beta"])


def test_portfolio_publication_rejects_unknown_priority_and_candidate_drift() -> None:
    lifecycle = [
        {"workflow_name": "alpha", "lifecycle_posture": "keep", "priority": "P2"}
    ]
    analysis = {
        "focus_workflows": ["alpha"],
        "analyzed_workflows": ["alpha"],
        "lifecycle_recommendations": lifecycle,
        "change_candidate_ids": ["keep-alpha"],
    }
    candidates = {
        "change_candidates": [
            {
                "candidate_id": "keep-alpha",
                "action": "keep",
                "priority": "P2",
                "why_now": "The workflow remains healthy.",
                "evidence_sources": ["run-health"],
                "next_step_hint": "Review again after more runs.",
                "workflow_names": ["alpha"],
            }
        ]
    }
    summary = {
        "focus_workflows": ["alpha"],
        "analyzed_workflows": ["alpha"],
        "lifecycle_recommendations": lifecycle,
        "governance_posture_counts": {"keep": 1},
        "change_candidate_ids": ["keep-alpha"],
        "priority_workflows": ["alpha"],
        "authoritative_artifacts": [
            "workflow_portfolio_operating_system",
            "portfolio_operating_summary",
            "portfolio_next_actions",
            "portfolio_health_analysis",
            "lifecycle_recommendations",
            "portfolio_change_candidates",
        ],
        "next_action": "A reviewer decides whether to keep the recommendation.",
        "publication_boundary": "operating_system_publication_only",
        "ready_for_publication": True,
    }
    package = {
        **summary,
        "outcome": "accepted",
    }
    assert validate_portfolio_publication(
        summary,
        analysis=analysis,
        package=package,
        change_candidates=candidates,
        allowed_workflows=["alpha"],
        expected_focus_workflows=["alpha"],
    )["change_candidate_ids"] == ["keep-alpha"]

    # Prose is a recommendation, not evidence that another operation executed.
    # The structured publication boundary and recorded runtime operations carry
    # that fact, so a wording pattern must not reject an otherwise valid package.
    summary["next_action"] = "The runtime will automatically launch a review."
    package["next_action"] = summary["next_action"]
    assert validate_portfolio_publication(
        summary,
        analysis=analysis,
        package=package,
        change_candidates=candidates,
        allowed_workflows=["alpha"],
    )["change_candidate_ids"] == ["keep-alpha"]

    summary["priority_workflows"] = ["unknown"]
    package["priority_workflows"] = ["unknown"]
    with pytest.raises(ValueError, match="only to analyzed"):
        validate_portfolio_publication(
            summary,
            analysis=analysis,
            package=package,
            change_candidates=candidates,
            allowed_workflows=["alpha"],
        )


def test_company_validators_reject_unknown_run_and_candidate_references() -> None:
    tasks = [
        {
            "task_id": "task-1",
            "workflow_run_summaries": [{"workflow_name": "alpha"}],
        }
    ]
    assert validate_company_task_summaries(
        tasks, allowed_workflows=["alpha"], focus_workflows=["alpha"]
    ) == ["task-1"]
    tasks[0]["workflow_run_summaries"] = [{"workflow_name": "missing"}]
    with pytest.raises(ValueError, match="unknown workflow"):
        validate_company_task_summaries(
            tasks, allowed_workflows=["alpha"], focus_workflows=["alpha"]
        )


def test_company_publication_rejects_summary_candidate_drift() -> None:
    analysis = {
        "focus_task_ids": ["task-1"],
        "focus_workflows": ["alpha"],
        "candidate_ids": ["candidate-1"],
        "priority_recommendations": [
            {
                "candidate_id": "candidate-1",
                "category": "workflow_package",
                "priority": "P1",
            }
        ],
    }
    candidates = {
        "improvement_candidates": [
            {
                "candidate_id": "candidate-1",
                "category": "workflow_package",
                "priority": "P1",
                "title": "Tighten package validation",
                "why_now": "The failure recurs.",
                "evidence_sources": ["run-1"],
                "next_step_hint": "Open a package refinement task.",
                "workflow_names": ["alpha"],
                "task_ids": ["task-1"],
            }
        ]
    }
    summary = {
        "workflow_name": "company_operation_to_recursive_improvement_cycle",
        "focus_task_ids": ["task-1"],
        "focus_workflows": ["alpha"],
        "candidate_ids": ["candidate-1"],
        "priority_item_ids": ["candidate-1"],
        "priority_categories": ["workflow_package"],
        "priority_category_counts": {"workflow_package": 1},
        "authoritative_artifacts": [
            "recursive_improvement_cycle",
            "recursive_improvement_summary",
            "recursive_improvement_next_actions",
            "company_pressure_map",
            "recursive_improvement_priority_matrix",
            "recursive_improvement_candidates",
        ],
        "next_action": "A reviewer selects the next package refinement.",
        "publication_boundary": "recursive_improvement_publication_only",
        "ready_for_publication": True,
    }
    package = {
        "focus_task_ids": ["task-1"],
        "focus_workflows": ["alpha"],
        "candidate_ids": ["candidate-1"],
        "priority_item_ids": ["candidate-1"],
        "priority_categories": ["workflow_package"],
        "publication_boundary": "recursive_improvement_publication_only",
        "ready_for_publication": True,
    }
    assert validate_company_publication(
        summary, analysis=analysis, package=package, candidates=candidates
    )["candidate_ids"] == ["candidate-1"]
    summary["candidate_ids"] = ["other"]
    with pytest.raises(ValueError, match="candidate_ids"):
        validate_company_publication(
            summary, analysis=analysis, package=package, candidates=candidates
        )

    summary["candidate_ids"] = ["candidate-1"]
    analysis["priority_recommendations"][0]["category"] = "operating_pattern"
    with pytest.raises(ValueError, match="priority categories"):
        validate_company_publication(
            summary, analysis=analysis, package=package, candidates=candidates
        )
