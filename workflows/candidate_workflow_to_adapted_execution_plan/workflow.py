"""Selected-workflow adaptation-planning building-block workflow package."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.stdlib import (
        normalize_optional_string,
        normalize_unique_strings,
        read_json_object,
        require_mapping,
        require_non_empty_string,
        require_string_list,
        validate_selected_workflow_artifact_alignment,
        validate_selected_workflow_capability_snapshot,
        write_selected_workflow_capability_snapshot,
        write_validated_workflow_parameters,
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
        require_non_empty_string,
        require_string_list,
        validate_selected_workflow_artifact_alignment,
        validate_selected_workflow_capability_snapshot,
        write_selected_workflow_capability_snapshot,
        write_validated_workflow_parameters,
    )
    from stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from workflow import Artifact, FAIL, PairStep, Session, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event, Outcome

from .contracts import (
    ANALYZE_ADAPTATION_SURFACE_ROUTE_CONTRACTS,
    FRAME_ADAPTATION_REQUEST_ROUTE_CONTRACTS,
    PACKAGE_ADAPTED_EXECUTION_PLAN_ROUTE_CONTRACTS,
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

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json")
    selected_workflow_capability = Artifact("{workflow_folder}/selected_workflow_capability.json")
    adaptation_request_brief = Artifact("{workflow_folder}/adaptation_request_brief.md")
    adaptation_success_criteria = Artifact("{workflow_folder}/adaptation_success_criteria.md")
    workflow_fit_assessment = Artifact("{workflow_folder}/workflow_fit_assessment.md")
    step_adaptation_matrix = Artifact("{workflow_folder}/step_adaptation_matrix.md")
    adapted_execution_plan = Artifact("{workflow_folder}/adapted_execution_plan.md")
    proposed_workflow_parameters = Artifact("{workflow_folder}/proposed_workflow_parameters.json")
    adapted_execution_summary = Artifact("{workflow_folder}/adapted_execution_summary.json")
    adapted_execution_next_action = Artifact("{workflow_folder}/adapted_execution_next_action.md")
    validated_workflow_parameters = Artifact("{workflow_folder}/validated_workflow_parameters.json")
    adapted_execution_plan_receipt = Artifact("{workflow_folder}/adapted_execution_plan_receipt.json")

    bootstrap = SystemStep(
        name="bootstrap",
        requires=[request],
        produces={"invocation_contract": invocation_contract},
    )
    capture_selected_workflow_contract = SystemStep(
        name="capture_selected_workflow_contract",
        requires=[request, invocation_contract],
        produces={"selected_workflow_capability": selected_workflow_capability},
    )
    frame_adaptation_request = PairStep(
        name="frame_adaptation_request",
        session=frame_session,
        producer="prompts/frame_producer.md",
        verifier="prompts/frame_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        produces={
            "adaptation_request_brief": adaptation_request_brief,
            "adaptation_success_criteria": adaptation_success_criteria,
        },
        expected_output_schema=AdaptationRequestFramingPayload,
        route_contracts=FRAME_ADAPTATION_REQUEST_ROUTE_CONTRACTS,
    )
    analyze_adaptation_surface = PairStep(
        name="analyze_adaptation_surface",
        session=analysis_session,
        producer="prompts/analyze_producer.md",
        verifier="prompts/analyze_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            adaptation_request_brief,
            adaptation_success_criteria,
        ],
        produces={
            "workflow_fit_assessment": workflow_fit_assessment,
            "step_adaptation_matrix": step_adaptation_matrix,
        },
        expected_output_schema=AdaptationSurfaceAnalysisPayload,
        route_contracts=ANALYZE_ADAPTATION_SURFACE_ROUTE_CONTRACTS,
    )
    package_adapted_execution_plan = PairStep(
        name="package_adapted_execution_plan",
        session=package_session,
        producer="prompts/package_producer.md",
        verifier="prompts/package_verifier.md",
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
        produces={
            "adapted_execution_plan": adapted_execution_plan,
            "proposed_workflow_parameters": proposed_workflow_parameters,
            "adapted_execution_summary": adapted_execution_summary,
            "adapted_execution_next_action": adapted_execution_next_action,
        },
        expected_output_schema=AdaptedExecutionPlanPayload,
        route_contracts=PACKAGE_ADAPTED_EXECUTION_PLAN_ROUTE_CONTRACTS,
    )
    publish_adapted_execution_plan = SystemStep(
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
        produces={
            "validated_workflow_parameters": validated_workflow_parameters,
            "adapted_execution_plan_receipt": adapted_execution_plan_receipt,
        },
    )

    entry = bootstrap

    transitions = merge_transitions(
        global_routes(pause_on_outcome_tags("question", "blocked"), failed=FAIL),
        {
            bootstrap: {"inputs_prepared": capture_selected_workflow_contract},
            capture_selected_workflow_contract: {"selected_workflow_contract_captured": frame_adaptation_request},
            frame_adaptation_request: {
                "adaptation_request_framed": analyze_adaptation_surface,
                "needs_rework": frame_adaptation_request,
                "needs_replan": frame_adaptation_request,
            },
            analyze_adaptation_surface: {
                "adaptation_surface_analyzed": package_adapted_execution_plan,
                "needs_rework": analyze_adaptation_surface,
                "needs_replan": frame_adaptation_request,
            },
            package_adapted_execution_plan: {
                "adapted_execution_plan_ready": publish_adapted_execution_plan,
                "needs_rework": package_adapted_execution_plan,
                "needs_replan": analyze_adaptation_surface,
            },
            publish_adapted_execution_plan: {"adapted_execution_plan_published": SUCCESS},
        },
    )

    @staticmethod
    def on_bootstrap(state: State, ctx) -> tuple[State, Event]:
        payload = dict(ctx.workflow_params)
        selected_workflow_reference = require_non_empty_string(
            payload.get("selected_workflow"),
            error_message="candidate_workflow_to_adapted_execution_plan requires workflow parameter 'selected_workflow'",
            coerce=True,
        )
        task_title = require_non_empty_string(
            payload.get("task_title"),
            error_message="candidate_workflow_to_adapted_execution_plan requires workflow parameter 'task_title'",
            coerce=True,
        )

        next_state = state.model_copy(
            update={
                "selected_workflow_reference": selected_workflow_reference,
                "selected_workflow_name": None,
                "task_title": task_title,
                "sponsor_role": normalize_optional_string(payload.get("sponsor_role")),
                "desired_outcome": normalize_optional_string(payload.get("desired_outcome")),
                "constraints": normalize_unique_strings(payload.get("constraints")),
                "evidence_expectations": normalize_unique_strings(payload.get("evidence_expectations")),
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
        return next_state, Event("inputs_prepared")

    @staticmethod
    def on_capture_selected_workflow_contract(state: State, ctx) -> tuple[State, Event]:
        snapshot_path = write_selected_workflow_capability_snapshot(ctx, state.selected_workflow_reference)
        if not snapshot_path.exists():
            raise FileNotFoundError(f"selected workflow capability snapshot was not written at {snapshot_path}")

        snapshot = read_json_object(snapshot_path)
        selected_workflow_name, _ = validate_selected_workflow_capability_snapshot(snapshot)
        return (
            state.model_copy(update={"selected_workflow_name": selected_workflow_name}),
            Event("selected_workflow_contract_captured"),
        )

    @staticmethod
    def on_frame_adaptation_request(state: State, outcome: Outcome, artifacts):
        del artifacts
        payload = outcome.payload
        selected_workflow_name = payload.get("selected_workflow_name")
        return state.model_copy(
            update={
                "framing_status": outcome.tag,
                "selected_workflow_name": (
                    selected_workflow_name if isinstance(selected_workflow_name, str) else state.selected_workflow_name
                ),
            }
        )

    @staticmethod
    def on_analyze_adaptation_surface(state: State, outcome: Outcome, artifacts):
        del artifacts
        payload = outcome.payload
        selected_workflow_name = payload.get("selected_workflow_name")
        return state.model_copy(
            update={
                "analysis_status": outcome.tag,
                "selected_workflow_name": (
                    selected_workflow_name if isinstance(selected_workflow_name, str) else state.selected_workflow_name
                ),
            }
        )

    @staticmethod
    def on_package_adapted_execution_plan(state: State, outcome: Outcome, artifacts):
        del artifacts
        payload = outcome.payload
        selected_workflow_name = payload.get("selected_workflow_name")
        proposed_parameter_keys = require_string_list(
            payload.get("proposed_parameter_keys"),
            error_message="package verifier payload must define proposed_parameter_keys as a string list",
            min_length=0,
            dedupe=True,
            coerce=True,
        )
        return state.model_copy(
            update={
                "packaging_status": outcome.tag,
                "selected_workflow_name": (
                    selected_workflow_name if isinstance(selected_workflow_name, str) else state.selected_workflow_name
                ),
                "proposed_parameter_keys": proposed_parameter_keys,
            }
        )

    @staticmethod
    def on_publish_adapted_execution_plan(state: State, ctx) -> tuple[State, Event]:
        workflow_folder = ctx.workflow_folder
        required_paths = {
            "selected_workflow_capability": workflow_folder / "selected_workflow_capability.json",
            "workflow_fit_assessment": workflow_folder / "workflow_fit_assessment.md",
            "step_adaptation_matrix": workflow_folder / "step_adaptation_matrix.md",
            "adapted_execution_plan": workflow_folder / "adapted_execution_plan.md",
            "proposed_workflow_parameters": workflow_folder / "proposed_workflow_parameters.json",
            "adapted_execution_summary": workflow_folder / "adapted_execution_summary.json",
            "adapted_execution_next_action": workflow_folder / "adapted_execution_next_action.md",
        }
        for artifact_path in required_paths.values():
            if not artifact_path.exists():
                raise FileNotFoundError(f"missing required publication artifact at {artifact_path}")

        capability_snapshot = read_json_object(required_paths["selected_workflow_capability"])
        snapshot_selected_workflow_name, selected_capability = validate_selected_workflow_capability_snapshot(
            capability_snapshot,
            expected_selected_workflow_name=state.selected_workflow_name,
            expected_label="workflow state",
        )

        proposed_parameters = read_json_object(required_paths["proposed_workflow_parameters"])

        validated_path = write_validated_workflow_parameters(
            ctx,
            state.selected_workflow_reference or snapshot_selected_workflow_name,
            proposed_parameters,
        )
        validated_payload = read_json_object(validated_path)
        validate_selected_workflow_artifact_alignment(
            validated_payload,
            artifact_name="validated_workflow_parameters.json",
            expected_selected_workflow_name=snapshot_selected_workflow_name,
            expected_artifact_name="selected_workflow_capability.json",
        )
        validated_parameters = require_mapping(
            validated_payload.get("validated_parameters"),
            error_message="validated_workflow_parameters.json must define validated_parameters as a JSON object",
        )

        summary = read_json_object(required_paths["adapted_execution_summary"])
        summary_selected_workflow_name = validate_selected_workflow_artifact_alignment(
            summary,
            artifact_name="adapted_execution_summary.json",
            expected_selected_workflow_name=snapshot_selected_workflow_name,
            expected_artifact_name="selected_workflow_capability.json",
        )
        summary_entry_step = require_non_empty_string(
            summary.get("selected_workflow_entry_step"),
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

        summary_parameters_supported = summary.get("selected_workflow_parameters_supported")
        if not isinstance(summary_parameters_supported, bool):
            raise ValueError(
                "adapted_execution_summary.json must define boolean selected_workflow_parameters_supported"
            )
        capability_parameters_supported = bool(selected_capability.get("parameters_supported"))
        if summary_parameters_supported is not capability_parameters_supported:
            raise ValueError(
                "adapted_execution_summary.json selected_workflow_parameters_supported must match selected_workflow_capability.json"
            )

        proposed_parameter_keys = require_string_list(
            summary.get("proposed_parameter_keys"),
            error_message="adapted_execution_summary.json must define proposed_parameter_keys as a string list",
            min_length=0,
            dedupe=True,
            coerce=True,
        )
        if sorted(proposed_parameter_keys) != sorted(str(key) for key in validated_parameters):
            raise ValueError(
                "adapted_execution_summary.json proposed_parameter_keys must match validated_workflow_parameters.json"
            )
        if state.proposed_parameter_keys and sorted(proposed_parameter_keys) != sorted(state.proposed_parameter_keys):
            raise ValueError("adapted_execution_summary.json proposed_parameter_keys must match workflow state")

        expected_downstream_artifacts = require_string_list(
            summary.get("expected_downstream_artifacts"),
            error_message="adapted_execution_summary.json must define non-empty expected_downstream_artifacts",
            dedupe=True,
            coerce=True,
        )
        authoritative_artifacts = require_string_list(
            summary.get("authoritative_artifacts"),
            error_message="adapted_execution_summary.json must define non-empty authoritative_artifacts",
            dedupe=True,
            coerce=True,
        )
        if not _AUTHORITATIVE_PACKAGE_ARTIFACTS.issubset(authoritative_artifacts):
            raise ValueError(
                "adapted_execution_summary.json authoritative_artifacts must include adapted_execution_plan, adapted_execution_summary, adapted_execution_next_action, and validated_workflow_parameters"
            )

        next_action = require_non_empty_string(
            summary.get("next_action"),
            error_message="adapted_execution_summary.json must define a non-empty next_action",
            coerce=True,
        )
        ready_for_execution = summary.get("ready_for_execution")
        if ready_for_execution is not True:
            raise ValueError("adapted_execution_summary.json must confirm ready_for_execution=true")

        write_publication_receipt(
            ctx,
            "adapted_execution_plan_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "task_title": state.task_title,
                "sponsor_role": state.sponsor_role,
                "desired_outcome": state.desired_outcome,
                "selected_workflow_reference": state.selected_workflow_reference,
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
        return (
            state.model_copy(
                update={
                    "selected_workflow_name": summary_selected_workflow_name,
                    "proposed_parameter_keys": proposed_parameter_keys,
                    "published": True,
                }
            ),
            Event("adapted_execution_plan_published"),
        )

    on_outcome = staticmethod(event_on_outcome_tags("question", "blocked", "failed"))
