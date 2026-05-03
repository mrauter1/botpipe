"""Reusable evaluation-suite authoring building-block workflow package."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from autoloop_optimizer import (
    capture_selected_workflow,
    write_selected_workflow_capability_snapshot,
    write_validated_eval_case_manifest,
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
    DESIGN_EVAL_CASES_ROUTE_CONTRACTS,
    FRAME_EVALUATION_TARGET_ROUTE_CONTRACTS,
    PACKAGE_WORKFLOW_EVAL_SUITE_ROUTE_CONTRACTS,
    VALIDATED_EVAL_CASE_MANIFEST_ARTIFACT,
    WORKFLOW_EVAL_SUITE_SUMMARY_ARTIFACT,
    EvalCaseDesignPayload,
    EvaluationTargetFramingPayload,
    WorkflowEvalSuitePayload,
)


_AUTHORITATIVE_PACKAGE_ARTIFACTS = frozenset(
    {
        "workflow_eval_suite",
        "workflow_eval_suite_summary",
        "workflow_eval_next_action",
        "validated_eval_case_manifest",
        "eval_rubric",
    }
)
_REQUIRED_CASE_KINDS = ("benchmark", "edge", "adversarial")


def _after_frame_evaluation_target(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    selected_workflow_name = payload.get("selected_workflow_name")
    ctx.state.framing_status = outcome.tag
    if isinstance(selected_workflow_name, str):
        ctx.state.selected_workflow_name = selected_workflow_name
    return None


def _after_design_eval_cases(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    selected_workflow_name = payload.get("selected_workflow_name")
    case_ids = require_string_list(
        payload.get("case_ids"),
        error_message="design verifier payload must define case_ids as a non-empty string list",
        dedupe=True,
        coerce=True,
    )
    case_kinds = _require_case_kinds(
        payload.get("case_kinds"),
        "design verifier payload must define case_kinds as a non-empty string list",
    )
    covered_expected_artifacts = require_string_list(
        payload.get("covered_expected_artifacts"),
        error_message="design verifier payload must define covered_expected_artifacts as a non-empty string list",
        dedupe=True,
        coerce=True,
    )
    ctx.state.design_status = outcome.tag
    if isinstance(selected_workflow_name, str):
        ctx.state.selected_workflow_name = selected_workflow_name
    ctx.state.case_ids = case_ids
    ctx.state.case_kinds = case_kinds
    ctx.state.covered_expected_artifacts = covered_expected_artifacts
    return None


def _after_package_workflow_eval_suite(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    selected_workflow_name = payload.get("selected_workflow_name")
    case_ids = require_string_list(
        payload.get("case_ids"),
        error_message="package verifier payload must define case_ids as a non-empty string list",
        dedupe=True,
        coerce=True,
    )
    case_kinds = _require_case_kinds(
        payload.get("case_kinds"),
        "package verifier payload must define case_kinds as a non-empty string list",
    )
    covered_expected_artifacts = require_string_list(
        payload.get("covered_expected_artifacts"),
        error_message="package verifier payload must define covered_expected_artifacts as a non-empty string list",
        dedupe=True,
        coerce=True,
    )
    ctx.state.packaging_status = outcome.tag
    if isinstance(selected_workflow_name, str):
        ctx.state.selected_workflow_name = selected_workflow_name
    ctx.state.case_ids = case_ids
    ctx.state.case_kinds = case_kinds
    ctx.state.covered_expected_artifacts = covered_expected_artifacts
    return None


class WorkflowToEvalSuite(Workflow):
    """Turn one chosen workflow into a publication-ready evaluation suite."""

    name = "workflow_to_eval_suite"

    class State(BaseModel):
        selected_workflow_reference: str = ""
        selected_workflow_name: str | None = None
        task_title: str = ""
        sponsor_role: str | None = None
        desired_outcome: str | None = None
        constraints: list[str] = Field(default_factory=list)
        evidence_expectations: list[str] = Field(default_factory=list)
        framing_status: str | None = None
        design_status: str | None = None
        packaging_status: str | None = None
        case_ids: list[str] = Field(default_factory=list)
        case_kinds: list[str] = Field(default_factory=list)
        covered_expected_artifacts: list[str] = Field(default_factory=list)
        published: bool = False

    frame_session = Session()
    design_session = Session()
    package_session = Session()

    request = Artifact("{run_folder}/request.md")
    framework_architecture_doc = Artifact("{package_folder}/../../docs/architecture.md")
    framework_authoring_doc = Artifact("{package_folder}/../../docs/authoring.md")
    workflow_instructions = Artifact("{package_folder}/../../Workflow_Instructions.md")
    eval_suite_checklist = Artifact("{package_folder}/assets/eval_suite_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json", role="managed")
    selected_workflow_capability = Artifact("{workflow_folder}/selected_workflow_capability.json", role="managed")
    evaluation_request_brief = Artifact("{workflow_folder}/evaluation_request_brief.md", role="managed")
    evaluation_dimensions = Artifact("{workflow_folder}/evaluation_dimensions.md", role="managed")
    benchmark_case_matrix = Artifact("{workflow_folder}/benchmark_case_matrix.md", role="managed")
    edge_case_matrix = Artifact("{workflow_folder}/edge_case_matrix.md", role="managed")
    adversarial_case_matrix = Artifact("{workflow_folder}/adversarial_case_matrix.md", role="managed")
    eval_case_manifest = Artifact("{workflow_folder}/eval_case_manifest.json", role="managed")
    eval_rubric = Artifact("{workflow_folder}/eval_rubric.md", role="managed")
    workflow_eval_suite = Artifact("{workflow_folder}/workflow_eval_suite.md", role="managed")
    workflow_eval_suite_summary = Artifact("{workflow_folder}/workflow_eval_suite_summary.json", role="managed")
    workflow_eval_next_action = Artifact("{workflow_folder}/workflow_eval_next_action.md", role="managed")
    validated_eval_case_manifest = Artifact("{workflow_folder}/validated_eval_case_manifest.json", role="managed")
    workflow_eval_suite_receipt = Artifact("{workflow_folder}/workflow_eval_suite_receipt.json", role="managed")

    frame_evaluation_target = produce_verify_step(
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
        producer_writes=[evaluation_request_brief, evaluation_dimensions],
        control_schema=EvaluationTargetFramingPayload,
        routes=FRAME_EVALUATION_TARGET_ROUTE_CONTRACTS,
        after_verifier=_after_frame_evaluation_target,
    )
    design_eval_cases = produce_verify_step(
        producer_prompt=Prompt.file("prompts/design_producer.md"),
        verifier_prompt=Prompt.file("prompts/design_verifier.md"),
        session=design_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            evaluation_request_brief,
            evaluation_dimensions,
        ],
        producer_writes=[
            benchmark_case_matrix,
            edge_case_matrix,
            adversarial_case_matrix,
            eval_case_manifest,
            eval_rubric,
        ],
        control_schema=EvalCaseDesignPayload,
        routes=DESIGN_EVAL_CASES_ROUTE_CONTRACTS,
        after_verifier=_after_design_eval_cases,
    )
    package_workflow_eval_suite = produce_verify_step(
        producer_prompt=Prompt.file("prompts/package_producer.md"),
        verifier_prompt=Prompt.file("prompts/package_verifier.md"),
        session=package_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            eval_suite_checklist,
            evaluation_request_brief,
            evaluation_dimensions,
            benchmark_case_matrix,
            edge_case_matrix,
            adversarial_case_matrix,
            eval_case_manifest,
            eval_rubric,
        ],
        producer_writes=[workflow_eval_suite, workflow_eval_suite_summary, workflow_eval_next_action],
        control_schema=WorkflowEvalSuitePayload,
        routes=PACKAGE_WORKFLOW_EVAL_SUITE_ROUTE_CONTRACTS,
        after_verifier=_after_package_workflow_eval_suite,
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
                "design_status": None,
                "packaging_status": None,
                "case_ids": [],
                "case_kinds": [],
                "covered_expected_artifacts": [],
                "published": False,
            }
        )
        open_workflow_sessions(ctx, "frame_session", "design_session", "package_session")
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
        routes={"selected_workflow_contract_captured": "frame_evaluation_target"},
    )
    def capture_selected_workflow_contract(ctx):
        capture = capture_selected_workflow(ctx, ctx.state.selected_workflow_reference)
        snapshot_path = write_selected_workflow_capability_snapshot(ctx, ctx.state.selected_workflow_reference)
        if not snapshot_path.exists():
            raise FileNotFoundError(f"selected workflow capability snapshot was not written at {snapshot_path}")
        ctx.state.selected_workflow_name = capture.selected_workflow_name
        return Event("selected_workflow_contract_captured")

    @python_step(
        name="publish_workflow_eval_suite",
        requires=[
            selected_workflow_capability,
            benchmark_case_matrix,
            edge_case_matrix,
            adversarial_case_matrix,
            eval_case_manifest,
            eval_rubric,
            workflow_eval_suite,
            workflow_eval_suite_summary,
            workflow_eval_next_action,
        ],
        writes=[validated_eval_case_manifest, workflow_eval_suite_receipt],
        routes={"workflow_eval_suite_published": FINISH},
    )
    def publish_workflow_eval_suite(ctx):
        workflow_folder = ctx.workflow_folder
        required_paths = require_existing_artifact_paths(
            {
                "selected_workflow_capability": workflow_folder / "selected_workflow_capability.json",
                "benchmark_case_matrix": workflow_folder / "benchmark_case_matrix.md",
                "edge_case_matrix": workflow_folder / "edge_case_matrix.md",
                "adversarial_case_matrix": workflow_folder / "adversarial_case_matrix.md",
                "eval_case_manifest": workflow_folder / "eval_case_manifest.json",
                "eval_rubric": workflow_folder / "eval_rubric.md",
                "workflow_eval_suite": workflow_folder / "workflow_eval_suite.md",
                "workflow_eval_suite_summary": workflow_folder / "workflow_eval_suite_summary.json",
                "workflow_eval_next_action": workflow_folder / "workflow_eval_next_action.md",
            }
        )

        capability_snapshot = read_json_object(required_paths["selected_workflow_capability"])
        snapshot_selected_workflow_name, selected_capability = validate_selected_workflow_capability_snapshot(
            capability_snapshot,
            expected_selected_workflow_name=ctx.state.selected_workflow_name,
            expected_label="workflow state",
        )

        capability_entry_step = require_non_empty_string(
            selected_capability.get("entry_step_name"),
            error_message="selected_workflow_capability.json must define selected_workflow_capability.entry_step_name",
            coerce=True,
        )
        capability_parameters_supported = bool(selected_capability.get("parameters_supported"))

        proposed_manifest = read_json_object(required_paths["eval_case_manifest"])
        validated_path = write_validated_eval_case_manifest(
            ctx,
            ctx.state.selected_workflow_reference or snapshot_selected_workflow_name,
            proposed_manifest,
        )
        validated_manifest = VALIDATED_EVAL_CASE_MANIFEST_ARTIFACT.read(validated_path)
        validate_selected_workflow_artifact_alignment(
            validated_manifest.model_dump(mode="python"),
            artifact_name="validated_eval_case_manifest.json",
            expected_selected_workflow_name=snapshot_selected_workflow_name,
            expected_artifact_name="selected_workflow_capability.json",
        )

        validated_case_count = validated_manifest.case_count
        if validated_case_count <= 0:
            raise ValueError("validated_eval_case_manifest.json must define positive integer case_count")
        validated_case_ids = require_string_list(
            validated_manifest.case_ids,
            error_message="validated_eval_case_manifest.json must define non-empty case_ids",
            dedupe=True,
            coerce=True,
        )
        validated_case_kinds = _require_case_kinds(
            validated_manifest.case_kinds,
            "validated_eval_case_manifest.json must define non-empty case_kinds",
        )
        if tuple(validated_case_kinds) != _REQUIRED_CASE_KINDS:
            raise ValueError(
                "validated_eval_case_manifest.json case_kinds must include benchmark, edge, and adversarial"
            )
        if validated_case_count != len(validated_case_ids):
            raise ValueError("validated_eval_case_manifest.json case_count must match case_ids length")
        covered_expected_artifacts = sorted(
            {
                artifact_name
                for validated_case in validated_manifest.validated_cases
                for artifact_name in validated_case.expected_artifacts
            }
        )
        if not covered_expected_artifacts:
            raise ValueError("validated_eval_case_manifest.json must cover at least one expected artifact")

        summary = WORKFLOW_EVAL_SUITE_SUMMARY_ARTIFACT.read(required_paths["workflow_eval_suite_summary"])
        summary_selected_workflow_name = validate_selected_workflow_artifact_alignment(
            summary.model_dump(mode="python"),
            artifact_name="workflow_eval_suite_summary.json",
            expected_selected_workflow_name=snapshot_selected_workflow_name,
            expected_artifact_name="selected_workflow_capability.json",
        )
        summary_entry_step = require_non_empty_string(
            summary.selected_workflow_entry_step,
            error_message="workflow_eval_suite_summary.json must define a non-empty selected_workflow_entry_step",
            coerce=True,
        )
        if summary_entry_step != capability_entry_step:
            raise ValueError(
                "workflow_eval_suite_summary.json selected_workflow_entry_step must match selected_workflow_capability.json"
            )

        summary_parameters_supported = summary.selected_workflow_parameters_supported
        if summary_parameters_supported is not capability_parameters_supported:
            raise ValueError(
                "workflow_eval_suite_summary.json selected_workflow_parameters_supported must match selected_workflow_capability.json"
            )

        summary_case_count = summary.case_count
        if summary_case_count <= 0:
            raise ValueError("workflow_eval_suite_summary.json must define positive integer case_count")
        if summary_case_count != validated_case_count:
            raise ValueError("workflow_eval_suite_summary.json case_count must match validated_eval_case_manifest.json")

        summary_case_ids = require_string_list(
            summary.case_ids,
            error_message="workflow_eval_suite_summary.json must define non-empty case_ids",
            dedupe=True,
            coerce=True,
        )
        if summary_case_ids != validated_case_ids:
            raise ValueError("workflow_eval_suite_summary.json case_ids must match validated_eval_case_manifest.json")
        if ctx.state.case_ids and summary_case_ids != ctx.state.case_ids:
            raise ValueError("workflow_eval_suite_summary.json case_ids must match workflow state")

        summary_case_kinds = _require_case_kinds(
            summary.case_kinds,
            "workflow_eval_suite_summary.json must define non-empty case_kinds",
        )
        if summary_case_kinds != validated_case_kinds:
            raise ValueError("workflow_eval_suite_summary.json case_kinds must match validated_eval_case_manifest.json")
        if ctx.state.case_kinds and summary_case_kinds != ctx.state.case_kinds:
            raise ValueError("workflow_eval_suite_summary.json case_kinds must match workflow state")

        summary_covered_expected_artifacts = require_string_list(
            summary.covered_expected_artifacts,
            error_message="workflow_eval_suite_summary.json must define non-empty covered_expected_artifacts",
            dedupe=True,
            coerce=True,
        )
        if summary_covered_expected_artifacts != covered_expected_artifacts:
            raise ValueError(
                "workflow_eval_suite_summary.json covered_expected_artifacts must match validated_eval_case_manifest.json"
            )
        if ctx.state.covered_expected_artifacts and summary_covered_expected_artifacts != ctx.state.covered_expected_artifacts:
            raise ValueError("workflow_eval_suite_summary.json covered_expected_artifacts must match workflow state")

        authoritative_artifacts = require_string_list(
            summary.authoritative_artifacts,
            error_message="workflow_eval_suite_summary.json must define non-empty authoritative_artifacts",
            dedupe=True,
            coerce=True,
        )
        if not _AUTHORITATIVE_PACKAGE_ARTIFACTS.issubset(authoritative_artifacts):
            raise ValueError(
                "workflow_eval_suite_summary.json authoritative_artifacts must include workflow_eval_suite, workflow_eval_suite_summary, workflow_eval_next_action, validated_eval_case_manifest, and eval_rubric"
            )

        next_action = require_non_empty_string(
            summary.next_action,
            error_message="workflow_eval_suite_summary.json must define a non-empty next_action",
            coerce=True,
        )
        ready_for_publication = summary.ready_for_publication
        if ready_for_publication is not True:
            raise ValueError("workflow_eval_suite_summary.json must confirm ready_for_publication=true")

        suite_text = required_paths["workflow_eval_suite"].read_text(encoding="utf-8")
        if snapshot_selected_workflow_name not in suite_text:
            raise ValueError("workflow_eval_suite.md must name the selected workflow")
        if "validated_eval_case_manifest.json" not in suite_text:
            raise ValueError("workflow_eval_suite.md must reference validated_eval_case_manifest.json")
        if "eval_rubric.md" not in suite_text:
            raise ValueError("workflow_eval_suite.md must reference eval_rubric.md")

        next_action_text = required_paths["workflow_eval_next_action"].read_text(encoding="utf-8")
        if "validated_eval_case_manifest.json" not in next_action_text:
            raise ValueError("workflow_eval_next_action.md must reference validated_eval_case_manifest.json")
        if "eval_rubric.md" not in next_action_text:
            raise ValueError("workflow_eval_next_action.md must reference eval_rubric.md")

        write_publication_receipt(
            ctx,
            "workflow_eval_suite_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "task_title": ctx.state.task_title,
                "sponsor_role": ctx.state.sponsor_role,
                "desired_outcome": ctx.state.desired_outcome,
                "selected_workflow_reference": ctx.state.selected_workflow_reference,
                "selected_workflow_name": summary_selected_workflow_name,
                "selected_workflow_entry_step": summary_entry_step,
                "selected_workflow_parameters_supported": summary_parameters_supported,
                "case_count": validated_case_count,
                "case_ids": validated_case_ids,
                "case_kinds": validated_case_kinds,
                "covered_expected_artifacts": covered_expected_artifacts,
                "next_action": next_action,
                "authoritative_artifacts": authoritative_artifacts,
                "selected_workflow_capability": str(required_paths["selected_workflow_capability"]),
                "benchmark_case_matrix": str(required_paths["benchmark_case_matrix"]),
                "edge_case_matrix": str(required_paths["edge_case_matrix"]),
                "adversarial_case_matrix": str(required_paths["adversarial_case_matrix"]),
                "eval_case_manifest": str(required_paths["eval_case_manifest"]),
                "validated_eval_case_manifest": str(validated_path),
                "eval_rubric": str(required_paths["eval_rubric"]),
                "workflow_eval_suite": str(required_paths["workflow_eval_suite"]),
                "workflow_eval_suite_summary": str(required_paths["workflow_eval_suite_summary"]),
                "workflow_eval_next_action": str(required_paths["workflow_eval_next_action"]),
                "published": True,
            },
        )
        ctx.state.selected_workflow_name = summary_selected_workflow_name
        ctx.state.case_ids = validated_case_ids
        ctx.state.case_kinds = validated_case_kinds
        ctx.state.covered_expected_artifacts = covered_expected_artifacts
        ctx.state.published = True
        return Event("workflow_eval_suite_published")

    entry = bootstrap



def _require_case_kinds(value: Any, error_message: str) -> list[str]:
    kinds = require_string_list(value, error_message=error_message, dedupe=True, coerce=True)
    normalized: list[str] = []
    for kind in kinds:
        if kind not in _REQUIRED_CASE_KINDS:
            raise ValueError(error_message)
        if kind not in normalized:
            normalized.append(kind)
    return normalized
