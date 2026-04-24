"""Workflow package for company-level recursive improvement."""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import partial
from typing import Any

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.stdlib import (
        normalize_optional_string,
        normalize_unique_strings,
        read_json_object,
        require_mapping,
        require_mapping_list,
        require_non_empty_string,
        require_positive_int,
        require_string_list,
        require_unique_values,
        write_company_operation_snapshot,
        write_workflow_capability_snapshot,
        write_workflow_portfolio_health_snapshot,
    )
    from autoloop_v3.stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from autoloop_v3.stdlib.lifecycle import (
        open_workflow_sessions,
        write_invocation_contract,
        write_publication_receipt,
    )
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from stdlib import (
        normalize_optional_string,
        normalize_unique_strings,
        read_json_object,
        require_mapping,
        require_mapping_list,
        require_non_empty_string,
        require_positive_int,
        require_string_list,
        require_unique_values,
        write_company_operation_snapshot,
        write_workflow_capability_snapshot,
        write_workflow_portfolio_health_snapshot,
    )
    from stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from workflow import Artifact, FAIL, PairStep, Session, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event, Outcome

from .contracts import (
    ANALYZE_RECURSIVE_IMPROVEMENT_ROUTE_CONTRACTS,
    FRAME_COMPANY_OPERATION_ROUTE_CONTRACTS,
    PACKAGE_RECURSIVE_IMPROVEMENT_CYCLE_ROUTE_CONTRACTS,
    CompanyOperationFramingPayload,
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
_HIDDEN_EXECUTION_PATTERNS = (
    re.compile(r"\bauto[- ]?run\b"),
    re.compile(r"\bautomatically\s+(?:run|queue|launch|execute|trigger|start)(?:s|ed)?\b"),
    re.compile(
        r"\b(?:the runtime|the system|this workflow|this package)\s+(?:will\s+)?(?:queue|launch|run|execute|trigger|start)(?:s|ed)?\b"
    ),
    re.compile(r"\bwill\s+be\s+(?:queued|launched|run|executed|triggered|started)\b"),
    re.compile(r"\bwithout further review\b"),
)
_NEGATED_HIDDEN_EXECUTION_MARKERS = (
    "do not auto-run",
    "does not auto-run",
    "must not auto-run",
    "should not auto-run",
    "do not automatically",
    "does not automatically",
    "must not automatically",
    "should not automatically",
    "without auto-running",
    "instead of auto-running",
)


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
    framework_architecture_doc = Artifact("{package_folder}/../../docs/architecture.md")
    framework_authoring_doc = Artifact("{package_folder}/../../docs/authoring.md")
    workflow_instructions = Artifact("{package_folder}/../../Workflow_Instructions.md")
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

    bootstrap = SystemStep(
        name="bootstrap",
        requires=[request],
        produces={"invocation_contract": invocation_contract},
    )
    capture_company_operation_context = SystemStep(
        name="capture_company_operation_context",
        requires=[request, invocation_contract],
        produces={
            "workflow_capability_snapshot": workflow_capability_snapshot,
            "workflow_portfolio_health_snapshot": workflow_portfolio_health_snapshot,
            "company_operation_snapshot": company_operation_snapshot,
        },
    )
    frame_company_operation = PairStep(
        name="frame_company_operation",
        session=frame_session,
        producer="prompts/frame_producer.md",
        verifier="prompts/frame_verifier.md",
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
        produces={
            "company_operation_brief": company_operation_brief,
            "recursive_improvement_criteria": recursive_improvement_criteria,
        },
        expected_output_schema=CompanyOperationFramingPayload,
        route_contracts=FRAME_COMPANY_OPERATION_ROUTE_CONTRACTS,
    )
    analyze_recursive_improvement_pressures = PairStep(
        name="analyze_recursive_improvement_pressures",
        session=analysis_session,
        producer="prompts/analyze_producer.md",
        verifier="prompts/analyze_verifier.md",
        requires=[
            request,
            invocation_contract,
            workflow_capability_snapshot,
            workflow_portfolio_health_snapshot,
            company_operation_snapshot,
            company_operation_brief,
            recursive_improvement_criteria,
        ],
        produces={
            "company_pressure_map": company_pressure_map,
            "recursive_improvement_priority_matrix": recursive_improvement_priority_matrix,
            "recursive_improvement_candidates": recursive_improvement_candidates,
        },
        expected_output_schema=RecursiveImprovementAnalysisPayload,
        route_contracts=ANALYZE_RECURSIVE_IMPROVEMENT_ROUTE_CONTRACTS,
    )
    package_recursive_improvement_cycle = PairStep(
        name="package_recursive_improvement_cycle",
        session=package_session,
        producer="prompts/package_producer.md",
        verifier="prompts/package_verifier.md",
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
        produces={
            "recursive_improvement_cycle": recursive_improvement_cycle,
            "recursive_improvement_summary": recursive_improvement_summary,
            "recursive_improvement_next_actions": recursive_improvement_next_actions,
        },
        expected_output_schema=RecursiveImprovementCyclePayload,
        route_contracts=PACKAGE_RECURSIVE_IMPROVEMENT_CYCLE_ROUTE_CONTRACTS,
    )
    publish_recursive_improvement_cycle = SystemStep(
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
        produces={"recursive_improvement_cycle_receipt": recursive_improvement_cycle_receipt},
    )

    entry = bootstrap

    transitions = merge_transitions(
        global_routes(pause_on_outcome_tags("question", "blocked"), failed=FAIL),
        {
            bootstrap: {"inputs_prepared": capture_company_operation_context},
            capture_company_operation_context: {"company_operation_context_captured": frame_company_operation},
            frame_company_operation: {
                "company_operation_framed": analyze_recursive_improvement_pressures,
                "needs_rework": frame_company_operation,
                "needs_replan": frame_company_operation,
            },
            analyze_recursive_improvement_pressures: {
                "recursive_improvement_pressures_analyzed": package_recursive_improvement_cycle,
                "needs_rework": analyze_recursive_improvement_pressures,
                "needs_replan": frame_company_operation,
            },
            package_recursive_improvement_cycle: {
                "recursive_improvement_cycle_ready": publish_recursive_improvement_cycle,
                "needs_rework": package_recursive_improvement_cycle,
                "needs_replan": analyze_recursive_improvement_pressures,
            },
            publish_recursive_improvement_cycle: {"recursive_improvement_cycle_published": SUCCESS},
        },
    )

    @staticmethod
    def on_bootstrap(state: State, ctx) -> tuple[State, Event]:
        payload = dict(ctx.workflow_params)
        task_title = _require_text(
            payload.get("task_title"),
            "company_operation_to_recursive_improvement_cycle requires workflow parameter 'task_title'",
        )
        max_tasks = _require_positive_int(
            payload.get("max_tasks"),
            "company_operation_to_recursive_improvement_cycle requires workflow parameter 'max_tasks' as a positive integer",
        )
        max_runs_per_workflow = _require_positive_int(
            payload.get("max_runs_per_workflow"),
            "company_operation_to_recursive_improvement_cycle requires workflow parameter 'max_runs_per_workflow' as a positive integer",
        )
        max_messages_per_task = _require_positive_int(
            payload.get("max_messages_per_task"),
            "company_operation_to_recursive_improvement_cycle requires workflow parameter 'max_messages_per_task' as a positive integer",
        )
        next_state = state.model_copy(
            update={
                "task_title": task_title,
                "sponsor_role": _normalize_optional_text(payload.get("sponsor_role")),
                "desired_outcome": _normalize_optional_text(payload.get("desired_outcome")),
                "decision_drivers": _normalize_unique_strings(payload.get("decision_drivers")),
                "constraints": _normalize_unique_strings(payload.get("constraints")),
                "focus_task_references": _normalize_unique_strings(payload.get("focus_tasks")),
                "focus_workflow_references": _normalize_unique_strings(payload.get("focus_workflows")),
                "statuses": _normalize_unique_strings(payload.get("statuses")),
                "max_tasks": max_tasks,
                "max_runs_per_workflow": max_runs_per_workflow,
                "max_messages_per_task": max_messages_per_task,
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
        return next_state, Event("inputs_prepared")

    @staticmethod
    def on_capture_company_operation_context(state: State, ctx) -> tuple[State, Event]:
        capability_path = write_workflow_capability_snapshot(ctx)
        health_path = write_workflow_portfolio_health_snapshot(
            ctx,
            workflows=state.focus_workflow_references or None,
            statuses=state.statuses or None,
            max_runs_per_workflow=state.max_runs_per_workflow,
        )
        company_path = write_company_operation_snapshot(
            ctx,
            task_ids=state.focus_task_references or None,
            workflows=state.focus_workflow_references or None,
            statuses=state.statuses or None,
            max_tasks=state.max_tasks,
            max_runs_per_workflow=state.max_runs_per_workflow,
            max_messages_per_task=state.max_messages_per_task,
        )
        for artifact_path in (capability_path, health_path, company_path):
            if not artifact_path.exists():
                raise FileNotFoundError(f"required context artifact was not written at {artifact_path}")

        capability_snapshot = _read_json(capability_path)
        workflow_count = capability_snapshot.get("workflow_count")
        if not isinstance(workflow_count, int) or workflow_count < 1:
            raise ValueError("workflow_capability_snapshot.json must define a positive workflow_count")
        capability_workflow_names = _workflow_names_from_capability_snapshot(capability_snapshot)

        health_snapshot = _read_json(health_path)
        health_payload = _require_mapping(
            health_snapshot.get("workflow_portfolio_health"),
            "workflow_portfolio_health_snapshot.json must define workflow_portfolio_health as a JSON object",
        )
        if health_payload.get("max_runs_per_workflow") != state.max_runs_per_workflow:
            raise ValueError("workflow_portfolio_health_snapshot.json max_runs_per_workflow must match the invocation contract")
        expected_statuses = _sorted_unique_strings(state.statuses) or None
        if health_payload.get("statuses") != expected_statuses:
            raise ValueError("workflow_portfolio_health_snapshot.json statuses must match the invocation contract")
        scoped_workflow_names = _extract_portfolio_workflow_names(health_payload)
        if not scoped_workflow_names:
            raise ValueError("workflow_portfolio_health_snapshot.json must contain at least one scoped workflow")
        if health_payload.get("workflow_count") != len(scoped_workflow_names):
            raise ValueError("workflow_portfolio_health_snapshot.json workflow_count must match the scoped workflow entries")
        if state.focus_workflow_references:
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
        if company_payload.get("max_tasks") != state.max_tasks:
            raise ValueError("company_operation_snapshot.json max_tasks must match the invocation contract")
        if company_payload.get("max_runs_per_workflow") != state.max_runs_per_workflow:
            raise ValueError("company_operation_snapshot.json max_runs_per_workflow must match the invocation contract")
        if company_payload.get("max_messages_per_task") != state.max_messages_per_task:
            raise ValueError("company_operation_snapshot.json max_messages_per_task must match the invocation contract")
        if company_payload.get("statuses") != expected_statuses:
            raise ValueError("company_operation_snapshot.json statuses must match the invocation contract")
        if state.focus_task_references:
            selected_task_ids = _require_string_list(
                company_payload.get("selected_task_ids"),
                "company_operation_snapshot.json must define selected_task_ids when focus_task_references are supplied",
            )
            if selected_task_ids != _sorted_unique_strings(state.focus_task_references):
                raise ValueError("company_operation_snapshot.json selected_task_ids must match the scoped task references")
        if state.focus_workflow_references:
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
            focus_workflows=scoped_workflow_names if state.focus_workflow_references else None,
        )
        if state.focus_task_references:
            unknown_task_refs = sorted(set(scoped_task_ids) - set(_sorted_unique_strings(state.focus_task_references)))
            if unknown_task_refs:
                raise ValueError("company_operation_snapshot.json includes unknown focus-task references")

        return (
            state.model_copy(
                update={
                    "scoped_task_ids": scoped_task_ids,
                    "focus_workflows": scoped_workflow_names,
                }
            ),
            Event("company_operation_context_captured"),
        )

    @staticmethod
    def on_frame_company_operation(state: State, outcome: Outcome, artifacts):
        del artifacts
        payload = outcome.payload
        focus_task_ids = _require_string_list(
            payload.get("focus_task_ids"),
            "frame verifier payload must define focus_task_ids as a non-empty string list",
        )
        if state.scoped_task_ids and focus_task_ids != state.scoped_task_ids:
            raise ValueError("frame verifier payload focus_task_ids must match the captured company context")
        focus_workflows = _require_string_list(
            payload.get("focus_workflows"),
            "frame verifier payload must define focus_workflows as a non-empty string list",
        )
        if state.focus_workflows and focus_workflows != state.focus_workflows:
            raise ValueError("frame verifier payload focus_workflows must match the captured company context")
        return state.model_copy(update={"framing_status": outcome.tag})

    @staticmethod
    def on_analyze_recursive_improvement_pressures(state: State, outcome: Outcome, artifacts):
        del artifacts
        payload = outcome.payload
        focus_task_ids = _require_string_list(
            payload.get("focus_task_ids"),
            "analysis verifier payload must define focus_task_ids as a non-empty string list",
        )
        if state.scoped_task_ids and focus_task_ids != state.scoped_task_ids:
            raise ValueError("analysis verifier payload focus_task_ids must match the captured company context")
        focus_workflows = _require_string_list(
            payload.get("focus_workflows"),
            "analysis verifier payload must define focus_workflows as a non-empty string list",
        )
        if state.focus_workflows and focus_workflows != state.focus_workflows:
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
        return state.model_copy(
            update={
                "analysis_status": outcome.tag,
                "candidate_ids": candidate_ids,
                "priority_item_ids": priority_item_ids,
                "priority_categories": priority_categories,
            }
        )

    @staticmethod
    def on_package_recursive_improvement_cycle(state: State, outcome: Outcome, artifacts):
        del artifacts
        payload = outcome.payload
        focus_task_ids = _require_string_list(
            payload.get("focus_task_ids"),
            "package verifier payload must define focus_task_ids as a non-empty string list",
        )
        if state.scoped_task_ids and focus_task_ids != state.scoped_task_ids:
            raise ValueError("package verifier payload focus_task_ids must match the captured company context")
        focus_workflows = _require_string_list(
            payload.get("focus_workflows"),
            "package verifier payload must define focus_workflows as a non-empty string list",
        )
        if state.focus_workflows and focus_workflows != state.focus_workflows:
            raise ValueError("package verifier payload focus_workflows must match the captured company context")
        candidate_ids = _require_string_list(
            payload.get("candidate_ids"),
            "package verifier payload must define candidate_ids as a non-empty string list",
        )
        if state.candidate_ids and candidate_ids != state.candidate_ids:
            raise ValueError("package verifier payload candidate_ids must match the analyzed recursive-improvement context")
        priority_item_ids = _require_string_list(
            payload.get("priority_item_ids"),
            "package verifier payload must define priority_item_ids as a non-empty string list",
        )
        if state.priority_item_ids and priority_item_ids != state.priority_item_ids:
            raise ValueError("package verifier payload priority_item_ids must match the analyzed recursive-improvement context")
        priority_categories = _require_priority_category_list(
            payload.get("priority_categories"),
            "package verifier payload must define priority_categories as a non-empty string list",
        )
        if state.priority_categories and priority_categories != state.priority_categories:
            raise ValueError("package verifier payload priority_categories must match the analyzed recursive-improvement context")
        return state.model_copy(update={"packaging_status": outcome.tag})

    @staticmethod
    def on_publish_recursive_improvement_cycle(state: State, ctx) -> tuple[State, Event]:
        workflow_folder = ctx.workflow_folder
        required_paths = {
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
        for artifact_path in required_paths.values():
            if not artifact_path.exists():
                raise FileNotFoundError(f"missing required publication artifact at {artifact_path}")

        capability_snapshot = _read_json(required_paths["workflow_capability_snapshot"])
        capability_workflow_names = _workflow_names_from_capability_snapshot(capability_snapshot)

        health_snapshot = _read_json(required_paths["workflow_portfolio_health_snapshot"])
        health_payload = _require_mapping(
            health_snapshot.get("workflow_portfolio_health"),
            "workflow_portfolio_health_snapshot.json must define workflow_portfolio_health as a JSON object",
        )
        scoped_workflow_names = _extract_portfolio_workflow_names(health_payload)
        if state.focus_workflows and scoped_workflow_names != state.focus_workflows:
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
        if state.scoped_task_ids and scoped_task_ids != state.scoped_task_ids:
            raise ValueError("company_operation_snapshot.json task entries must match the captured company context")
        _validate_company_task_summaries(
            company_tasks,
            allowed_workflows=capability_workflow_names,
            focus_workflows=scoped_workflow_names if state.focus_workflows else None,
        )

        pressure_map_text = _read_required_text(
            required_paths["company_pressure_map"],
            "company_pressure_map.md must not be empty",
        )
        priority_matrix_text = _read_required_text(
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
        if state.candidate_ids and candidate_ids != state.candidate_ids:
            raise ValueError("recursive_improvement_candidates.json candidate_ids must match workflow state")
        if state.priority_item_ids and candidate_ids != state.priority_item_ids:
            raise ValueError("recursive_improvement_candidates.json candidate order must match the analyzed recursive-improvement context")
        if state.priority_categories and priority_categories != state.priority_categories:
            raise ValueError("recursive_improvement_candidates.json priority categories must match workflow state")
        for candidate_id in candidate_ids:
            if candidate_id not in priority_matrix_text:
                raise ValueError("recursive_improvement_priority_matrix.md must name each improvement candidate explicitly")

        summary = _read_json(required_paths["recursive_improvement_summary"])
        summary_focus_task_ids = _require_string_list(
            summary.get("focus_task_ids"),
            "recursive_improvement_summary.json must define focus_task_ids as a non-empty string list",
        )
        if summary_focus_task_ids != scoped_task_ids:
            unknown_task_refs = sorted(set(summary_focus_task_ids) - set(scoped_task_ids))
            if unknown_task_refs:
                raise ValueError("recursive_improvement_summary.json includes unknown focus-task references")
            raise ValueError("recursive_improvement_summary.json focus_task_ids must match the scoped company context")
        summary_focus_workflows = _require_string_list(
            summary.get("focus_workflows"),
            "recursive_improvement_summary.json must define focus_workflows as a non-empty string list",
        )
        if summary_focus_workflows != scoped_workflow_names:
            unknown_workflow_refs = sorted(set(summary_focus_workflows) - set(scoped_workflow_names))
            if unknown_workflow_refs:
                raise ValueError("recursive_improvement_summary.json includes unknown focus-workflow references")
            raise ValueError("recursive_improvement_summary.json focus_workflows must match the scoped company context")
        summary_candidate_ids = _require_string_list(
            summary.get("candidate_ids"),
            "recursive_improvement_summary.json must define candidate_ids as a non-empty string list",
        )
        if summary_candidate_ids != candidate_ids:
            raise ValueError("recursive_improvement_summary.json candidate_ids must not drift from recursive_improvement_candidates.json")
        priority_item_ids = _require_string_list(
            summary.get("priority_item_ids"),
            "recursive_improvement_summary.json must define priority_item_ids as a non-empty string list",
        )
        if priority_item_ids != candidate_ids:
            raise ValueError("recursive_improvement_summary.json priority_item_ids must match recursive_improvement_candidates.json")
        summary_priority_categories = _require_priority_category_list(
            summary.get("priority_categories"),
            "recursive_improvement_summary.json must define priority_categories as a non-empty string list",
        )
        if summary_priority_categories != priority_categories:
            raise ValueError(
                "recursive_improvement_summary.json priority_categories must not drift from recursive_improvement_candidates.json"
            )
        summary_priority_category_counts = _require_priority_category_count_mapping(
            summary.get("priority_category_counts"),
            "recursive_improvement_summary.json must define priority_category_counts as a JSON object",
        )
        if summary_priority_category_counts != priority_category_counts:
            raise ValueError(
                "recursive_improvement_summary.json priority_category_counts must not drift from recursive_improvement_candidates.json"
            )
        authoritative_artifacts = _require_string_list(
            summary.get("authoritative_artifacts"),
            "recursive_improvement_summary.json must define authoritative_artifacts as a non-empty string list",
        )
        if not _AUTHORITATIVE_PACKAGE_ARTIFACTS.issubset(authoritative_artifacts):
            raise ValueError(
                "recursive_improvement_summary.json authoritative_artifacts must include recursive_improvement_cycle, recursive_improvement_summary, recursive_improvement_next_actions, company_pressure_map, recursive_improvement_priority_matrix, and recursive_improvement_candidates"
            )
        next_action = _require_text(
            summary.get("next_action"),
            "recursive_improvement_summary.json must define a non-empty next_action",
        )
        _validate_no_hidden_execution_signal(
            next_action,
            "recursive_improvement_summary.json next_action must not imply hidden downstream execution",
        )
        publication_boundary = _require_text(
            summary.get("publication_boundary"),
            "recursive_improvement_summary.json must define a non-empty publication_boundary",
        )
        if publication_boundary != _PUBLICATION_BOUNDARY:
            raise ValueError(
                "recursive_improvement_summary.json publication_boundary must be recursive_improvement_publication_only"
            )
        if summary.get("ready_for_publication") is not True:
            raise ValueError("recursive_improvement_summary.json must confirm ready_for_publication=true")
        if _require_text(
            summary.get("workflow_name"),
            "recursive_improvement_summary.json must define workflow_name",
        ) != ctx.workflow_name:
            raise ValueError("recursive_improvement_summary.json workflow_name must match the workflow")

        cycle_text = _read_required_text(
            required_paths["recursive_improvement_cycle"],
            "recursive_improvement_cycle.md must not be empty",
        )
        for marker in _PACKAGE_SECTION_MARKERS:
            if marker not in cycle_text:
                raise ValueError("recursive_improvement_cycle.md must keep category sections and the publication boundary explicit")
        if _PUBLICATION_BOUNDARY not in cycle_text:
            raise ValueError("recursive_improvement_cycle.md must state the recursive-improvement publication boundary explicitly")
        if _contains_hidden_execution_signal(cycle_text):
            raise ValueError("recursive_improvement_cycle.md must not imply hidden downstream execution")
        for candidate_id in candidate_ids:
            if candidate_id not in cycle_text:
                raise ValueError("recursive_improvement_cycle.md must name each priority item explicitly")

        next_actions_text = _read_required_text(
            required_paths["recursive_improvement_next_actions"],
            "recursive_improvement_next_actions.md must not be empty",
        )
        if _PUBLICATION_BOUNDARY not in next_actions_text:
            raise ValueError("recursive_improvement_next_actions.md must state the recursive-improvement publication boundary explicitly")
        if _contains_hidden_execution_signal(next_actions_text):
            raise ValueError("recursive_improvement_next_actions.md must not imply hidden downstream execution")

        write_publication_receipt(
            ctx,
            "recursive_improvement_cycle_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "task_title": state.task_title,
                "sponsor_role": state.sponsor_role,
                "desired_outcome": state.desired_outcome,
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
        return (
            state.model_copy(
                update={
                    "scoped_task_ids": scoped_task_ids,
                    "focus_workflows": scoped_workflow_names,
                    "candidate_ids": candidate_ids,
                    "priority_item_ids": candidate_ids,
                    "priority_categories": priority_categories,
                    "published": True,
                }
            ),
            Event("recursive_improvement_cycle_published"),
        )

    on_outcome = staticmethod(event_on_outcome_tags("question", "blocked", "failed"))


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


def _read_required_text(path, error_message: str) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(error_message)
    return text


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


def _workflow_names_from_capability_snapshot(snapshot) -> set[str]:
    workflows = snapshot.get("workflows")
    if not isinstance(workflows, list):
        raise ValueError("workflow_capability_snapshot.json must define a workflows list")
    names: set[str] = set()
    for entry in workflows:
        if not isinstance(entry, Mapping):
            raise ValueError("workflow_capability_snapshot.json workflows entries must be objects")
        workflow_name = entry.get("workflow_name")
        if isinstance(workflow_name, str) and workflow_name.strip():
            names.add(workflow_name.strip())
    if not names:
        raise ValueError("workflow_capability_snapshot.json must contain at least one workflow_name")
    return names


def _extract_portfolio_workflow_names(health_payload: Mapping[str, Any]) -> list[str]:
    workflows = _require_mapping_list(
        health_payload.get("workflows"),
        "workflow_portfolio_health_snapshot.json must define workflow_portfolio_health.workflows as a JSON array of objects",
    )
    names: list[str] = []
    for entry in workflows:
        workflow_name = _require_text(
            entry.get("workflow_name"),
            "workflow_portfolio_health_snapshot.json workflow entries must define workflow_name",
        )
        names.append(workflow_name)
    require_unique_values(
        names,
        error_message="workflow_portfolio_health_snapshot.json scoped workflow names must be unique",
    )
    return names


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


def _contains_hidden_execution_signal(text: str) -> bool:
    for raw_line in text.splitlines():
        lowered = raw_line.strip().lower()
        if not lowered:
            continue
        if any(marker in lowered for marker in _NEGATED_HIDDEN_EXECUTION_MARKERS):
            continue
        if any(pattern.search(lowered) for pattern in _HIDDEN_EXECUTION_PATTERNS):
            return True
    return False


def _validate_no_hidden_execution_signal(text: str, error_message: str) -> None:
    if _contains_hidden_execution_signal(text):
        raise ValueError(error_message)


__all__ = ["CompanyOperationToRecursiveImprovementCycle"]
