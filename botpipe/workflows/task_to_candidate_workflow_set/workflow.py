"""Task-to-candidate-workflow-set building-block workflow package."""

from __future__ import annotations

from pydantic import BaseModel, Field

from botpipe_optimizer import write_workflow_capability_snapshot
from botpipe.stdlib import (
    normalize_unique_strings,
    read_json_object,
    require_non_empty_string,
    require_string_list,
)
from botpipe.stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from botpipe import Event, FAIL, FINISH, Outcome, Prompt, Session, Workflow, produce_verify_step, python_step
from botpipe.core import Artifact

from .contracts import (
    ANALYZE_CANDIDATE_WORKFLOWS_ROUTE_CONTRACTS,
    CANDIDATE_WORKFLOW_SET_SUMMARY_ARTIFACT,
    FRAME_CANDIDATE_REQUEST_ROUTE_CONTRACTS,
    PACKAGE_CANDIDATE_WORKFLOW_SET_ROUTE_CONTRACTS,
    CandidateRequestFramingPayload,
    CandidateWorkflowAnalysisPayload,
    CandidateWorkflowSetPayload,
    _PORTFOLIO_POSTURES,
    _require_portfolio_posture,
)


_BUILDER_BASELINE = "workflow_idea_to_workflow_package"
_AUTHORITATIVE_PACKAGE_ARTIFACTS = frozenset(
    {
        "candidate_workflow_set",
        "candidate_workflow_set_summary",
        "candidate_next_action",
    }
)


def _after_frame_candidate_request(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    ctx.state.framing_status = outcome.tag
    return None


def _after_analyze_candidate_workflows(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    portfolio_posture = payload.get("portfolio_posture")
    ctx.state.analysis_status = outcome.tag
    if isinstance(portfolio_posture, str) and portfolio_posture in _PORTFOLIO_POSTURES:
        ctx.state.portfolio_posture = portfolio_posture
    return None


def _after_package_candidate_workflow_set(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    portfolio_posture = payload.get("portfolio_posture")
    recommended = normalize_unique_strings(
        payload.get("recommended_candidate_workflows"),
        allow_scalar=True,
    )
    ctx.state.packaging_status = outcome.tag
    if isinstance(portfolio_posture, str) and portfolio_posture in _PORTFOLIO_POSTURES:
        ctx.state.portfolio_posture = portfolio_posture
    if recommended:
        ctx.state.recommended_candidate_workflows = recommended
    return None


class TaskToCandidateWorkflowSet(Workflow):
    """Turn an arbitrary task into a ranked candidate-workflow-set package."""

    name = "task_to_candidate_workflow_set"

    class State(BaseModel):
        task_title: str = ""
        sponsor_role: str | None = None
        desired_outcome: str | None = None
        constraints: list[str] = Field(default_factory=list)
        evidence_expectations: list[str] = Field(default_factory=list)
        framing_status: str | None = None
        analysis_status: str | None = None
        packaging_status: str | None = None
        portfolio_posture: str | None = None
        recommended_candidate_workflows: list[str] = Field(default_factory=list)
        published: bool = False

    frame_session = Session()
    analysis_session = Session()
    package_session = Session()

    request = Artifact("{{ run.folder }}/request.md")
    framework_architecture_doc = Artifact("{{ root }}/docs/architecture.md")
    framework_authoring_doc = Artifact("{{ root }}/docs/authoring.md")
    workflow_authoring_guidelines = Artifact("{{ root }}/docs/workflow_authoring_guidelines.md")
    candidate_set_checklist = Artifact("{{ package.folder }}/assets/candidate_workflow_set_checklist.md")

    invocation_contract = Artifact("{{ workflow.folder }}/invocation_contract.json")
    workflow_capability_snapshot = Artifact("{{ workflow.folder }}/workflow_capability_snapshot.json")
    candidate_request_brief = Artifact("{{ workflow.folder }}/candidate_request_brief.md")
    candidate_selection_criteria = Artifact("{{ workflow.folder }}/candidate_selection_criteria.md")
    workflow_candidate_matrix = Artifact("{{ workflow.folder }}/workflow_candidate_matrix.md")
    workflow_gap_analysis = Artifact("{{ workflow.folder }}/workflow_gap_analysis.md")
    candidate_route_posture = Artifact("{{ workflow.folder }}/candidate_route_posture.md")
    candidate_workflow_set = Artifact("{{ workflow.folder }}/candidate_workflow_set.md")
    candidate_workflow_set_summary = Artifact("{{ workflow.folder }}/candidate_workflow_set_summary.json")
    candidate_next_action = Artifact("{{ workflow.folder }}/candidate_next_action.md")
    candidate_workflow_set_receipt = Artifact("{{ workflow.folder }}/candidate_workflow_set_receipt.json")

    @python_step(
        name="bootstrap",
        requires=[request],
        writes=[invocation_contract],
        routes={"inputs_prepared": "capture_workflow_capabilities"},
    )
    def bootstrap(ctx):
        params = ctx.params
        next_state = ctx.state.model_copy(
            update={
                "task_title": params.task_title,
                "sponsor_role": params.sponsor_role,
                "desired_outcome": params.desired_outcome,
                "constraints": list(params.constraints),
                "evidence_expectations": list(params.evidence_expectations),
                "framing_status": None,
                "analysis_status": None,
                "packaging_status": None,
                "portfolio_posture": None,
                "recommended_candidate_workflows": [],
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
                "constraints": next_state.constraints,
                "evidence_expectations": next_state.evidence_expectations,
            },
        )
        ctx.state = next_state
        return "inputs_prepared"

    @python_step(
        name="capture_workflow_capabilities",
        requires=[request, invocation_contract],
        writes=[workflow_capability_snapshot],
        routes={"workflow_capabilities_captured": "frame_candidate_request"},
    )
    def capture_workflow_capabilities(ctx):
        snapshot_path = write_workflow_capability_snapshot(ctx)
        if not snapshot_path.exists():
            raise FileNotFoundError(f"workflow capability snapshot was not written at {snapshot_path}")
        summary = read_json_object(snapshot_path)
        workflow_count = summary.get("workflow_count")
        if not isinstance(workflow_count, int) or workflow_count < 1:
            raise ValueError("workflow_capability_snapshot.json must define a positive workflow_count")
        return "workflow_capabilities_captured"

    frame_candidate_request = produce_verify_step(
        producer_prompt=Prompt.file("prompts/frame_producer.md"),
        verifier_prompt=Prompt.file("prompts/frame_verifier.md"),
        session=frame_session,
        requires=[
            request,
            invocation_contract,
            workflow_capability_snapshot,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_authoring_guidelines,
        ],
        producer_writes=[candidate_request_brief, candidate_selection_criteria],
        control_schema=CandidateRequestFramingPayload,
        routes=FRAME_CANDIDATE_REQUEST_ROUTE_CONTRACTS,
        after_verifier=_after_frame_candidate_request,
    )

    analyze_candidate_workflows = produce_verify_step(
        producer_prompt=Prompt.file("prompts/analyze_producer.md"),
        verifier_prompt=Prompt.file("prompts/analyze_verifier.md"),
        session=analysis_session,
        requires=[
            request,
            invocation_contract,
            workflow_capability_snapshot,
            candidate_request_brief,
            candidate_selection_criteria,
        ],
        producer_writes=[workflow_candidate_matrix, workflow_gap_analysis, candidate_route_posture],
        control_schema=CandidateWorkflowAnalysisPayload,
        routes=ANALYZE_CANDIDATE_WORKFLOWS_ROUTE_CONTRACTS,
        after_verifier=_after_analyze_candidate_workflows,
    )

    package_candidate_workflow_set = produce_verify_step(
        producer_prompt=Prompt.file("prompts/package_producer.md"),
        verifier_prompt=Prompt.file("prompts/package_verifier.md"),
        session=package_session,
        requires=[
            request,
            invocation_contract,
            workflow_capability_snapshot,
            candidate_set_checklist,
            candidate_request_brief,
            candidate_selection_criteria,
            workflow_candidate_matrix,
            workflow_gap_analysis,
            candidate_route_posture,
        ],
        producer_writes=[candidate_workflow_set, candidate_workflow_set_summary, candidate_next_action],
        control_schema=CandidateWorkflowSetPayload,
        routes=PACKAGE_CANDIDATE_WORKFLOW_SET_ROUTE_CONTRACTS,
        after_verifier=_after_package_candidate_workflow_set,
    )

    @python_step(
        name="publish_candidate_workflow_set",
        requires=[
            workflow_capability_snapshot,
            workflow_candidate_matrix,
            workflow_gap_analysis,
            candidate_route_posture,
            candidate_workflow_set,
            candidate_workflow_set_summary,
            candidate_next_action,
        ],
        writes=[candidate_workflow_set_receipt],
        routes={"candidate_workflow_set_published": FINISH},
    )
    def publish_candidate_workflow_set(ctx):
        workflow_folder = ctx.workflow_folder
        required_paths = {
            "workflow_capability_snapshot": workflow_folder / "workflow_capability_snapshot.json",
            "workflow_candidate_matrix": workflow_folder / "workflow_candidate_matrix.md",
            "workflow_gap_analysis": workflow_folder / "workflow_gap_analysis.md",
            "candidate_route_posture": workflow_folder / "candidate_route_posture.md",
            "candidate_workflow_set": workflow_folder / "candidate_workflow_set.md",
            "candidate_workflow_set_summary": workflow_folder / "candidate_workflow_set_summary.json",
            "candidate_next_action": workflow_folder / "candidate_next_action.md",
        }
        for artifact_path in required_paths.values():
            if not artifact_path.exists():
                raise FileNotFoundError(f"missing required publication artifact at {artifact_path}")

        capability_snapshot = read_json_object(required_paths["workflow_capability_snapshot"])
        workflow_count = capability_snapshot.get("workflow_count")
        if not isinstance(workflow_count, int) or workflow_count < 1:
            raise ValueError("workflow_capability_snapshot.json must define a positive workflow_count")

        summary = CANDIDATE_WORKFLOW_SET_SUMMARY_ARTIFACT.read(
            required_paths["candidate_workflow_set_summary"]
        )
        comparison_candidates = require_string_list(
            summary.comparison_candidates,
            error_message="candidate_workflow_set_summary.json must define non-empty comparison_candidates",
            allow_scalar=True,
            dedupe=True,
            coerce=True,
        )
        required_candidate_count = 3 if workflow_count >= 3 else 1
        if len(comparison_candidates) < required_candidate_count:
            raise ValueError(
                "candidate_workflow_set_summary.json must compare at least three candidate workflows when the portfolio size permits"
            )
        ranked_candidates = require_string_list(
            summary.ranked_candidates,
            error_message="candidate_workflow_set_summary.json must define non-empty ranked_candidates",
            allow_scalar=True,
            dedupe=True,
            coerce=True,
        )
        recommended_candidate_workflows = require_string_list(
            summary.recommended_candidate_workflows,
            error_message="candidate_workflow_set_summary.json must define non-empty recommended_candidate_workflows",
            allow_scalar=True,
            dedupe=True,
            coerce=True,
        )
        for candidate_name in ranked_candidates:
            if candidate_name not in comparison_candidates:
                raise ValueError(
                    "candidate_workflow_set_summary.json ranked_candidates must be drawn from comparison_candidates"
                )
        for candidate_name in recommended_candidate_workflows:
            if candidate_name not in ranked_candidates:
                raise ValueError(
                    "candidate_workflow_set_summary.json recommended_candidate_workflows must be drawn from ranked_candidates"
                )

        builder_baseline_workflow = require_non_empty_string(
            summary.builder_baseline_workflow,
            error_message="candidate_workflow_set_summary.json must define a non-empty builder_baseline_workflow",
            coerce=True,
        )
        if builder_baseline_workflow != _BUILDER_BASELINE:
            raise ValueError(
                f"candidate_workflow_set_summary.json builder_baseline_workflow must be {_BUILDER_BASELINE!r}"
            )
        builder_present = _BUILDER_BASELINE in _workflow_names_from_snapshot(capability_snapshot)
        builder_considered = summary.builder_considered
        if builder_present:
            if builder_considered is not True:
                raise ValueError("candidate_workflow_set_summary.json must confirm builder_considered=true")
            if _BUILDER_BASELINE not in comparison_candidates:
                raise ValueError(
                    "candidate_workflow_set_summary.json must include the builder baseline in comparison_candidates"
                )

        portfolio_posture = _require_portfolio_posture(
            summary.portfolio_posture,
            "candidate_workflow_set_summary.json must define a legal portfolio_posture",
        )
        if portfolio_posture == "compose_needed" and len(recommended_candidate_workflows) < 2:
            raise ValueError(
                "candidate_workflow_set_summary.json must recommend at least two workflows when portfolio_posture is compose_needed"
            )
        if portfolio_posture == "material_gap" and _BUILDER_BASELINE not in recommended_candidate_workflows:
            raise ValueError(
                "candidate_workflow_set_summary.json must recommend workflow_idea_to_workflow_package when portfolio_posture is material_gap"
            )

        authoritative_artifacts = require_string_list(
            summary.authoritative_artifacts,
            error_message="candidate_workflow_set_summary.json must define non-empty authoritative_artifacts",
            allow_scalar=True,
            dedupe=True,
            coerce=True,
        )
        if not _AUTHORITATIVE_PACKAGE_ARTIFACTS.issubset(authoritative_artifacts):
            raise ValueError(
                "candidate_workflow_set_summary.json authoritative_artifacts must include candidate_workflow_set, candidate_workflow_set_summary, and candidate_next_action"
            )
        next_action = require_non_empty_string(
            summary.next_action,
            error_message="candidate_workflow_set_summary.json must define a non-empty next_action",
            coerce=True,
        )
        ready_for_strategy_selection = summary.ready_for_strategy_selection
        if ready_for_strategy_selection is not True:
            raise ValueError(
                "candidate_workflow_set_summary.json must confirm ready_for_strategy_selection=true"
            )

        if ctx.state.portfolio_posture is not None and portfolio_posture != ctx.state.portfolio_posture:
            raise ValueError("candidate_workflow_set_summary.json portfolio_posture must match workflow state")
        if ctx.state.recommended_candidate_workflows and recommended_candidate_workflows != ctx.state.recommended_candidate_workflows:
            raise ValueError(
                "candidate_workflow_set_summary.json recommended_candidate_workflows must match workflow state"
            )

        write_publication_receipt(
            ctx,
            "candidate_workflow_set_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "task_title": ctx.state.task_title,
                "sponsor_role": ctx.state.sponsor_role,
                "desired_outcome": ctx.state.desired_outcome,
                "comparison_candidates": comparison_candidates,
                "ranked_candidates": ranked_candidates,
                "recommended_candidate_workflows": recommended_candidate_workflows,
                "builder_baseline_workflow": builder_baseline_workflow,
                "portfolio_posture": portfolio_posture,
                "next_action": next_action,
                "authoritative_artifacts": authoritative_artifacts,
                "workflow_capability_snapshot": str(required_paths["workflow_capability_snapshot"]),
                "workflow_candidate_matrix": str(required_paths["workflow_candidate_matrix"]),
                "workflow_gap_analysis": str(required_paths["workflow_gap_analysis"]),
                "candidate_route_posture": str(required_paths["candidate_route_posture"]),
                "candidate_workflow_set": str(required_paths["candidate_workflow_set"]),
                "candidate_workflow_set_summary": str(required_paths["candidate_workflow_set_summary"]),
                "candidate_next_action": str(required_paths["candidate_next_action"]),
                "published": True,
            },
        )
        ctx.state.portfolio_posture = portfolio_posture
        ctx.state.recommended_candidate_workflows = recommended_candidate_workflows
        ctx.state.published = True
        return Event("candidate_workflow_set_published")


def _workflow_names_from_snapshot(snapshot) -> set[str]:
    workflows = snapshot.get("workflows")
    if not isinstance(workflows, list):
        raise ValueError("workflow_capability_snapshot.json must define a workflows list")
    names: set[str] = set()
    for entry in workflows:
        if not isinstance(entry, dict):
            raise ValueError("workflow_capability_snapshot.json workflows entries must be objects")
        workflow_name = entry.get("workflow_name")
        if isinstance(workflow_name, str) and workflow_name.strip():
            names.add(workflow_name.strip())
    return names
