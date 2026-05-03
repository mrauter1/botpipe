"""Selected-workflow adaptation-planning building-block workflow package."""

from __future__ import annotations

from pydantic import BaseModel, Field

from autoloop_optimizer import (
    capture_selected_workflow,
    write_selected_workflow_capability_snapshot,
    write_validated_workflow_parameters,
)
from autoloop.stdlib import (
    read_json_object,
    require_existing_artifact_paths,
    require_non_empty_string,
    require_string_list,
    validate_selected_workflow_artifact_alignment,
    validate_selected_workflow_capability_snapshot,
)
from autoloop.stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from autoloop import Event, FAIL, FINISH, Outcome, Prompt, Session, Workflow, produce_verify_step, python_step
from autoloop.core import Artifact

from .contracts import (
    ADAPTED_EXECUTION_SUMMARY_ARTIFACT,
    ANALYZE_ADAPTATION_SURFACE_ROUTE_CONTRACTS,
    FRAME_ADAPTATION_REQUEST_ROUTE_CONTRACTS,
    PACKAGE_ADAPTED_EXECUTION_PLAN_ROUTE_CONTRACTS,
    VALIDATED_WORKFLOW_PARAMETERS_ARTIFACT,
    AdaptationRequestFramingPayload,
    AdaptationSurfaceAnalysisPayload,
    AdaptedExecutionPlanPayload,
)


_AUTHORITATIVE_PACKAGE_ARTIFACTS = frozenset(
    {
        "adapted_execution_plan",
        "adapted_execution_summary",
        "adapted_execution_next_action",
        "validated_workflow_parameters",
    }
)


def _after_frame_adaptation_request(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    selected_workflow_name = payload.get("selected_workflow_name")
    ctx.state.framing_status = outcome.tag
    if isinstance(selected_workflow_name, str):
        ctx.state.selected_workflow_name = selected_workflow_name
    return None


def _after_analyze_adaptation_surface(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    selected_workflow_name = payload.get("selected_workflow_name")
    ctx.state.analysis_status = outcome.tag
    if isinstance(selected_workflow_name, str):
        ctx.state.selected_workflow_name = selected_workflow_name
    return None


def _after_package_adapted_execution_plan(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    selected_workflow_name = payload.get("selected_workflow_name")
    proposed_parameter_keys = require_string_list(
        payload.get("proposed_parameter_keys"),
        error_message="package verifier payload must define proposed_parameter_keys as a string list",
        min_length=0,
        dedupe=True,
        coerce=True,
    )
    ctx.state.packaging_status = outcome.tag
    if isinstance(selected_workflow_name, str):
        ctx.state.selected_workflow_name = selected_workflow_name
    ctx.state.proposed_parameter_keys = proposed_parameter_keys
    return None


class CandidateWorkflowToAdaptedExecutionPlan(Workflow):
    """Turn one chosen workflow plus task context into an execution-ready adapted plan."""

    name = "candidate_workflow_to_adapted_execution_plan"

    class State(BaseModel):
        selected_workflow_reference: str = ""
        selected_workflow_name: str | None = None
        task_title: str = ""
        sponsor_role: str | None = None
        desired_outcome: str | None = None
        constraints: list[str] = Field(default_factory=list)
        evidence_expectations: list[str] = Field(default_factory=list)
        framing_status: str | None = None
        analysis_status: str | None = None
        packaging_status: str | None = None
        proposed_parameter_keys: list[str] = Field(default_factory=list)
        published: bool = False

    frame_session = Session()
    analysis_session = Session()
    package_session = Session()

    request = Artifact("{run_folder}/request.md")
    framework_architecture_doc = Artifact("{package_folder}/../../docs/architecture.md")
    framework_authoring_doc = Artifact("{package_folder}/../../docs/authoring.md")
    workflow_instructions = Artifact("{package_folder}/../../Workflow_Instructions.md")
    adapted_execution_plan_checklist = Artifact("{package_folder}/assets/adapted_execution_plan_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json", role="managed")
    selected_workflow_capability = Artifact("{workflow_folder}/selected_workflow_capability.json", role="managed")
    adaptation_request_brief = Artifact("{workflow_folder}/adaptation_request_brief.md", role="managed")
    adaptation_success_criteria = Artifact("{workflow_folder}/adaptation_success_criteria.md", role="managed")
    workflow_fit_assessment = Artifact("{workflow_folder}/workflow_fit_assessment.md", role="managed")
    step_adaptation_matrix = Artifact("{workflow_folder}/step_adaptation_matrix.md", role="managed")
    adapted_execution_plan = Artifact("{workflow_folder}/adapted_execution_plan.md", role="managed")
    proposed_workflow_parameters = Artifact("{workflow_folder}/proposed_workflow_parameters.json", role="managed")
    adapted_execution_summary = Artifact("{workflow_folder}/adapted_execution_summary.json", role="managed")
    adapted_execution_next_action = Artifact("{workflow_folder}/adapted_execution_next_action.md", role="managed")
    validated_workflow_parameters = Artifact("{workflow_folder}/validated_workflow_parameters.json", role="managed")
    adapted_execution_plan_receipt = Artifact("{workflow_folder}/adapted_execution_plan_receipt.json", role="managed")

    frame_adaptation_request = produce_verify_step(
        producer_prompt=Prompt.file("prompts/frame_producer.md"),
        verifier_prompt=Prompt.file("prompts/frame_verifier.md"),
        session=frame_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        producer_writes=[adaptation_request_brief, adaptation_success_criteria],
        control_schema=AdaptationRequestFramingPayload,
        routes=FRAME_ADAPTATION_REQUEST_ROUTE_CONTRACTS,
        after_verifier=_after_frame_adaptation_request,
    )
    analyze_adaptation_surface = produce_verify_step(
        producer_prompt=Prompt.file("prompts/analyze_producer.md"),
        verifier_prompt=Prompt.file("prompts/analyze_verifier.md"),
        session=analysis_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            adaptation_request_brief,
            adaptation_success_criteria,
        ],
        producer_writes=[workflow_fit_assessment, step_adaptation_matrix],
        control_schema=AdaptationSurfaceAnalysisPayload,
        routes=ANALYZE_ADAPTATION_SURFACE_ROUTE_CONTRACTS,
        after_verifier=_after_analyze_adaptation_surface,
    )
    package_adapted_execution_plan = produce_verify_step(
        producer_prompt=Prompt.file("prompts/package_producer.md"),
        verifier_prompt=Prompt.file("prompts/package_verifier.md"),
        session=package_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            adapted_execution_plan_checklist,
            adaptation_request_brief,
            adaptation_success_criteria,
            workflow_fit_assessment,
            step_adaptation_matrix,
        ],
        producer_writes=[
            adapted_execution_plan,
            proposed_workflow_parameters,
            adapted_execution_summary,
            adapted_execution_next_action,
        ],
        control_schema=AdaptedExecutionPlanPayload,
        routes=PACKAGE_ADAPTED_EXECUTION_PLAN_ROUTE_CONTRACTS,
        after_verifier=_after_package_adapted_execution_plan,
    )

    @python_step(
        name="bootstrap",
        requires=[request],
        writes=[invocation_contract],
        routes={"inputs_prepared": "capture_selected_workflow_contract"},
    )
    def bootstrap(ctx):
        params = ctx.params
        next_state = ctx.state.model_copy(
            update={
                "selected_workflow_reference": params.selected_workflow,
                "selected_workflow_name": None,
                "task_title": params.task_title,
                "sponsor_role": params.sponsor_role,
                "desired_outcome": params.desired_outcome,
                "constraints": list(params.constraints),
                "evidence_expectations": list(params.evidence_expectations),
                "framing_status": None,
                "analysis_status": None,
                "packaging_status": None,
                "proposed_parameter_keys": [],
                "published": False,
            }
        )
        open_workflow_sessions(ctx, "frame_session", "analysis_session", "package_session")
        write_invocation_contract(
            ctx,
            {
                "selected_workflow_reference": next_state.selected_workflow_reference,
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
        name="capture_selected_workflow_contract",
        requires=[request, invocation_contract],
        writes=[selected_workflow_capability],
        routes={"selected_workflow_contract_captured": "frame_adaptation_request"},
    )
    def capture_selected_workflow_contract(ctx):
        capture = capture_selected_workflow(ctx, ctx.state.selected_workflow_reference)
        snapshot_path = write_selected_workflow_capability_snapshot(ctx, ctx.state.selected_workflow_reference)
        if not snapshot_path.exists():
            raise FileNotFoundError(f"selected workflow capability snapshot was not written at {snapshot_path}")
        ctx.state.selected_workflow_name = capture.selected_workflow_name
        return Event("selected_workflow_contract_captured")


    @python_step(
        name="publish_adapted_execution_plan",
        requires=[
            selected_workflow_capability,
            workflow_fit_assessment,
            step_adaptation_matrix,
            adapted_execution_plan,
            proposed_workflow_parameters,
            adapted_execution_summary,
            adapted_execution_next_action,
        ],
        writes=[validated_workflow_parameters, adapted_execution_plan_receipt],
        routes={"adapted_execution_plan_published": FINISH},
    )
    def publish_adapted_execution_plan(ctx):
        workflow_folder = ctx.workflow_folder
        required_paths = require_existing_artifact_paths(
            {
                "selected_workflow_capability": workflow_folder / "selected_workflow_capability.json",
                "workflow_fit_assessment": workflow_folder / "workflow_fit_assessment.md",
                "step_adaptation_matrix": workflow_folder / "step_adaptation_matrix.md",
                "adapted_execution_plan": workflow_folder / "adapted_execution_plan.md",
                "proposed_workflow_parameters": workflow_folder / "proposed_workflow_parameters.json",
                "adapted_execution_summary": workflow_folder / "adapted_execution_summary.json",
                "adapted_execution_next_action": workflow_folder / "adapted_execution_next_action.md",
            }
        )

        capability_snapshot = read_json_object(required_paths["selected_workflow_capability"])
        snapshot_selected_workflow_name, selected_capability = validate_selected_workflow_capability_snapshot(
            capability_snapshot,
            expected_selected_workflow_name=ctx.state.selected_workflow_name,
            expected_label="workflow state",
        )

        proposed_parameters = read_json_object(required_paths["proposed_workflow_parameters"])

        validated_path = write_validated_workflow_parameters(
            ctx,
            ctx.state.selected_workflow_reference or snapshot_selected_workflow_name,
            proposed_parameters,
        )
        validated_payload = VALIDATED_WORKFLOW_PARAMETERS_ARTIFACT.read(validated_path)
        validate_selected_workflow_artifact_alignment(
            validated_payload.model_dump(mode="python"),
            artifact_name="validated_workflow_parameters.json",
            expected_selected_workflow_name=snapshot_selected_workflow_name,
            expected_artifact_name="selected_workflow_capability.json",
        )
        validated_parameters = dict(validated_payload.validated_parameters)

        summary = ADAPTED_EXECUTION_SUMMARY_ARTIFACT.read(required_paths["adapted_execution_summary"])
        summary_selected_workflow_name = validate_selected_workflow_artifact_alignment(
            summary.model_dump(mode="python"),
            artifact_name="adapted_execution_summary.json",
            expected_selected_workflow_name=snapshot_selected_workflow_name,
            expected_artifact_name="selected_workflow_capability.json",
        )
        summary_entry_step = require_non_empty_string(
            summary.selected_workflow_entry_step,
            error_message="adapted_execution_summary.json must define a non-empty selected_workflow_entry_step",
            coerce=True,
        )
        capability_entry_step = require_non_empty_string(
            selected_capability.get("entry_step_name"),
            error_message="selected_workflow_capability.json must define selected_workflow_capability.entry_step_name",
            coerce=True,
        )
        if summary_entry_step != capability_entry_step:
            raise ValueError(
                "adapted_execution_summary.json selected_workflow_entry_step must match selected_workflow_capability.json"
            )

        summary_parameters_supported = summary.selected_workflow_parameters_supported
        capability_parameters_supported = bool(selected_capability.get("parameters_supported"))
        if summary_parameters_supported is not capability_parameters_supported:
            raise ValueError(
                "adapted_execution_summary.json selected_workflow_parameters_supported must match selected_workflow_capability.json"
            )

        proposed_parameter_keys = require_string_list(
            summary.proposed_parameter_keys,
            error_message="adapted_execution_summary.json must define proposed_parameter_keys as a string list",
            min_length=0,
            dedupe=True,
            coerce=True,
        )
        if sorted(proposed_parameter_keys) != sorted(str(key) for key in validated_parameters):
            raise ValueError(
                "adapted_execution_summary.json proposed_parameter_keys must match validated_workflow_parameters.json"
            )
        if ctx.state.proposed_parameter_keys and sorted(proposed_parameter_keys) != sorted(ctx.state.proposed_parameter_keys):
            raise ValueError("adapted_execution_summary.json proposed_parameter_keys must match workflow state")

        expected_downstream_artifacts = require_string_list(
            summary.expected_downstream_artifacts,
            error_message="adapted_execution_summary.json must define non-empty expected_downstream_artifacts",
            dedupe=True,
            coerce=True,
        )
        authoritative_artifacts = require_string_list(
            summary.authoritative_artifacts,
            error_message="adapted_execution_summary.json must define non-empty authoritative_artifacts",
            dedupe=True,
            coerce=True,
        )
        if not _AUTHORITATIVE_PACKAGE_ARTIFACTS.issubset(authoritative_artifacts):
            raise ValueError(
                "adapted_execution_summary.json authoritative_artifacts must include adapted_execution_plan, adapted_execution_summary, adapted_execution_next_action, and validated_workflow_parameters"
            )

        next_action = require_non_empty_string(
            summary.next_action,
            error_message="adapted_execution_summary.json must define a non-empty next_action",
            coerce=True,
        )
        ready_for_execution = summary.ready_for_execution
        if ready_for_execution is not True:
            raise ValueError("adapted_execution_summary.json must confirm ready_for_execution=true")

        write_publication_receipt(
            ctx,
            "adapted_execution_plan_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "task_title": ctx.state.task_title,
                "sponsor_role": ctx.state.sponsor_role,
                "desired_outcome": ctx.state.desired_outcome,
                "selected_workflow_reference": ctx.state.selected_workflow_reference,
                "selected_workflow_name": summary_selected_workflow_name,
                "selected_workflow_entry_step": summary_entry_step,
                "expected_downstream_artifacts": expected_downstream_artifacts,
                "proposed_parameter_keys": proposed_parameter_keys,
                "next_action": next_action,
                "authoritative_artifacts": authoritative_artifacts,
                "selected_workflow_capability": str(required_paths["selected_workflow_capability"]),
                "workflow_fit_assessment": str(required_paths["workflow_fit_assessment"]),
                "step_adaptation_matrix": str(required_paths["step_adaptation_matrix"]),
                "adapted_execution_plan": str(required_paths["adapted_execution_plan"]),
                "proposed_workflow_parameters": str(required_paths["proposed_workflow_parameters"]),
                "adapted_execution_summary": str(required_paths["adapted_execution_summary"]),
                "adapted_execution_next_action": str(required_paths["adapted_execution_next_action"]),
                "validated_workflow_parameters": str(validated_path),
                "published": True,
            },
        )
        ctx.state.selected_workflow_name = summary_selected_workflow_name
        ctx.state.proposed_parameter_keys = proposed_parameter_keys
        ctx.state.published = True
        return Event("adapted_execution_plan_published")

    entry = bootstrap
