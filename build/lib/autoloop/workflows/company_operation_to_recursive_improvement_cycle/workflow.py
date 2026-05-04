"""Workflow package for company-level recursive improvement."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from typing import Any

from pydantic import BaseModel, Field

from autoloop_optimizer import (
    write_company_operation_snapshot,
    write_workflow_capability_snapshot,
    write_workflow_portfolio_health_snapshot,
)
from autoloop.stdlib import (
    extract_workflow_names_from_capability_snapshot,
    extract_workflow_names_from_portfolio_health,
    normalize_optional_string,
    normalize_unique_strings,
    read_json_object,
    read_required_text,
    require_existing_artifact_paths,
    require_mapping,
    require_mapping_list,
    require_non_empty_string,
    require_positive_int,
    require_string_list,
    require_true_flag,
    require_unique_values,
    validate_authoritative_artifact_subset,
    validate_no_hidden_execution_signal,
    validate_publication_boundary,
)
from autoloop.stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from autoloop import Event, FINISH, Outcome, Prompt, Session, Workflow, produce_verify_step, python_step
from autoloop.core import Artifact

from .contracts import (
    ANALYZE_RECURSIVE_IMPROVEMENT_ROUTE_CONTRACTS,
    FRAME_COMPANY_OPERATION_ROUTE_CONTRACTS,
    PACKAGE_RECURSIVE_IMPROVEMENT_CYCLE_ROUTE_CONTRACTS,
    CompanyOperationFramingPayload,
    RECURSIVE_IMPROVEMENT_SUMMARY_ARTIFACT,
    RecursiveImprovementAnalysisPayload,
    RecursiveImprovementCyclePayload,
)


_ALLOWED_PRIORITY_LEVELS = frozenset({"P1", "P2", "P3"})
_ALLOWED_PRIORITY_CATEGORIES = frozenset(
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
_AUTHORITATIVE_PACKAGE_ARTIFACTS = frozenset(
    {
        "recursive_improvement_cycle",
        "recursive_improvement_summary",
        "recursive_improvement_next_actions",
        "company_pressure_map",
        "recursive_improvement_priority_matrix",
        "recursive_improvement_candidates",
    }
)
_PACKAGE_SECTION_MARKERS = (
    "## Workflow Portfolio",
    "## Workflow Packages",
    "## Evaluation / Refinement / Decomposition Follow-Through",
    "## Composition / Escalation Policy",
    "## Operating Patterns",
    "## Publication Boundary",
)
_PUBLICATION_BOUNDARY = "recursive_improvement_publication_only"


def _after_frame_company_operation(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    focus_task_ids = _require_string_list(
        payload.get("focus_task_ids"),
        "frame verifier payload must define focus_task_ids as a non-empty string list",
    )
    if ctx.state.scoped_task_ids and focus_task_ids != ctx.state.scoped_task_ids:
        raise ValueError("frame verifier payload focus_task_ids must match the captured company context")
    focus_workflows = _require_string_list(
        payload.get("focus_workflows"),
        "frame verifier payload must define focus_workflows as a non-empty string list",
    )
    if ctx.state.focus_workflows and focus_workflows != ctx.state.focus_workflows:
        raise ValueError("frame verifier payload focus_workflows must match the captured company context")
    ctx.state.framing_status = outcome.tag
    return None


def _after_analyze_recursive_improvement_pressures(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    focus_task_ids = _require_string_list(
        payload.get("focus_task_ids"),
        "analysis verifier payload must define focus_task_ids as a non-empty string list",
    )
    if ctx.state.scoped_task_ids and focus_task_ids != ctx.state.scoped_task_ids:
        raise ValueError("analysis verifier payload focus_task_ids must match the captured company context")
    focus_workflows = _require_string_list(
        payload.get("focus_workflows"),
        "analysis verifier payload must define focus_workflows as a non-empty string list",
    )
    if ctx.state.focus_workflows and focus_workflows != ctx.state.focus_workflows:
        raise ValueError("analysis verifier payload focus_workflows must match the captured company context")
    candidate_ids = _require_string_list(
        payload.get("candidate_ids"),
        "analysis verifier payload must define candidate_ids as a non-empty string list",
    )
    priority_item_ids, priority_categories = _validated_priority_recommendations(
        payload.get("priority_recommendations"),
        allowed_candidate_ids=candidate_ids,
        error_prefix="analysis verifier payload",
    )
    ctx.state.analysis_status = outcome.tag
    ctx.state.candidate_ids = candidate_ids
    ctx.state.priority_item_ids = priority_item_ids
    ctx.state.priority_categories = priority_categories
    return None


def _after_package_recursive_improvement_cycle(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    focus_task_ids = _require_string_list(
        payload.get("focus_task_ids"),
        "package verifier payload must define focus_task_ids as a non-empty string list",
    )
    if ctx.state.scoped_task_ids and focus_task_ids != ctx.state.scoped_task_ids:
        raise ValueError("package verifier payload focus_task_ids must match the captured company context")
    focus_workflows = _require_string_list(
        payload.get("focus_workflows"),
        "package verifier payload must define focus_workflows as a non-empty string list",
    )
    if ctx.state.focus_workflows and focus_workflows != ctx.state.focus_workflows:
        raise ValueError("package verifier payload focus_workflows must match the captured company context")
    candidate_ids = _require_string_list(
        payload.get("candidate_ids"),
        "package verifier payload must define candidate_ids as a non-empty string list",
    )
    if ctx.state.candidate_ids and candidate_ids != ctx.state.candidate_ids:
        raise ValueError("package verifier payload candidate_ids must match the analyzed recursive-improvement context")
    priority_item_ids = _require_string_list(
        payload.get("priority_item_ids"),
        "package verifier payload must define priority_item_ids as a non-empty string list",
    )
    if ctx.state.priority_item_ids and priority_item_ids != ctx.state.priority_item_ids:
        raise ValueError(
            "package verifier payload priority_item_ids must match the analyzed recursive-improvement context"
        )
    priority_categories = _require_priority_category_list(
        payload.get("priority_categories"),
        "package verifier payload must define priority_categories as a non-empty string list",
    )
    if ctx.state.priority_categories and priority_categories != ctx.state.priority_categories:
        raise ValueError(
            "package verifier payload priority_categories must match the analyzed recursive-improvement context"
        )
    ctx.state.packaging_status = outcome.tag
    return None


class CompanyOperationToRecursiveImprovementCycle(Workflow):
    """Turn company work history plus workflow telemetry into a next-cycle package."""

    name = "company_operation_to_recursive_improvement_cycle"

    class State(BaseModel):
        task_title: str = ""
        sponsor_role: str | None = None
        desired_outcome: str | None = None
        decision_drivers: list[str] = Field(default_factory=list)
        constraints: list[str] = Field(default_factory=list)
        focus_task_references: list[str] = Field(default_factory=list)
        focus_workflow_references: list[str] = Field(default_factory=list)
        statuses: list[str] = Field(default_factory=list)
        max_tasks: int = 25
        max_runs_per_workflow: int = 10
        max_messages_per_task: int = 5
        scoped_task_ids: list[str] = Field(default_factory=list)
        focus_workflows: list[str] = Field(default_factory=list)
        framing_status: str | None = None
        analysis_status: str | None = None
        packaging_status: str | None = None
        candidate_ids: list[str] = Field(default_factory=list)
        priority_item_ids: list[str] = Field(default_factory=list)
        priority_categories: list[str] = Field(default_factory=list)
        published: bool = False

    frame_session = Session()
    analysis_session = Session()
    package_session = Session()

    request = Artifact("{run_folder}/request.md")
    framework_architecture_doc = Artifact("{package_folder}/../../../docs/architecture.md")
    framework_authoring_doc = Artifact("{package_folder}/../../../docs/authoring.md")
    workflow_instructions = Artifact("{package_folder}/../../../Workflow_Instructions.md")
    recursive_improvement_cycle_checklist = Artifact("{package_folder}/assets/recursive_improvement_cycle_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json")
    workflow_capability_snapshot = Artifact("{workflow_folder}/workflow_capability_snapshot.json")
    workflow_portfolio_health_snapshot = Artifact("{workflow_folder}/workflow_portfolio_health_snapshot.json")
    company_operation_snapshot = Artifact("{workflow_folder}/company_operation_snapshot.json")
    company_operation_brief = Artifact("{workflow_folder}/company_operation_brief.md")
    recursive_improvement_criteria = Artifact("{workflow_folder}/recursive_improvement_criteria.md")
    company_pressure_map = Artifact("{workflow_folder}/company_pressure_map.md")
    recursive_improvement_priority_matrix = Artifact("{workflow_folder}/recursive_improvement_priority_matrix.md")
    recursive_improvement_candidates = Artifact("{workflow_folder}/recursive_improvement_candidates.json")
    recursive_improvement_cycle = Artifact("{workflow_folder}/recursive_improvement_cycle.md")
    recursive_improvement_summary = Artifact("{workflow_folder}/recursive_improvement_summary.json")
    recursive_improvement_next_actions = Artifact("{workflow_folder}/recursive_improvement_next_actions.md")
    recursive_improvement_cycle_receipt = Artifact("{workflow_folder}/recursive_improvement_cycle_receipt.json")

    frame_company_operation = produce_verify_step(
        producer_prompt=Prompt.file("prompts/frame_producer.md"),
        verifier_prompt=Prompt.file("prompts/frame_verifier.md"),
        session=frame_session,
        requires=[
            request,
            invocation_contract,
            workflow_capability_snapshot,
            workflow_portfolio_health_snapshot,
            company_operation_snapshot,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        producer_writes=[company_operation_brief, recursive_improvement_criteria],
        control_schema=CompanyOperationFramingPayload,
        routes=FRAME_COMPANY_OPERATION_ROUTE_CONTRACTS,
        after_verifier=_after_frame_company_operation,
    )
    analyze_recursive_improvement_pressures = produce_verify_step(
        producer_prompt=Prompt.file("prompts/analyze_producer.md"),
        verifier_prompt=Prompt.file("prompts/analyze_verifier.md"),
        session=analysis_session,
        requires=[
            request,
            invocation_contract,
            workflow_capability_snapshot,
            workflow_portfolio_health_snapshot,
            company_operation_snapshot,
            company_operation_brief,
            recursive_improvement_criteria,
        ],
        producer_writes=[
            company_pressure_map,
            recursive_improvement_priority_matrix,
            recursive_improvement_candidates,
        ],
        control_schema=RecursiveImprovementAnalysisPayload,
        routes=ANALYZE_RECURSIVE_IMPROVEMENT_ROUTE_CONTRACTS,
        after_verifier=_after_analyze_recursive_improvement_pressures,
    )
    package_recursive_improvement_cycle = produce_verify_step(
        producer_prompt=Prompt.file("prompts/package_producer.md"),
        verifier_prompt=Prompt.file("prompts/package_verifier.md"),
        session=package_session,
        requires=[
            request,
            invocation_contract,
            workflow_capability_snapshot,
            workflow_portfolio_health_snapshot,
            company_operation_snapshot,
            recursive_improvement_cycle_checklist,
            company_operation_brief,
            recursive_improvement_criteria,
            company_pressure_map,
            recursive_improvement_priority_matrix,
            recursive_improvement_candidates,
        ],
        producer_writes=[
            recursive_improvement_cycle,
            recursive_improvement_summary,
            recursive_improvement_next_actions,
        ],
        control_schema=RecursiveImprovementCyclePayload,
        routes=PACKAGE_RECURSIVE_IMPROVEMENT_CYCLE_ROUTE_CONTRACTS,
        after_verifier=_after_package_recursive_improvement_cycle,
    )

    @python_step(
        name="bootstrap",
        requires=[request],
        writes=[invocation_contract],
        routes={"inputs_prepared": "capture_company_operation_context"},
    )
    def bootstrap(ctx):
        params = ctx.params
        next_state = ctx.state.model_copy(
            update={
                "task_title": params.task_title,
                "sponsor_role": params.sponsor_role,
                "desired_outcome": params.desired_outcome,
                "decision_drivers": list(params.decision_drivers),
                "constraints": list(params.constraints),
                "focus_task_references": list(params.focus_tasks),
                "focus_workflow_references": list(params.focus_workflows),
                "statuses": list(params.statuses),
                "max_tasks": params.max_tasks,
                "max_runs_per_workflow": params.max_runs_per_workflow,
                "max_messages_per_task": params.max_messages_per_task,
                "scoped_task_ids": [],
                "focus_workflows": [],
                "framing_status": None,
                "analysis_status": None,
                "packaging_status": None,
                "candidate_ids": [],
                "priority_item_ids": [],
                "priority_categories": [],
                "published": False,
            }
        )
        open_workflow_sessions(ctx, "frame_session", "analysis_session", "package_session")
        write_invocation_contract(
            ctx,
            {
                "task_title": next_state.task_title,
                "sponsor_role": next_state.sponsor_role,
                "desired_outcome": next_state.desired_outcome,
                "decision_drivers": next_state.decision_drivers,
                "constraints": next_state.constraints,
                "focus_task_references": next_state.focus_task_references or None,
                "focus_workflow_references": next_state.focus_workflow_references or None,
                "statuses": next_state.statuses or None,
                "max_tasks": next_state.max_tasks,
                "max_runs_per_workflow": next_state.max_runs_per_workflow,
                "max_messages_per_task": next_state.max_messages_per_task,
            },
        )
        ctx.state = next_state
        return "inputs_prepared"

    @python_step(
        name="capture_company_operation_context",
        requires=[request, invocation_contract],
        writes=[
            workflow_capability_snapshot,
            workflow_portfolio_health_snapshot,
            company_operation_snapshot,
        ],
        routes={"company_operation_context_captured": "frame_company_operation"},
    )
    def capture_company_operation_context(ctx):
        capability_path = write_workflow_capability_snapshot(ctx)
        health_path = write_workflow_portfolio_health_snapshot(
            ctx,
            workflows=ctx.state.focus_workflow_references or None,
            statuses=ctx.state.statuses or None,
            max_runs_per_workflow=ctx.state.max_runs_per_workflow,
        )
        company_path = write_company_operation_snapshot(
            ctx,
            task_ids=ctx.state.focus_task_references or None,
            workflows=ctx.state.focus_workflow_references or None,
            statuses=ctx.state.statuses or None,
            max_tasks=ctx.state.max_tasks,
            max_runs_per_workflow=ctx.state.max_runs_per_workflow,
            max_messages_per_task=ctx.state.max_messages_per_task,
        )
        for artifact_path in (capability_path, health_path, company_path):
            if not artifact_path.exists():
                raise FileNotFoundError(f"required context artifact was not written at {artifact_path}")

        capability_snapshot = _read_json(capability_path)
        workflow_count = capability_snapshot.get("workflow_count")
        if not isinstance(workflow_count, int) or workflow_count < 1:
            raise ValueError("workflow_capability_snapshot.json must define a positive workflow_count")
        capability_workflow_names = extract_workflow_names_from_capability_snapshot(capability_snapshot)

        health_snapshot = _read_json(health_path)
        health_payload = _require_mapping(
            health_snapshot.get("workflow_portfolio_health"),
            "workflow_portfolio_health_snapshot.json must define workflow_portfolio_health as a JSON object",
        )
        if health_payload.get("max_runs_per_workflow") != ctx.state.max_runs_per_workflow:
            raise ValueError("workflow_portfolio_health_snapshot.json max_runs_per_workflow must match the invocation contract")
        expected_statuses = _sorted_unique_strings(ctx.state.statuses) or None
        if health_payload.get("statuses") != expected_statuses:
            raise ValueError("workflow_portfolio_health_snapshot.json statuses must match the invocation contract")
        scoped_workflow_names = extract_workflow_names_from_portfolio_health(health_payload)
        if not scoped_workflow_names:
            raise ValueError("workflow_portfolio_health_snapshot.json must contain at least one scoped workflow")
        if health_payload.get("workflow_count") != len(scoped_workflow_names):
            raise ValueError("workflow_portfolio_health_snapshot.json workflow_count must match the scoped workflow entries")
        if ctx.state.focus_workflow_references:
            selected_workflow_names = _require_string_list(
                health_payload.get("selected_workflow_names"),
                "workflow_portfolio_health_snapshot.json must define selected_workflow_names when focus_workflow_references are supplied",
            )
            if selected_workflow_names != scoped_workflow_names:
                raise ValueError(
                    "workflow_portfolio_health_snapshot.json selected_workflow_names must match the scoped workflow entries"
                )
        unknown_workflows = sorted(set(scoped_workflow_names) - capability_workflow_names)
        if unknown_workflows:
            raise ValueError("workflow_portfolio_health_snapshot.json includes unknown focus-workflow references")

        company_snapshot = _read_json(company_path)
        company_payload = _require_mapping(
            company_snapshot.get("company_operation"),
            "company_operation_snapshot.json must define company_operation as a JSON object",
        )
        if company_payload.get("max_tasks") != ctx.state.max_tasks:
            raise ValueError("company_operation_snapshot.json max_tasks must match the invocation contract")
        if company_payload.get("max_runs_per_workflow") != ctx.state.max_runs_per_workflow:
            raise ValueError("company_operation_snapshot.json max_runs_per_workflow must match the invocation contract")
        if company_payload.get("max_messages_per_task") != ctx.state.max_messages_per_task:
            raise ValueError("company_operation_snapshot.json max_messages_per_task must match the invocation contract")
        if company_payload.get("statuses") != expected_statuses:
            raise ValueError("company_operation_snapshot.json statuses must match the invocation contract")
        if ctx.state.focus_task_references:
            selected_task_ids = _require_string_list(
                company_payload.get("selected_task_ids"),
                "company_operation_snapshot.json must define selected_task_ids when focus_task_references are supplied",
            )
            if selected_task_ids != _sorted_unique_strings(ctx.state.focus_task_references):
                raise ValueError("company_operation_snapshot.json selected_task_ids must match the scoped task references")
        if ctx.state.focus_workflow_references:
            selected_company_workflow_names = _require_string_list(
                company_payload.get("selected_workflow_names"),
                "company_operation_snapshot.json must define selected_workflow_names when focus_workflow_references are supplied",
            )
            if selected_company_workflow_names != scoped_workflow_names:
                raise ValueError("company_operation_snapshot.json selected_workflow_names must match the scoped workflow entries")
        company_tasks = _require_mapping_list(
            company_payload.get("tasks"),
            "company_operation_snapshot.json must define company_operation.tasks as a JSON array of objects",
        )
        scoped_task_ids = _extract_company_task_ids(company_tasks)
        _validate_company_task_summaries(
            company_tasks,
            allowed_workflows=capability_workflow_names,
            focus_workflows=scoped_workflow_names if ctx.state.focus_workflow_references else None,
        )
        if ctx.state.focus_task_references:
            unknown_task_refs = sorted(set(scoped_task_ids) - set(_sorted_unique_strings(ctx.state.focus_task_references)))
            if unknown_task_refs:
                raise ValueError("company_operation_snapshot.json includes unknown focus-task references")
        ctx.state.scoped_task_ids = scoped_task_ids
        ctx.state.focus_workflows = scoped_workflow_names
        return Event("company_operation_context_captured")

    @python_step(
        name="publish_recursive_improvement_cycle",
        requires=[
            workflow_capability_snapshot,
            workflow_portfolio_health_snapshot,
            company_operation_snapshot,
            company_pressure_map,
            recursive_improvement_priority_matrix,
            recursive_improvement_candidates,
            recursive_improvement_cycle,
            recursive_improvement_summary,
            recursive_improvement_next_actions,
        ],
        writes=[recursive_improvement_cycle_receipt],
        routes={"recursive_improvement_cycle_published": FINISH},
    )
    def publish_recursive_improvement_cycle(ctx):
        workflow_folder = ctx.workflow_folder
        required_paths = require_existing_artifact_paths(
            {
                "workflow_capability_snapshot": workflow_folder / "workflow_capability_snapshot.json",
                "workflow_portfolio_health_snapshot": workflow_folder / "workflow_portfolio_health_snapshot.json",
                "company_operation_snapshot": workflow_folder / "company_operation_snapshot.json",
                "company_pressure_map": workflow_folder / "company_pressure_map.md",
                "recursive_improvement_priority_matrix": workflow_folder / "recursive_improvement_priority_matrix.md",
                "recursive_improvement_candidates": workflow_folder / "recursive_improvement_candidates.json",
                "recursive_improvement_cycle": workflow_folder / "recursive_improvement_cycle.md",
                "recursive_improvement_summary": workflow_folder / "recursive_improvement_summary.json",
                "recursive_improvement_next_actions": workflow_folder / "recursive_improvement_next_actions.md",
            }
        )

        capability_snapshot = _read_json(required_paths["workflow_capability_snapshot"])
        capability_workflow_names = extract_workflow_names_from_capability_snapshot(capability_snapshot)

        health_snapshot = _read_json(required_paths["workflow_portfolio_health_snapshot"])
        health_payload = _require_mapping(
            health_snapshot.get("workflow_portfolio_health"),
            "workflow_portfolio_health_snapshot.json must define workflow_portfolio_health as a JSON object",
        )
        scoped_workflow_names = extract_workflow_names_from_portfolio_health(health_payload)
        if ctx.state.focus_workflows and scoped_workflow_names != ctx.state.focus_workflows:
            raise ValueError(
                "workflow_portfolio_health_snapshot.json scoped workflow entries must match the captured company context"
            )
        unknown_workflows = sorted(set(scoped_workflow_names) - capability_workflow_names)
        if unknown_workflows:
            raise ValueError("workflow_portfolio_health_snapshot.json includes unknown focus-workflow references")

        company_snapshot = _read_json(required_paths["company_operation_snapshot"])
        company_payload = _require_mapping(
            company_snapshot.get("company_operation"),
            "company_operation_snapshot.json must define company_operation as a JSON object",
        )
        company_tasks = _require_mapping_list(
            company_payload.get("tasks"),
            "company_operation_snapshot.json must define company_operation.tasks as a JSON array of objects",
        )
        scoped_task_ids = _extract_company_task_ids(company_tasks)
        if ctx.state.scoped_task_ids and scoped_task_ids != ctx.state.scoped_task_ids:
            raise ValueError("company_operation_snapshot.json task entries must match the captured company context")
        _validate_company_task_summaries(
            company_tasks,
            allowed_workflows=capability_workflow_names,
            focus_workflows=scoped_workflow_names if ctx.state.focus_workflows else None,
        )

        pressure_map_text = read_required_text(
            required_paths["company_pressure_map"],
            "company_pressure_map.md must not be empty",
        )
        priority_matrix_text = read_required_text(
            required_paths["recursive_improvement_priority_matrix"],
            "recursive_improvement_priority_matrix.md must not be empty",
        )
        del pressure_map_text

        candidate_payload = _read_json(required_paths["recursive_improvement_candidates"])
        candidate_ids, priority_categories, priority_category_counts = _validate_improvement_candidates(
            candidate_payload,
            allowed_workflows=scoped_workflow_names,
            allowed_tasks=scoped_task_ids,
        )
        if ctx.state.candidate_ids and candidate_ids != ctx.state.candidate_ids:
            raise ValueError("recursive_improvement_candidates.json candidate_ids must match workflow state")
        if ctx.state.priority_item_ids and candidate_ids != ctx.state.priority_item_ids:
            raise ValueError("recursive_improvement_candidates.json candidate order must match the analyzed recursive-improvement context")
        if ctx.state.priority_categories and priority_categories != ctx.state.priority_categories:
            raise ValueError("recursive_improvement_candidates.json priority categories must match workflow state")
        for candidate_id in candidate_ids:
            if candidate_id not in priority_matrix_text:
                raise ValueError("recursive_improvement_priority_matrix.md must name each improvement candidate explicitly")

        summary = RECURSIVE_IMPROVEMENT_SUMMARY_ARTIFACT.read(required_paths["recursive_improvement_summary"])
        summary_focus_task_ids = _require_string_list(
            summary.focus_task_ids,
            "recursive_improvement_summary.json must define focus_task_ids as a non-empty string list",
        )
        if summary_focus_task_ids != scoped_task_ids:
            unknown_task_refs = sorted(set(summary_focus_task_ids) - set(scoped_task_ids))
            if unknown_task_refs:
                raise ValueError("recursive_improvement_summary.json includes unknown focus-task references")
            raise ValueError("recursive_improvement_summary.json focus_task_ids must match the scoped company context")
        summary_focus_workflows = _require_string_list(
            summary.focus_workflows,
            "recursive_improvement_summary.json must define focus_workflows as a non-empty string list",
        )
        if summary_focus_workflows != scoped_workflow_names:
            unknown_workflow_refs = sorted(set(summary_focus_workflows) - set(scoped_workflow_names))
            if unknown_workflow_refs:
                raise ValueError("recursive_improvement_summary.json includes unknown focus-workflow references")
            raise ValueError("recursive_improvement_summary.json focus_workflows must match the scoped company context")
        summary_candidate_ids = _require_string_list(
            summary.candidate_ids,
            "recursive_improvement_summary.json must define candidate_ids as a non-empty string list",
        )
        if summary_candidate_ids != candidate_ids:
            raise ValueError("recursive_improvement_summary.json candidate_ids must not drift from recursive_improvement_candidates.json")
        priority_item_ids = _require_string_list(
            summary.priority_item_ids,
            "recursive_improvement_summary.json must define priority_item_ids as a non-empty string list",
        )
        if priority_item_ids != candidate_ids:
            raise ValueError("recursive_improvement_summary.json priority_item_ids must match recursive_improvement_candidates.json")
        summary_priority_categories = _require_priority_category_list(
            summary.priority_categories,
            "recursive_improvement_summary.json must define priority_categories as a non-empty string list",
        )
        if summary_priority_categories != priority_categories:
            raise ValueError(
                "recursive_improvement_summary.json priority_categories must not drift from recursive_improvement_candidates.json"
            )
        summary_priority_category_counts = _require_priority_category_count_mapping(
            summary.priority_category_counts,
            "recursive_improvement_summary.json must define priority_category_counts as a JSON object",
        )
        if summary_priority_category_counts != priority_category_counts:
            raise ValueError(
                "recursive_improvement_summary.json priority_category_counts must not drift from recursive_improvement_candidates.json"
            )
        authoritative_artifacts = validate_authoritative_artifact_subset(
            summary.authoritative_artifacts,
            required_artifacts=_AUTHORITATIVE_PACKAGE_ARTIFACTS,
            missing_error_message="recursive_improvement_summary.json must define authoritative_artifacts as a non-empty string list",
            subset_error_message="recursive_improvement_summary.json authoritative_artifacts must include recursive_improvement_cycle, recursive_improvement_summary, recursive_improvement_next_actions, company_pressure_map, recursive_improvement_priority_matrix, and recursive_improvement_candidates",
        )
        next_action = _require_text(
            summary.next_action,
            "recursive_improvement_summary.json must define a non-empty next_action",
        )
        validate_no_hidden_execution_signal(
            next_action,
            "recursive_improvement_summary.json next_action must not imply hidden downstream execution",
        )
        publication_boundary = validate_publication_boundary(
            summary.publication_boundary,
            expected_boundary=_PUBLICATION_BOUNDARY,
            missing_error_message="recursive_improvement_summary.json must define a non-empty publication_boundary",
            mismatch_error_message="recursive_improvement_summary.json publication_boundary must be recursive_improvement_publication_only",
        )
        require_true_flag(
            summary.ready_for_publication,
            "recursive_improvement_summary.json must confirm ready_for_publication=true",
        )
        if _require_text(
            summary.workflow_name,
            "recursive_improvement_summary.json must define workflow_name",
        ) != ctx.workflow_name:
            raise ValueError("recursive_improvement_summary.json workflow_name must match the workflow")

        cycle_text = read_required_text(
            required_paths["recursive_improvement_cycle"],
            "recursive_improvement_cycle.md must not be empty",
        )
        for marker in _PACKAGE_SECTION_MARKERS:
            if marker not in cycle_text:
                raise ValueError("recursive_improvement_cycle.md must keep category sections and the publication boundary explicit")
        if _PUBLICATION_BOUNDARY not in cycle_text:
            raise ValueError("recursive_improvement_cycle.md must state the recursive-improvement publication boundary explicitly")
        validate_no_hidden_execution_signal(
            cycle_text,
            "recursive_improvement_cycle.md must not imply hidden downstream execution",
        )
        for candidate_id in candidate_ids:
            if candidate_id not in cycle_text:
                raise ValueError("recursive_improvement_cycle.md must name each priority item explicitly")

        next_actions_text = read_required_text(
            required_paths["recursive_improvement_next_actions"],
            "recursive_improvement_next_actions.md must not be empty",
        )
        if _PUBLICATION_BOUNDARY not in next_actions_text:
            raise ValueError("recursive_improvement_next_actions.md must state the recursive-improvement publication boundary explicitly")
        validate_no_hidden_execution_signal(
            next_actions_text,
            "recursive_improvement_next_actions.md must not imply hidden downstream execution",
        )

        write_publication_receipt(
            ctx,
            "recursive_improvement_cycle_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "task_title": ctx.state.task_title,
                "sponsor_role": ctx.state.sponsor_role,
                "desired_outcome": ctx.state.desired_outcome,
                "focus_task_ids": scoped_task_ids,
                "focus_workflows": scoped_workflow_names,
                "candidate_ids": candidate_ids,
                "priority_categories": priority_categories,
                "priority_item_ids": candidate_ids,
                "next_action": next_action,
                "publication_boundary": publication_boundary,
                "authoritative_artifacts": authoritative_artifacts,
                "workflow_capability_snapshot": str(required_paths["workflow_capability_snapshot"]),
                "workflow_portfolio_health_snapshot": str(required_paths["workflow_portfolio_health_snapshot"]),
                "company_operation_snapshot": str(required_paths["company_operation_snapshot"]),
                "company_pressure_map": str(required_paths["company_pressure_map"]),
                "recursive_improvement_priority_matrix": str(required_paths["recursive_improvement_priority_matrix"]),
                "recursive_improvement_candidates": str(required_paths["recursive_improvement_candidates"]),
                "recursive_improvement_cycle": str(required_paths["recursive_improvement_cycle"]),
                "recursive_improvement_summary": str(required_paths["recursive_improvement_summary"]),
                "recursive_improvement_next_actions": str(required_paths["recursive_improvement_next_actions"]),
                "published": True,
            },
        )
        ctx.state.scoped_task_ids = scoped_task_ids
        ctx.state.focus_workflows = scoped_workflow_names
        ctx.state.candidate_ids = candidate_ids
        ctx.state.priority_item_ids = candidate_ids
        ctx.state.priority_categories = priority_categories
        ctx.state.published = True
        return Event("recursive_improvement_cycle_published")

    entry = bootstrap



_require_text = partial(require_non_empty_string, coerce=True)
_normalize_optional_text = normalize_optional_string
_normalize_unique_strings = partial(normalize_unique_strings, allow_scalar=True)
_require_string_list = partial(require_string_list, allow_scalar=True, dedupe=True, coerce=True)


def _require_priority_category_list(value: Any, error_message: str) -> list[str]:
    normalized = _require_string_list(value, error_message)
    for category in normalized:
        if category not in _ALLOWED_PRIORITY_CATEGORIES:
            raise ValueError(f"{error_message} with legal priority categories")
    return normalized


_require_positive_int = require_positive_int
_read_json = read_json_object


_require_mapping = require_mapping
_require_mapping_list = require_mapping_list


def _require_priority_category_count_mapping(value: Any, error_message: str) -> dict[str, int]:
    mapping = _require_mapping(value, error_message)
    normalized: dict[str, int] = {}
    for key, raw_count in mapping.items():
        normalized_key = _require_text(key, error_message)
        if normalized_key not in _ALLOWED_PRIORITY_CATEGORIES:
            raise ValueError("recursive_improvement_summary.json priority_category_counts keys must be legal priority categories")
        if not isinstance(raw_count, int) or raw_count < 0:
            raise ValueError(error_message)
        normalized[normalized_key] = raw_count
    return dict(sorted(normalized.items()))


def _extract_company_task_ids(tasks: list[dict[str, Any]]) -> list[str]:
    task_ids: list[str] = []
    for task in tasks:
        task_id = _require_text(
            task.get("task_id"),
            "company_operation_snapshot.json task entries must define task_id",
        )
        task_ids.append(task_id)
    require_unique_values(task_ids, error_message="company_operation_snapshot.json task ids must be unique")
    return task_ids


def _validate_company_task_summaries(
    tasks: list[dict[str, Any]],
    *,
    allowed_workflows: set[str],
    focus_workflows: list[str] | None,
) -> None:
    for task in tasks:
        summaries = _require_mapping_list(
            task.get("workflow_run_summaries"),
            "company_operation_snapshot.json task entries must define workflow_run_summaries as a JSON array of objects",
            min_length=0,
        )
        workflow_names: list[str] = []
        for summary in summaries:
            workflow_name = _require_text(
                summary.get("workflow_name"),
                "company_operation_snapshot.json workflow_run_summaries entries must define workflow_name",
            )
            if workflow_name not in allowed_workflows:
                raise ValueError("company_operation_snapshot.json workflow_run_summaries include unknown workflow references")
            workflow_names.append(workflow_name)
        require_unique_values(
            workflow_names,
            error_message="company_operation_snapshot.json workflow_run_summaries must keep workflow_name values unique within each task",
        )
        if focus_workflows is not None and workflow_names != focus_workflows:
            raise ValueError("company_operation_snapshot.json workflow_run_summaries must match the scoped workflow set for every task")


def _validated_priority_recommendations(
    value: Any,
    *,
    allowed_candidate_ids: list[str],
    error_prefix: str,
) -> tuple[list[str], list[str]]:
    recommendations = _require_mapping_list(
        value,
        f"{error_prefix} must define priority_recommendations as a JSON array of objects",
    )
    allowed = set(allowed_candidate_ids)
    candidate_ids: list[str] = []
    categories: list[str] = []
    for entry in recommendations:
        candidate_id = _require_text(
            entry.get("candidate_id"),
            f"{error_prefix} priority_recommendations entries must define candidate_id",
        )
        if candidate_id not in allowed:
            raise ValueError(f"{error_prefix} priority_recommendations must be drawn from candidate_ids")
        if candidate_id in candidate_ids:
            raise ValueError(f"{error_prefix} priority_recommendations candidate_id values must be unique")
        category = _require_text(
            entry.get("category"),
            f"{error_prefix} priority_recommendations entries must define category",
        )
        if category not in _ALLOWED_PRIORITY_CATEGORIES:
            raise ValueError(f"{error_prefix} priority_recommendations entries must define a legal priority category")
        priority = _require_text(
            entry.get("priority"),
            f"{error_prefix} priority_recommendations entries must define priority",
        )
        if priority not in _ALLOWED_PRIORITY_LEVELS:
            raise ValueError(f"{error_prefix} priority_recommendations entries must define a legal priority")
        candidate_ids.append(candidate_id)
        if category not in categories:
            categories.append(category)
    if candidate_ids != allowed_candidate_ids:
        raise ValueError(f"{error_prefix} priority_recommendations must cover candidate_ids exactly once in order")
    return candidate_ids, categories


def _validate_improvement_candidates(
    payload: Mapping[str, Any],
    *,
    allowed_workflows: list[str],
    allowed_tasks: list[str],
) -> tuple[list[str], list[str], dict[str, int]]:
    candidates = _require_mapping_list(
        payload.get("improvement_candidates"),
        "recursive_improvement_candidates.json must define improvement_candidates as a JSON array of objects",
    )
    allowed_workflow_set = set(allowed_workflows)
    allowed_task_set = set(allowed_tasks)
    candidate_ids: list[str] = []
    categories: list[str] = []
    category_counts: dict[str, int] = {}
    for entry in candidates:
        candidate_id = _require_text(
            entry.get("candidate_id"),
            "recursive_improvement_candidates.json improvement_candidates entries must define candidate_id",
        )
        if candidate_id in candidate_ids:
            raise ValueError("recursive_improvement_candidates.json candidate_id values must be unique")
        category = _require_text(
            entry.get("category"),
            "recursive_improvement_candidates.json improvement_candidates entries must define category",
        )
        if category not in _ALLOWED_PRIORITY_CATEGORIES:
            raise ValueError("recursive_improvement_candidates.json improvement_candidates entries must define a legal priority category")
        priority = _require_text(
            entry.get("priority"),
            "recursive_improvement_candidates.json improvement_candidates entries must define priority",
        )
        if priority not in _ALLOWED_PRIORITY_LEVELS:
            raise ValueError("recursive_improvement_candidates.json improvement_candidates entries must define a legal priority")
        _require_text(
            entry.get("title"),
            "recursive_improvement_candidates.json improvement_candidates entries must define title",
        )
        _require_text(
            entry.get("why_now"),
            "recursive_improvement_candidates.json improvement_candidates entries must define why_now",
        )
        _require_string_list(
            entry.get("evidence_sources"),
            "recursive_improvement_candidates.json improvement_candidates entries must define evidence_sources",
        )
        _require_text(
            entry.get("next_step_hint"),
            "recursive_improvement_candidates.json improvement_candidates entries must define next_step_hint",
        )
        workflow_names = _normalize_unique_strings(entry.get("workflow_names"))
        task_ids = _normalize_unique_strings(entry.get("task_ids"))
        if not workflow_names and not task_ids:
            raise ValueError(
                "recursive_improvement_candidates.json improvement_candidates entries must define workflow_names, task_ids, or both"
            )
        for workflow_name in workflow_names:
            if workflow_name not in allowed_workflow_set:
                raise ValueError(
                    "recursive_improvement_candidates.json improvement_candidates entries must refer only to scoped workflows"
                )
        for task_id in task_ids:
            if task_id not in allowed_task_set:
                raise ValueError(
                    "recursive_improvement_candidates.json improvement_candidates entries must refer only to scoped tasks"
                )
        candidate_ids.append(candidate_id)
        if category not in categories:
            categories.append(category)
        category_counts[category] = category_counts.get(category, 0) + 1
    return candidate_ids, categories, dict(sorted(category_counts.items()))


def _sorted_unique_strings(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})


__all__ = ["CompanyOperationToRecursiveImprovementCycle"]
