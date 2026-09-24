"""Pure semantic publication gates shared by imperative labs workflows.

Provider verification is evidence, not the publication gate itself.  These
helpers validate cross-artifact facts before a workflow completes. They accept
plain mappings from typed producer values or JSON artifacts read by a journaled
activity.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

LIFECYCLE_POSTURES = frozenset({"keep", "refine", "decompose", "merge", "retire"})
CHANGE_ACTIONS = frozenset({*LIFECYCLE_POSTURES, "create_next"})
PRIORITY_LEVELS = frozenset({"P1", "P2", "P3"})
PRIORITY_CATEGORIES = frozenset(
    {
        "workflow_portfolio",
        "workflow_package",
        "evaluation_follow_through",
        "refinement_follow_through",
        "decomposition_follow_through",
        "composition_or_escalation_policy",
        "operating_pattern",
    }
)
RELEASE_DECISIONS = frozenset({"go", "conditional_go", "no_go"})
INCIDENT_POSTURES = frozenset({"urgent", "high", "planned"})
PORTFOLIO_AUTHORITATIVE_ARTIFACTS = frozenset(
    {
        "workflow_portfolio_operating_system",
        "portfolio_operating_summary",
        "portfolio_next_actions",
        "portfolio_health_analysis",
        "lifecycle_recommendations",
        "portfolio_change_candidates",
    }
)
COMPANY_AUTHORITATIVE_ARTIFACTS = frozenset(
    {
        "recursive_improvement_cycle",
        "recursive_improvement_summary",
        "recursive_improvement_next_actions",
        "company_pressure_map",
        "recursive_improvement_priority_matrix",
        "recursive_improvement_candidates",
    }
)
def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field} must be a boolean")
    return value


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be an object")
    return value


def _mapping_list(
    value: Any, field: str, *, allow_empty: bool = False
) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field} must be an array of objects")
    result = [_mapping(item, f"{field} entries") for item in value]
    if not result and not allow_empty:
        raise ValueError(f"{field} must not be empty")
    return result


def _string_list(value: Any, field: str, *, allow_empty: bool = False) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field} must be an array of strings")
    result = [_text(item, f"{field} entries") for item in value]
    if not result and not allow_empty:
        raise ValueError(f"{field} must not be empty")
    if len(result) != len(set(result)):
        raise ValueError(f"{field} entries must be unique")
    return result


def _same(actual: Sequence[str], expected: Sequence[str], field: str) -> None:
    if list(actual) != list(expected):
        raise ValueError(f"{field} must match the accepted upstream result")


def _authoritative_subset(
    value: Any, required: frozenset[str], field: str
) -> list[str]:
    artifacts = _string_list(value, field)
    normalized = {item.rsplit(".", 1)[0] for item in artifacts}
    missing = sorted(required - normalized)
    if missing:
        raise ValueError(f"{field} omitted required artifacts: {', '.join(missing)}")
    return artifacts


def validate_release_publication(
    decision_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the final release decision facts required by publication."""

    decision = _text(
        decision_summary.get("recommended_decision"),
        "decision_summary.recommended_decision",
    )
    if decision not in RELEASE_DECISIONS:
        raise ValueError(
            "decision_summary.recommended_decision must be go, conditional_go, or no_go"
        )
    blocking_count = _non_negative_int(
        decision_summary.get("blocking_issue_count"),
        "decision_summary.blocking_issue_count",
    )
    executed = _string_list(
        decision_summary.get("executed_checks"),
        "decision_summary.executed_checks",
        allow_empty=True,
    )
    unexecuted = _string_list(
        decision_summary.get("unexecuted_checks"),
        "decision_summary.unexecuted_checks",
        allow_empty=True,
    )
    return {
        "recommended_decision": decision,
        "blocking_issue_count": blocking_count,
        "executed_checks": executed,
        "unexecuted_checks": unexecuted,
    }


def validate_investigation_summary(
    summary: Mapping[str, Any], *, expected_kind: str
) -> dict[str, Any]:
    """Validate the machine-readable evidence-pack handoff."""

    kind = _text(
        summary.get("investigation_kind"), "investigation_summary.investigation_kind"
    )
    if kind != expected_kind:
        raise ValueError("investigation summary kind must match the invocation")
    authoritative = _string_list(
        summary.get("authoritative_artifacts"),
        "investigation_summary.authoritative_artifacts",
    )
    ready = _boolean(
        summary.get("ready_for_downstream_assessment"),
        "investigation_summary.ready_for_downstream_assessment",
    )
    source_count = _non_negative_int(
        summary.get("source_count"), "investigation_summary.source_count"
    )
    finding_count = _non_negative_int(
        summary.get("finding_count"), "investigation_summary.finding_count"
    )
    gap_count = _non_negative_int(
        summary.get("unresolved_gap_count"),
        "investigation_summary.unresolved_gap_count",
    )
    key_findings = _string_list(
        summary.get("key_findings"), "investigation_summary.key_findings"
    )
    return {
        "investigation_kind": kind,
        "authoritative_artifacts": authoritative,
        "ready_for_downstream_assessment": ready,
        "source_count": source_count,
        "finding_count": finding_count,
        "unresolved_gap_count": gap_count,
        "key_findings": key_findings,
    }


def validate_security_child_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Require a completed, downstream-ready investigation child result."""

    if result.get("workflow_name") != "investigation_request_to_evidence_pack":
        raise ValueError(
            "security evidence child must be investigation_request_to_evidence_pack"
        )
    if result.get("outcome") != "completed":
        raise ValueError("security evidence child must complete")
    raw_artifacts = result.get("artifacts")
    if isinstance(raw_artifacts, Mapping):
        artifact_names = {str(name).rsplit(".", 1)[0] for name in raw_artifacts}
    else:
        artifact_names = {
            name.rsplit(".", 1)[0]
            for name in _string_list(
                result.get("artifact_names"), "security evidence child artifacts"
            )
        }
    required = {
        "investigation_scope_brief",
        "evidence_pack",
        "source_register",
        "evidence_gaps",
        "investigation_summary",
    }
    missing = sorted(required - artifact_names)
    if missing:
        raise ValueError(
            f"security evidence child omitted required artifacts: {', '.join(missing)}"
        )
    phases = _mapping_list(result.get("phases"), "security evidence child phases")
    final = phases[-1]
    if (
        final.get("name") != "assemble_evidence_pack"
        or final.get("outcome") != "accepted"
    ):
        raise ValueError(
            "security evidence child must end with an accepted evidence pack"
        )
    details = _mapping(final.get("details"), "security evidence child final details")
    if not _boolean(
        details.get("ready_for_downstream_assessment"),
        "security evidence child readiness",
    ):
        raise ValueError(
            "security evidence child is not ready for downstream assessment"
        )
    _non_negative_int(
        details.get("source_count"), "security evidence child source_count"
    )
    _string_list(details.get("key_findings"), "security evidence child key_findings")
    return dict(details)


def validate_security_publication(
    evidence_summary: Mapping[str, Any],
    remediation_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate adopted evidence and final remediation facts."""

    evidence = validate_investigation_summary(
        evidence_summary, expected_kind="security_remediation"
    )
    if not evidence["ready_for_downstream_assessment"]:
        raise ValueError(
            "security evidence pack is not ready for downstream assessment"
        )
    selected = _text(
        remediation_summary.get("selected_remediation"),
        "remediation_summary.selected_remediation",
    )
    verification_ready = _boolean(
        remediation_summary.get("verification_ready"),
        "remediation_summary.verification_ready",
    )
    rollout_ready = _boolean(
        remediation_summary.get("rollout_ready"), "remediation_summary.rollout_ready"
    )
    _string_list(
        remediation_summary.get("authoritative_artifacts"),
        "remediation_summary.authoritative_artifacts",
    )
    return {
        "selected_remediation": selected,
        "verification_ready": verification_ready,
        "rollout_ready": rollout_ready,
        **evidence,
    }


def validate_incident_publication(
    incident_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate incident facts required by publication."""

    posture = _text(
        incident_summary.get("recommended_posture"),
        "incident_summary.recommended_posture",
    )
    if posture not in INCIDENT_POSTURES:
        raise ValueError(
            "incident_summary.recommended_posture must be urgent, high, or planned"
        )
    hypothesis = _text(
        incident_summary.get("primary_hypothesis"),
        "incident_summary.primary_hypothesis",
    )
    backlog_items = _non_negative_int(
        incident_summary.get("hardening_backlog_items"),
        "incident_summary.hardening_backlog_items",
    )
    return {
        "recommended_posture": posture,
        "primary_hypothesis": hypothesis,
        "hardening_backlog_items": backlog_items,
    }


def validate_lifecycle_recommendations(
    value: Any,
    *,
    allowed_workflows: Sequence[str],
    field: str = "lifecycle_recommendations",
) -> dict[str, str]:
    """Validate one legal, unique lifecycle posture for every analyzed workflow."""

    allowed = set(_string_list(allowed_workflows, "analyzed_workflows"))
    normalized: dict[str, str] = {}
    for entry in _mapping_list(value, field):
        workflow_name = _text(entry.get("workflow_name"), f"{field}.workflow_name")
        if workflow_name not in allowed:
            raise ValueError(f"{field} must refer only to analyzed workflows")
        if workflow_name in normalized:
            raise ValueError(f"{field} workflow names must be unique")
        posture = _text(entry.get("lifecycle_posture"), f"{field}.lifecycle_posture")
        if posture not in LIFECYCLE_POSTURES:
            raise ValueError(f"{field} contains an illegal lifecycle posture")
        priority = _text(entry.get("priority"), f"{field}.priority")
        if priority not in PRIORITY_LEVELS:
            raise ValueError(f"{field} contains an illegal priority")
        normalized[workflow_name] = posture
    if set(normalized) != allowed:
        raise ValueError(f"{field} must cover every analyzed workflow exactly once")
    return normalized


def validate_change_candidates(
    payload: Mapping[str, Any], *, analyzed_workflows: Sequence[str]
) -> list[str]:
    """Validate scoped portfolio changes without executing them."""

    analyzed = set(_string_list(analyzed_workflows, "analyzed_workflows"))
    candidate_ids: list[str] = []
    for entry in _mapping_list(payload.get("change_candidates"), "change_candidates"):
        candidate_id = _text(
            entry.get("candidate_id"), "change_candidates.candidate_id"
        )
        if candidate_id in candidate_ids:
            raise ValueError("change candidate ids must be unique")
        action = _text(entry.get("action"), "change_candidates.action")
        if action not in CHANGE_ACTIONS:
            raise ValueError("change candidate action is illegal")
        priority = _text(entry.get("priority"), "change_candidates.priority")
        if priority not in PRIORITY_LEVELS:
            raise ValueError("change candidate priority is illegal")
        _text(entry.get("why_now"), "change_candidates.why_now")
        _string_list(
            entry.get("evidence_sources"), "change_candidates.evidence_sources"
        )
        _text(entry.get("next_step_hint"), "change_candidates.next_step_hint")
        if action == "create_next":
            _text(
                entry.get("proposed_workflow_name"),
                "change_candidates.proposed_workflow_name",
            )
        else:
            names = _string_list(
                entry.get("workflow_names"), "change_candidates.workflow_names"
            )
            if not set(names) <= analyzed:
                raise ValueError(
                    "change candidates must refer only to analyzed workflows"
                )
            if action == "merge" and len(names) < 2:
                raise ValueError(
                    "merge change candidates must name at least two workflows"
                )
        candidate_ids.append(candidate_id)
    return candidate_ids


def validate_portfolio_publication(
    summary: Mapping[str, Any],
    *,
    analysis: Mapping[str, Any],
    package: Mapping[str, Any],
    change_candidates: Mapping[str, Any],
    allowed_workflows: Sequence[str] | None = None,
    expected_focus_workflows: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate portfolio analysis, manifest, summary, and package agreement."""

    analyzed = _string_list(
        analysis.get("analyzed_workflows"), "analysis.analyzed_workflows"
    )
    focus = _string_list(analysis.get("focus_workflows"), "analysis.focus_workflows")
    if allowed_workflows is not None and not set(analyzed) <= set(allowed_workflows):
        raise ValueError(
            "analysis.analyzed_workflows includes unknown workflow references"
        )
    if expected_focus_workflows is not None:
        _same(focus, list(expected_focus_workflows), "analysis.focus_workflows")
    postures = validate_lifecycle_recommendations(
        analysis.get("lifecycle_recommendations"),
        allowed_workflows=analyzed,
        field="analysis.lifecycle_recommendations",
    )
    candidate_ids = validate_change_candidates(
        change_candidates, analyzed_workflows=analyzed
    )
    _same(
        candidate_ids,
        _string_list(
            analysis.get("change_candidate_ids"), "analysis.change_candidate_ids"
        ),
        "portfolio change candidate ids",
    )
    _same(
        _string_list(summary.get("focus_workflows"), "summary.focus_workflows"),
        focus,
        "summary.focus_workflows",
    )
    _same(
        _string_list(summary.get("analyzed_workflows"), "summary.analyzed_workflows"),
        analyzed,
        "summary.analyzed_workflows",
    )
    summary_postures = validate_lifecycle_recommendations(
        summary.get("lifecycle_recommendations"),
        allowed_workflows=analyzed,
        field="summary.lifecycle_recommendations",
    )
    if summary_postures != postures:
        raise ValueError(
            "portfolio summary lifecycle recommendations drifted from analysis"
        )
    counts = _mapping(
        summary.get("governance_posture_counts"), "summary.governance_posture_counts"
    )
    normalized_counts = {
        str(key): _non_negative_int(value, "summary.governance_posture_counts")
        for key, value in counts.items()
    }
    if normalized_counts != dict(sorted(Counter(postures.values()).items())):
        raise ValueError(
            "portfolio summary posture counts drifted from lifecycle recommendations"
        )
    _same(
        _string_list(
            summary.get("change_candidate_ids"), "summary.change_candidate_ids"
        ),
        candidate_ids,
        "summary.change_candidate_ids",
    )
    priority_workflows = _string_list(
        summary.get("priority_workflows"), "summary.priority_workflows"
    )
    if not set(priority_workflows) <= set(analyzed):
        raise ValueError(
            "summary.priority_workflows must refer only to analyzed workflows"
        )
    _authoritative_subset(
        summary.get("authoritative_artifacts"),
        PORTFOLIO_AUTHORITATIVE_ARTIFACTS,
        "summary.authoritative_artifacts",
    )
    _text(summary.get("next_action"), "summary.next_action")
    for field in (
        "focus_workflows",
        "analyzed_workflows",
        "change_candidate_ids",
        "priority_workflows",
    ):
        _same(
            _string_list(package.get(field), f"package.{field}"),
            _string_list(summary.get(field), f"summary.{field}"),
            f"package.{field}",
        )
    if (
        _text(summary.get("publication_boundary"), "summary.publication_boundary")
        != "operating_system_publication_only"
    ):
        raise ValueError("portfolio publication boundary is invalid")
    if (
        _text(package.get("publication_boundary"), "package.publication_boundary")
        != "operating_system_publication_only"
    ):
        raise ValueError("portfolio package publication boundary is invalid")
    if not _boolean(
        summary.get("ready_for_publication"), "summary.ready_for_publication"
    ):
        raise ValueError("portfolio summary is not ready for publication")
    if not _boolean(
        package.get("ready_for_publication"), "package.ready_for_publication"
    ):
        raise ValueError("portfolio package is not ready for publication")
    return {
        "analyzed_workflows": analyzed,
        "lifecycle_postures": postures,
        "change_candidate_ids": candidate_ids,
    }


def validate_company_task_summaries(
    tasks: Any,
    *,
    allowed_workflows: Sequence[str],
    focus_workflows: Sequence[str] | None,
) -> list[str]:
    """Validate captured company tasks and their scoped per-workflow run summaries."""

    allowed = set(allowed_workflows)
    expected = list(focus_workflows) if focus_workflows is not None else None
    task_ids: list[str] = []
    for task in _mapping_list(tasks, "company tasks"):
        task_id = _text(task.get("task_id"), "company tasks.task_id")
        if task_id in task_ids:
            raise ValueError("company task ids must be unique")
        task_ids.append(task_id)
        summaries = _mapping_list(
            task.get("workflow_run_summaries"),
            "workflow_run_summaries",
            allow_empty=True,
        )
        names = [
            _text(item.get("workflow_name"), "workflow_run_summaries.workflow_name")
            for item in summaries
        ]
        if len(names) != len(set(names)):
            raise ValueError("workflow summary names must be unique within each task")
        if not set(names) <= allowed:
            raise ValueError("workflow summaries include unknown workflow references")
        if expected is not None and names != expected:
            raise ValueError(
                "workflow summaries must match the scoped workflow set for every task"
            )
    return task_ids


def validate_priority_recommendations(
    value: Any,
    *,
    allowed_candidate_ids: Sequence[str],
    field: str = "priority_recommendations",
) -> tuple[list[str], list[str]]:
    """Validate an ordered, exhaustive priority recommendation list."""

    allowed = list(_string_list(allowed_candidate_ids, "candidate_ids"))
    candidate_ids: list[str] = []
    categories: list[str] = []
    for entry in _mapping_list(value, field):
        candidate_id = _text(entry.get("candidate_id"), f"{field}.candidate_id")
        if candidate_id not in allowed or candidate_id in candidate_ids:
            raise ValueError(
                f"{field} candidate ids must be unique and drawn from candidate_ids"
            )
        category = _text(entry.get("category"), f"{field}.category")
        if category not in PRIORITY_CATEGORIES:
            raise ValueError(f"{field} contains an illegal priority category")
        priority = _text(entry.get("priority"), f"{field}.priority")
        if priority not in PRIORITY_LEVELS:
            raise ValueError(f"{field} contains an illegal priority")
        candidate_ids.append(candidate_id)
        if category not in categories:
            categories.append(category)
    if candidate_ids != allowed:
        raise ValueError(f"{field} must cover candidate_ids exactly once in order")
    return candidate_ids, categories


def validate_improvement_candidates(
    payload: Mapping[str, Any],
    *,
    allowed_workflows: Sequence[str],
    allowed_tasks: Sequence[str],
) -> tuple[list[str], list[str], dict[str, int]]:
    """Validate company improvement candidates and all workflow/task references."""

    workflow_set = set(allowed_workflows)
    task_set = set(allowed_tasks)
    candidate_ids: list[str] = []
    categories: list[str] = []
    counts: Counter[str] = Counter()
    for entry in _mapping_list(
        payload.get("improvement_candidates"), "improvement_candidates"
    ):
        candidate_id = _text(
            entry.get("candidate_id"), "improvement_candidates.candidate_id"
        )
        if candidate_id in candidate_ids:
            raise ValueError("improvement candidate ids must be unique")
        category = _text(entry.get("category"), "improvement_candidates.category")
        if category not in PRIORITY_CATEGORIES:
            raise ValueError("improvement candidate category is illegal")
        priority = _text(entry.get("priority"), "improvement_candidates.priority")
        if priority not in PRIORITY_LEVELS:
            raise ValueError("improvement candidate priority is illegal")
        _text(entry.get("title"), "improvement_candidates.title")
        _text(entry.get("why_now"), "improvement_candidates.why_now")
        _string_list(
            entry.get("evidence_sources"), "improvement_candidates.evidence_sources"
        )
        _text(entry.get("next_step_hint"), "improvement_candidates.next_step_hint")
        workflows = _string_list(
            entry.get("workflow_names", []),
            "improvement_candidates.workflow_names",
            allow_empty=True,
        )
        tasks = _string_list(
            entry.get("task_ids", []),
            "improvement_candidates.task_ids",
            allow_empty=True,
        )
        if not workflows and not tasks:
            raise ValueError(
                "improvement candidates must name workflow_names, task_ids, or both"
            )
        if not set(workflows) <= workflow_set:
            raise ValueError(
                "improvement candidates refer to workflows outside the scoped set"
            )
        if not set(tasks) <= task_set:
            raise ValueError(
                "improvement candidates refer to tasks outside the scoped set"
            )
        candidate_ids.append(candidate_id)
        if category not in categories:
            categories.append(category)
        counts[category] += 1
    return candidate_ids, categories, dict(sorted(counts.items()))


def validate_company_publication(
    summary: Mapping[str, Any],
    *,
    analysis: Mapping[str, Any],
    package: Mapping[str, Any],
    candidates: Mapping[str, Any],
    allowed_workflows: Sequence[str] | None = None,
    expected_focus_workflows: Sequence[str] | None = None,
    expected_focus_task_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate recursive-improvement analysis, manifest, summary, and package."""

    task_ids = _string_list(analysis.get("focus_task_ids"), "analysis.focus_task_ids")
    workflows = _string_list(
        analysis.get("focus_workflows"), "analysis.focus_workflows"
    )
    if allowed_workflows is not None and not set(workflows) <= set(allowed_workflows):
        raise ValueError(
            "analysis.focus_workflows includes unknown workflow references"
        )
    if expected_focus_workflows is not None:
        _same(workflows, list(expected_focus_workflows), "analysis.focus_workflows")
    if expected_focus_task_ids is not None:
        _same(task_ids, list(expected_focus_task_ids), "analysis.focus_task_ids")
    analyzed_candidates = _string_list(
        analysis.get("candidate_ids"), "analysis.candidate_ids"
    )
    priority_ids, priority_categories = validate_priority_recommendations(
        analysis.get("priority_recommendations"),
        allowed_candidate_ids=analyzed_candidates,
    )
    candidate_ids, categories, counts = validate_improvement_candidates(
        candidates, allowed_workflows=workflows, allowed_tasks=task_ids
    )
    _same(candidate_ids, analyzed_candidates, "improvement_candidates candidate ids")
    _same(categories, priority_categories, "improvement candidate priority categories")
    _same(
        _string_list(summary.get("focus_task_ids"), "summary.focus_task_ids"),
        task_ids,
        "summary.focus_task_ids",
    )
    _same(
        _string_list(summary.get("focus_workflows"), "summary.focus_workflows"),
        workflows,
        "summary.focus_workflows",
    )
    _same(
        _string_list(summary.get("candidate_ids"), "summary.candidate_ids"),
        candidate_ids,
        "summary.candidate_ids",
    )
    _same(
        _string_list(summary.get("priority_item_ids"), "summary.priority_item_ids"),
        priority_ids,
        "summary.priority_item_ids",
    )
    _same(
        _string_list(summary.get("priority_categories"), "summary.priority_categories"),
        categories,
        "summary.priority_categories",
    )
    raw_counts = _mapping(
        summary.get("priority_category_counts"), "summary.priority_category_counts"
    )
    summary_counts = {
        str(key): _non_negative_int(value, "summary.priority_category_counts")
        for key, value in raw_counts.items()
    }
    if summary_counts != counts:
        raise ValueError(
            "recursive improvement summary category counts drifted from candidates"
        )
    _authoritative_subset(
        summary.get("authoritative_artifacts"),
        COMPANY_AUTHORITATIVE_ARTIFACTS,
        "summary.authoritative_artifacts",
    )
    _text(summary.get("next_action"), "summary.next_action")
    if (
        _text(summary.get("workflow_name"), "summary.workflow_name")
        != "company_operation_to_recursive_improvement_cycle"
    ):
        raise ValueError("recursive improvement summary workflow_name is invalid")
    for field, expected in (
        ("focus_task_ids", task_ids),
        ("focus_workflows", workflows),
        ("candidate_ids", candidate_ids),
        ("priority_item_ids", priority_ids),
        ("priority_categories", priority_categories),
    ):
        _same(
            _string_list(package.get(field), f"package.{field}"),
            expected,
            f"package.{field}",
        )
    if (
        _text(summary.get("publication_boundary"), "summary.publication_boundary")
        != "recursive_improvement_publication_only"
    ):
        raise ValueError("recursive improvement publication boundary is invalid")
    if (
        _text(package.get("publication_boundary"), "package.publication_boundary")
        != "recursive_improvement_publication_only"
    ):
        raise ValueError("recursive improvement package boundary is invalid")
    if not _boolean(
        summary.get("ready_for_publication"), "summary.ready_for_publication"
    ):
        raise ValueError("recursive improvement summary is not ready for publication")
    if not _boolean(
        package.get("ready_for_publication"), "package.ready_for_publication"
    ):
        raise ValueError("recursive improvement package is not ready for publication")
    return {
        "focus_task_ids": task_ids,
        "focus_workflows": workflows,
        "candidate_ids": candidate_ids,
        "priority_categories": categories,
        "priority_category_counts": counts,
    }


__all__ = [
    "validate_change_candidates",
    "validate_company_publication",
    "validate_company_task_summaries",
    "validate_improvement_candidates",
    "validate_incident_publication",
    "validate_investigation_summary",
    "validate_lifecycle_recommendations",
    "validate_portfolio_publication",
    "validate_priority_recommendations",
    "validate_release_publication",
    "validate_security_child_result",
    "validate_security_publication",
]
