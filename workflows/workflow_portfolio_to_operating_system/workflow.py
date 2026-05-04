"""Workflow package for portfolio-level workflow governance."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from typing import Any

from pydantic import BaseModel, Field

from autoloop_optimizer import write_workflow_capability_snapshot, write_workflow_portfolio_health_snapshot
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

from autoloop import Event, FAIL, FINISH, Outcome, Prompt, Session, Workflow, produce_verify_step, python_step
from autoloop.core import Artifact

from .contracts import (
    ANALYZE_PORTFOLIO_OPERATING_MODEL_ROUTE_CONTRACTS,
    FRAME_PORTFOLIO_GOVERNANCE_ROUTE_CONTRACTS,
    PACKAGE_PORTFOLIO_OPERATING_SYSTEM_ROUTE_CONTRACTS,
    PORTFOLIO_OPERATING_SUMMARY_ARTIFACT,
    PortfolioGovernanceFramingPayload,
    PortfolioOperatingModelPayload,
    PortfolioOperatingSystemPayload,
)


_ALLOWED_LIFECYCLE_POSTURES = frozenset({"keep", "refine", "decompose", "merge", "retire"})
_ALLOWED_CHANGE_ACTIONS = frozenset({*_ALLOWED_LIFECYCLE_POSTURES, "create_next"})
_ALLOWED_PRIORITY_LEVELS = frozenset({"P1", "P2", "P3"})
_AUTHORITATIVE_PACKAGE_ARTIFACTS = frozenset(
    {
        "workflow_portfolio_operating_system",
        "portfolio_operating_summary",
        "portfolio_next_actions",
        "workflow_lifecycle_matrix",
        "portfolio_gap_analysis",
        "portfolio_change_candidates",
    }
)
_PACKAGE_SECTION_MARKERS = (
    "## Keep",
    "## Refine",
    "## Decompose",
    "## Merge",
    "## Retire",
    "## Create Next",
)
_PUBLICATION_BOUNDARY = "operating_system_publication_only"


def _after_frame_portfolio_governance(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    focus_workflows = _require_string_list(
        outcome.payload.get("focus_workflows"),
        "frame verifier payload must define focus_workflows as a non-empty string list",
    )
    if ctx.state.focus_workflows and focus_workflows != ctx.state.focus_workflows:
        raise ValueError("frame verifier payload focus_workflows must match the captured portfolio context")
    ctx.state.framing_status = outcome.tag
    ctx.state.focus_workflows = focus_workflows
    return None


def _after_analyze_portfolio_operating_model(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    focus_workflows = _require_string_list(
        payload.get("focus_workflows"),
        "analysis verifier payload must define focus_workflows as a non-empty string list",
    )
    if ctx.state.focus_workflows and focus_workflows != ctx.state.focus_workflows:
        raise ValueError("analysis verifier payload focus_workflows must match the captured portfolio context")
    analyzed_workflows = _require_string_list(
        payload.get("analyzed_workflows"),
        "analysis verifier payload must define analyzed_workflows as a non-empty string list",
    )
    lifecycle_postures = _validated_lifecycle_recommendations(
        payload.get("lifecycle_recommendations"),
        allowed_workflows=analyzed_workflows,
        error_prefix="analysis verifier payload",
    )
    change_candidate_ids = _require_string_list(
        payload.get("change_candidate_ids"),
        "analysis verifier payload must define change_candidate_ids as a non-empty string list",
    )
    ctx.state.analysis_status = outcome.tag
    ctx.state.focus_workflows = focus_workflows
    ctx.state.analyzed_workflows = analyzed_workflows
    ctx.state.lifecycle_postures = lifecycle_postures
    ctx.state.change_candidate_ids = change_candidate_ids
    return None


def _after_package_portfolio_operating_system(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    focus_workflows = _require_string_list(
        payload.get("focus_workflows"),
        "package verifier payload must define focus_workflows as a non-empty string list",
    )
    if ctx.state.focus_workflows and focus_workflows != ctx.state.focus_workflows:
        raise ValueError("package verifier payload focus_workflows must match the captured portfolio context")
    analyzed_workflows = _require_string_list(
        payload.get("analyzed_workflows"),
        "package verifier payload must define analyzed_workflows as a non-empty string list",
    )
    if ctx.state.analyzed_workflows and analyzed_workflows != ctx.state.analyzed_workflows:
        raise ValueError("package verifier payload analyzed_workflows must match the analyzed portfolio context")
    change_candidate_ids = _require_string_list(
        payload.get("change_candidate_ids"),
        "package verifier payload must define change_candidate_ids as a non-empty string list",
    )
    if ctx.state.change_candidate_ids and change_candidate_ids != ctx.state.change_candidate_ids:
        raise ValueError("package verifier payload change_candidate_ids must match the analyzed portfolio context")
    priority_workflows = _require_string_list(
        payload.get("priority_workflows"),
        "package verifier payload must define priority_workflows as a non-empty string list",
    )
    for workflow_name in priority_workflows:
        if workflow_name not in analyzed_workflows:
            raise ValueError("package verifier payload priority_workflows must be drawn from analyzed_workflows")
    ctx.state.packaging_status = outcome.tag
    ctx.state.focus_workflows = focus_workflows
    ctx.state.analyzed_workflows = analyzed_workflows
    ctx.state.change_candidate_ids = change_candidate_ids
    ctx.state.priority_workflows = priority_workflows
    return None


class WorkflowPortfolioToOperatingSystem(Workflow):
    """Turn workflow portfolio evidence into a lifecycle-governance package."""

    name = "workflow_portfolio_to_operating_system"

    class State(BaseModel):
        task_title: str = ""
        sponsor_role: str | None = None
        desired_outcome: str | None = None
        decision_drivers: list[str] = Field(default_factory=list)
        constraints: list[str] = Field(default_factory=list)
        focus_workflow_references: list[str] = Field(default_factory=list)
        focus_workflows: list[str] = Field(default_factory=list)
        max_runs_per_workflow: int = 10
        framing_status: str | None = None
        analysis_status: str | None = None
        packaging_status: str | None = None
        analyzed_workflows: list[str] = Field(default_factory=list)
        lifecycle_postures: dict[str, str] = Field(default_factory=dict)
        change_candidate_ids: list[str] = Field(default_factory=list)
        priority_workflows: list[str] = Field(default_factory=list)
        published: bool = False

    frame_session = Session()
    analysis_session = Session()
    package_session = Session()

    request = Artifact("{run_folder}/request.md")
    framework_architecture_doc = Artifact("{package_folder}/../../docs/architecture.md")
    framework_authoring_doc = Artifact("{package_folder}/../../docs/authoring.md")
    workflow_instructions = Artifact("{package_folder}/../../Workflow_Instructions.md")
    portfolio_operating_system_checklist = Artifact("{package_folder}/assets/portfolio_operating_system_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json")
    workflow_capability_snapshot = Artifact("{workflow_folder}/workflow_capability_snapshot.json")
    workflow_portfolio_health_snapshot = Artifact("{workflow_folder}/workflow_portfolio_health_snapshot.json")
    portfolio_governance_brief = Artifact("{workflow_folder}/portfolio_governance_brief.md")
    portfolio_decision_criteria = Artifact("{workflow_folder}/portfolio_decision_criteria.md")
    workflow_lifecycle_matrix = Artifact("{workflow_folder}/workflow_lifecycle_matrix.md")
    portfolio_gap_analysis = Artifact("{workflow_folder}/portfolio_gap_analysis.md")
    portfolio_change_candidates = Artifact("{workflow_folder}/portfolio_change_candidates.json")
    workflow_portfolio_operating_system = Artifact("{workflow_folder}/workflow_portfolio_operating_system.md")
    portfolio_operating_summary = Artifact("{workflow_folder}/portfolio_operating_summary.json")
    portfolio_next_actions = Artifact("{workflow_folder}/portfolio_next_actions.md")
    portfolio_operating_system_receipt = Artifact("{workflow_folder}/portfolio_operating_system_receipt.json")

    @python_step(
        name="bootstrap",
        requires=[request],
        writes=[invocation_contract],
        routes={"inputs_prepared": "capture_portfolio_context"},
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
                "focus_workflow_references": list(params.focus_workflows),
                "focus_workflows": [],
                "max_runs_per_workflow": params.max_runs_per_workflow,
                "framing_status": None,
                "analysis_status": None,
                "packaging_status": None,
                "analyzed_workflows": [],
                "lifecycle_postures": {},
                "change_candidate_ids": [],
                "priority_workflows": [],
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
                "focus_workflow_references": next_state.focus_workflow_references or None,
                "max_runs_per_workflow": next_state.max_runs_per_workflow,
            },
        )
        ctx.state = next_state
        return "inputs_prepared"

    @python_step(
        name="capture_portfolio_context",
        requires=[request, invocation_contract],
        writes=[workflow_capability_snapshot, workflow_portfolio_health_snapshot],
        routes={"portfolio_context_captured": "frame_portfolio_governance"},
    )
    def capture_portfolio_context(ctx):
        capability_path = write_workflow_capability_snapshot(ctx)
        health_path = write_workflow_portfolio_health_snapshot(
            ctx,
            workflows=ctx.state.focus_workflow_references or None,
            max_runs_per_workflow=ctx.state.max_runs_per_workflow,
        )
        if not capability_path.exists():
            raise FileNotFoundError(f"workflow capability snapshot was not written at {capability_path}")
        if not health_path.exists():
            raise FileNotFoundError(f"workflow portfolio health snapshot was not written at {health_path}")

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
        captured_max_runs = health_payload.get("max_runs_per_workflow")
        if captured_max_runs != ctx.state.max_runs_per_workflow:
            raise ValueError("workflow_portfolio_health_snapshot.json max_runs_per_workflow must match the invocation contract")
        scoped_workflow_names = extract_workflow_names_from_portfolio_health(health_payload)
        if ctx.state.focus_workflow_references:
            selected_workflow_names = _require_string_list(
                health_payload.get("selected_workflow_names"),
                "workflow_portfolio_health_snapshot.json must define selected_workflow_names when focus_workflow_references are supplied",
            )
            if scoped_workflow_names != selected_workflow_names:
                raise ValueError(
                    "workflow_portfolio_health_snapshot.json selected_workflow_names must match the scoped workflow entries"
                )
        if not scoped_workflow_names:
            raise ValueError("workflow_portfolio_health_snapshot.json must contain at least one scoped workflow")
        health_workflow_count = health_payload.get("workflow_count")
        if health_workflow_count != len(scoped_workflow_names):
            raise ValueError("workflow_portfolio_health_snapshot.json workflow_count must match the scoped workflow entries")
        unknown_workflows = sorted(set(scoped_workflow_names) - capability_workflow_names)
        if unknown_workflows:
            raise ValueError("workflow_portfolio_health_snapshot.json includes unknown focus-workflow references")

        ctx.state.focus_workflows = scoped_workflow_names
        return Event("portfolio_context_captured")

    frame_portfolio_governance = produce_verify_step(
        producer_prompt=Prompt.file("prompts/frame_producer.md"),
        verifier_prompt=Prompt.file("prompts/frame_verifier.md"),
        session=frame_session,
        requires=[
            request,
            invocation_contract,
            workflow_capability_snapshot,
            workflow_portfolio_health_snapshot,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        producer_writes=[portfolio_governance_brief, portfolio_decision_criteria],
        control_schema=PortfolioGovernanceFramingPayload,
        routes=FRAME_PORTFOLIO_GOVERNANCE_ROUTE_CONTRACTS,
        after_verifier=_after_frame_portfolio_governance,
    )

    analyze_portfolio_operating_model = produce_verify_step(
        producer_prompt=Prompt.file("prompts/analyze_producer.md"),
        verifier_prompt=Prompt.file("prompts/analyze_verifier.md"),
        session=analysis_session,
        requires=[
            request,
            invocation_contract,
            workflow_capability_snapshot,
            workflow_portfolio_health_snapshot,
            portfolio_governance_brief,
            portfolio_decision_criteria,
        ],
        producer_writes=[workflow_lifecycle_matrix, portfolio_gap_analysis, portfolio_change_candidates],
        control_schema=PortfolioOperatingModelPayload,
        routes=ANALYZE_PORTFOLIO_OPERATING_MODEL_ROUTE_CONTRACTS,
        after_verifier=_after_analyze_portfolio_operating_model,
    )

    package_portfolio_operating_system = produce_verify_step(
        producer_prompt=Prompt.file("prompts/package_producer.md"),
        verifier_prompt=Prompt.file("prompts/package_verifier.md"),
        session=package_session,
        requires=[
            request,
            invocation_contract,
            workflow_capability_snapshot,
            workflow_portfolio_health_snapshot,
            portfolio_operating_system_checklist,
            portfolio_governance_brief,
            portfolio_decision_criteria,
            workflow_lifecycle_matrix,
            portfolio_gap_analysis,
            portfolio_change_candidates,
        ],
        producer_writes=[
            workflow_portfolio_operating_system,
            portfolio_operating_summary,
            portfolio_next_actions,
        ],
        control_schema=PortfolioOperatingSystemPayload,
        routes=PACKAGE_PORTFOLIO_OPERATING_SYSTEM_ROUTE_CONTRACTS,
        after_verifier=_after_package_portfolio_operating_system,
    )

    @python_step(
        name="publish_portfolio_operating_system",
        requires=[
            workflow_capability_snapshot,
            workflow_portfolio_health_snapshot,
            workflow_lifecycle_matrix,
            portfolio_gap_analysis,
            portfolio_change_candidates,
            workflow_portfolio_operating_system,
            portfolio_operating_summary,
            portfolio_next_actions,
        ],
        writes=[portfolio_operating_system_receipt],
        routes={"portfolio_operating_system_published": FINISH},
    )
    def publish_portfolio_operating_system(ctx):
        workflow_folder = ctx.workflow_folder
        required_paths = require_existing_artifact_paths(
            {
                "workflow_capability_snapshot": workflow_folder / "workflow_capability_snapshot.json",
                "workflow_portfolio_health_snapshot": workflow_folder / "workflow_portfolio_health_snapshot.json",
                "workflow_lifecycle_matrix": workflow_folder / "workflow_lifecycle_matrix.md",
                "portfolio_gap_analysis": workflow_folder / "portfolio_gap_analysis.md",
                "portfolio_change_candidates": workflow_folder / "portfolio_change_candidates.json",
                "workflow_portfolio_operating_system": workflow_folder / "workflow_portfolio_operating_system.md",
                "portfolio_operating_summary": workflow_folder / "portfolio_operating_summary.json",
                "portfolio_next_actions": workflow_folder / "portfolio_next_actions.md",
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
                "workflow_portfolio_health_snapshot.json scoped workflow entries must match the captured portfolio context"
            )
        unknown_workflows = sorted(set(scoped_workflow_names) - capability_workflow_names)
        if unknown_workflows:
            raise ValueError("workflow_portfolio_health_snapshot.json includes unknown focus-workflow references")

        lifecycle_matrix_text = read_required_text(
            required_paths["workflow_lifecycle_matrix"],
            "workflow_lifecycle_matrix.md must not be empty",
        )
        gap_analysis_text = read_required_text(
            required_paths["portfolio_gap_analysis"],
            "portfolio_gap_analysis.md must not be empty",
        )
        del gap_analysis_text

        change_candidates_payload = _read_json(required_paths["portfolio_change_candidates"])
        change_candidate_ids = _validate_change_candidates(
            change_candidates_payload,
            analyzed_workflows=ctx.state.analyzed_workflows or scoped_workflow_names,
        )

        summary = PORTFOLIO_OPERATING_SUMMARY_ARTIFACT.read(required_paths["portfolio_operating_summary"])
        summary_focus_workflows = _require_string_list(
            summary.focus_workflows,
            "portfolio_operating_summary.json must define focus_workflows as a non-empty string list",
        )
        if summary_focus_workflows != scoped_workflow_names:
            raise ValueError("portfolio_operating_summary.json focus_workflows must match the scoped portfolio context")
        analyzed_workflows = _require_string_list(
            summary.analyzed_workflows,
            "portfolio_operating_summary.json must define analyzed_workflows as a non-empty string list",
        )
        if ctx.state.analyzed_workflows and analyzed_workflows != ctx.state.analyzed_workflows:
            raise ValueError("portfolio_operating_summary.json analyzed_workflows must match workflow state")
        lifecycle_postures = _validated_lifecycle_recommendations(
            [entry.model_dump(mode="python") for entry in summary.lifecycle_recommendations],
            allowed_workflows=analyzed_workflows,
            error_prefix="portfolio_operating_summary.json",
        )
        if ctx.state.lifecycle_postures and lifecycle_postures != ctx.state.lifecycle_postures:
            raise ValueError("portfolio_operating_summary.json lifecycle_recommendations must match workflow state")
        governance_posture_counts = _require_count_mapping(
            summary.governance_posture_counts,
            "portfolio_operating_summary.json must define governance_posture_counts as a JSON object",
        )
        expected_posture_counts = _count_lifecycle_postures(lifecycle_postures)
        if governance_posture_counts != expected_posture_counts:
            raise ValueError(
                "portfolio_operating_summary.json governance_posture_counts must not drift from lifecycle_recommendations"
            )
        summary_change_candidate_ids = _require_string_list(
            summary.change_candidate_ids,
            "portfolio_operating_summary.json must define change_candidate_ids as a non-empty string list",
        )
        if summary_change_candidate_ids != change_candidate_ids:
            raise ValueError("portfolio_operating_summary.json change_candidate_ids must not drift from portfolio_change_candidates.json")
        if ctx.state.change_candidate_ids and summary_change_candidate_ids != ctx.state.change_candidate_ids:
            raise ValueError("portfolio_operating_summary.json change_candidate_ids must match workflow state")
        priority_workflows = _require_string_list(
            summary.priority_workflows,
            "portfolio_operating_summary.json must define priority_workflows as a non-empty string list",
        )
        if ctx.state.priority_workflows and priority_workflows != ctx.state.priority_workflows:
            raise ValueError("portfolio_operating_summary.json priority_workflows must match workflow state")
        for workflow_name in priority_workflows:
            if workflow_name not in analyzed_workflows:
                raise ValueError("portfolio_operating_summary.json priority_workflows must be drawn from analyzed_workflows")
        authoritative_artifacts = validate_authoritative_artifact_subset(
            summary.authoritative_artifacts,
            required_artifacts=_AUTHORITATIVE_PACKAGE_ARTIFACTS,
            missing_error_message="portfolio_operating_summary.json must define authoritative_artifacts as a non-empty string list",
            subset_error_message="portfolio_operating_summary.json authoritative_artifacts must include workflow_portfolio_operating_system, portfolio_operating_summary, portfolio_next_actions, workflow_lifecycle_matrix, portfolio_gap_analysis, and portfolio_change_candidates",
        )
        next_action = _require_text(
            summary.next_action,
            "portfolio_operating_summary.json must define a non-empty next_action",
        )
        validate_no_hidden_execution_signal(
            next_action,
            "portfolio_operating_summary.json next_action must not imply hidden downstream execution",
        )
        publication_boundary = validate_publication_boundary(
            summary.publication_boundary,
            expected_boundary=_PUBLICATION_BOUNDARY,
            missing_error_message="portfolio_operating_summary.json must define a non-empty publication_boundary",
            mismatch_error_message="portfolio_operating_summary.json publication_boundary must be operating_system_publication_only",
        )
        require_true_flag(
            summary.ready_for_publication,
            "portfolio_operating_summary.json must confirm ready_for_publication=true",
        )

        operating_system_text = read_required_text(
            required_paths["workflow_portfolio_operating_system"],
            "workflow_portfolio_operating_system.md must not be empty",
        )
        for marker in _PACKAGE_SECTION_MARKERS:
            if marker not in operating_system_text:
                raise ValueError("workflow_portfolio_operating_system.md must keep keep/refine/decompose/merge/retire/create-next sections explicit")
        if _PUBLICATION_BOUNDARY not in operating_system_text:
            raise ValueError("workflow_portfolio_operating_system.md must state the operating-system publication boundary explicitly")
        validate_no_hidden_execution_signal(
            operating_system_text,
            "workflow_portfolio_operating_system.md must not imply hidden downstream execution",
        )

        next_actions_text = read_required_text(
            required_paths["portfolio_next_actions"],
            "portfolio_next_actions.md must not be empty",
        )
        if _PUBLICATION_BOUNDARY not in next_actions_text:
            raise ValueError("portfolio_next_actions.md must state the operating-system publication boundary explicitly")
        validate_no_hidden_execution_signal(
            next_actions_text,
            "portfolio_next_actions.md must not imply hidden downstream execution",
        )

        for workflow_name, posture in lifecycle_postures.items():
            if workflow_name not in lifecycle_matrix_text or posture not in lifecycle_matrix_text:
                raise ValueError("workflow_lifecycle_matrix.md must name each analyzed workflow and its lifecycle posture explicitly")

        write_publication_receipt(
            ctx,
            "portfolio_operating_system_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "task_title": ctx.state.task_title,
                "sponsor_role": ctx.state.sponsor_role,
                "desired_outcome": ctx.state.desired_outcome,
                "focus_workflows": scoped_workflow_names,
                "analyzed_workflows": analyzed_workflows,
                "lifecycle_postures": lifecycle_postures,
                "change_candidate_ids": summary_change_candidate_ids,
                "priority_workflows": priority_workflows,
                "next_action": next_action,
                "publication_boundary": publication_boundary,
                "authoritative_artifacts": authoritative_artifacts,
                "workflow_capability_snapshot": str(required_paths["workflow_capability_snapshot"]),
                "workflow_portfolio_health_snapshot": str(required_paths["workflow_portfolio_health_snapshot"]),
                "workflow_lifecycle_matrix": str(required_paths["workflow_lifecycle_matrix"]),
                "portfolio_gap_analysis": str(required_paths["portfolio_gap_analysis"]),
                "portfolio_change_candidates": str(required_paths["portfolio_change_candidates"]),
                "workflow_portfolio_operating_system": str(required_paths["workflow_portfolio_operating_system"]),
                "portfolio_operating_summary": str(required_paths["portfolio_operating_summary"]),
                "portfolio_next_actions": str(required_paths["portfolio_next_actions"]),
                "published": True,
            },
        )
        ctx.state.focus_workflows = scoped_workflow_names
        ctx.state.analyzed_workflows = analyzed_workflows
        ctx.state.lifecycle_postures = lifecycle_postures
        ctx.state.change_candidate_ids = summary_change_candidate_ids
        ctx.state.priority_workflows = priority_workflows
        ctx.state.published = True
        return Event("portfolio_operating_system_published")



_require_text = partial(require_non_empty_string, coerce=True)
_normalize_optional_text = normalize_optional_string
_normalize_unique_strings = partial(normalize_unique_strings, allow_scalar=True)
_require_string_list = partial(require_string_list, allow_scalar=True, dedupe=True, coerce=True)
_require_positive_int = require_positive_int
_read_json = read_json_object


_require_mapping = require_mapping
_require_mapping_list = require_mapping_list


def _require_count_mapping(value: Any, error_message: str) -> dict[str, int]:
    mapping = _require_mapping(value, error_message)
    normalized: dict[str, int] = {}
    for key, raw_count in mapping.items():
        normalized_key = _require_text(key, error_message)
        if normalized_key not in _ALLOWED_LIFECYCLE_POSTURES:
            raise ValueError("portfolio_operating_summary.json governance_posture_counts keys must be legal lifecycle_postures")
        if not isinstance(raw_count, int) or raw_count < 0:
            raise ValueError(error_message)
        normalized[normalized_key] = raw_count
    return dict(sorted(normalized.items()))


def _validated_lifecycle_recommendations(
    value: Any,
    *,
    allowed_workflows: list[str],
    error_prefix: str,
) -> dict[str, str]:
    recommendations = _require_mapping_list(
        value,
        f"{error_prefix} must define lifecycle_recommendations as a JSON array of objects",
    )
    allowed = set(allowed_workflows)
    normalized: dict[str, str] = {}
    for entry in recommendations:
        workflow_name = _require_text(
            entry.get("workflow_name"),
            f"{error_prefix} lifecycle_recommendations entries must define workflow_name",
        )
        if workflow_name not in allowed:
            raise ValueError(f"{error_prefix} lifecycle_recommendations must be drawn from analyzed_workflows")
        lifecycle_posture = _require_text(
            entry.get("lifecycle_posture"),
            f"{error_prefix} lifecycle_recommendations entries must define lifecycle_posture",
        )
        if lifecycle_posture not in _ALLOWED_LIFECYCLE_POSTURES:
            raise ValueError(f"{error_prefix} lifecycle_recommendations entries must define a legal lifecycle_posture")
        priority = _require_text(
            entry.get("priority"),
            f"{error_prefix} lifecycle_recommendations entries must define priority",
        )
        if priority not in _ALLOWED_PRIORITY_LEVELS:
            raise ValueError(f"{error_prefix} lifecycle_recommendations entries must define a legal priority")
        if workflow_name in normalized:
            raise ValueError(f"{error_prefix} lifecycle_recommendations workflow_name values must be unique")
        normalized[workflow_name] = lifecycle_posture
    if set(normalized) != allowed:
        raise ValueError(f"{error_prefix} lifecycle_recommendations must cover every analyzed_workflow exactly once")
    return normalized


def _validate_change_candidates(payload: Mapping[str, Any], *, analyzed_workflows: list[str]) -> list[str]:
    change_candidates = _require_mapping_list(
        payload.get("change_candidates"),
        "portfolio_change_candidates.json must define change_candidates as a JSON array of objects",
    )
    analyzed = set(analyzed_workflows)
    candidate_ids: list[str] = []
    for entry in change_candidates:
        candidate_id = _require_text(
            entry.get("candidate_id"),
            "portfolio_change_candidates.json change_candidates entries must define candidate_id",
        )
        if candidate_id in candidate_ids:
            raise ValueError("portfolio_change_candidates.json candidate_id values must be unique")
        action = _require_text(
            entry.get("action"),
            "portfolio_change_candidates.json change_candidates entries must define action",
        )
        if action not in _ALLOWED_CHANGE_ACTIONS:
            raise ValueError("portfolio_change_candidates.json change_candidates entries must define a legal action")
        priority = _require_text(
            entry.get("priority"),
            "portfolio_change_candidates.json change_candidates entries must define priority",
        )
        if priority not in _ALLOWED_PRIORITY_LEVELS:
            raise ValueError("portfolio_change_candidates.json change_candidates entries must define a legal priority")
        _require_text(
            entry.get("why_now"),
            "portfolio_change_candidates.json change_candidates entries must define why_now",
        )
        _require_string_list(
            entry.get("evidence_sources"),
            "portfolio_change_candidates.json change_candidates entries must define evidence_sources",
        )
        _require_text(
            entry.get("next_step_hint"),
            "portfolio_change_candidates.json change_candidates entries must define next_step_hint",
        )
        if action == "create_next":
            _require_text(
                entry.get("proposed_workflow_name"),
                "portfolio_change_candidates.json create_next entries must define proposed_workflow_name",
            )
        else:
            workflow_names = _require_string_list(
                entry.get("workflow_names"),
                "portfolio_change_candidates.json non-create_next entries must define workflow_names",
            )
            for workflow_name in workflow_names:
                if workflow_name not in analyzed:
                    raise ValueError(
                        "portfolio_change_candidates.json non-create_next entries must refer only to analyzed_workflows"
                    )
            if action == "merge" and len(workflow_names) < 2:
                raise ValueError("portfolio_change_candidates.json merge entries must name at least two workflows")
        candidate_ids.append(candidate_id)
    return candidate_ids


def _count_lifecycle_postures(lifecycle_postures: Mapping[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for posture in lifecycle_postures.values():
        counts[posture] = counts.get(posture, 0) + 1
    return dict(sorted(counts.items()))


__all__ = ["WorkflowPortfolioToOperatingSystem"]
