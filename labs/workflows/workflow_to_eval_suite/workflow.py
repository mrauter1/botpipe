"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

from botpipe import Provider, current_run, provider_budget, workflow
from labs.workflows._shared import (
    LabWorkflowResult,
    ReplanRequired,
    artifact,
    finish,
    observe_workflow,
    run_phase,
    validate_selected_eval_manifest,
)
from labs.workflows.optimizer_integration import (
    evaluation_suite_identity,
    load_optimizer_candidate_handoff,
)

from .contracts import (
    EvalCaseDesignPayload,
    EvaluationTargetFramingPayload,
    WorkflowEvalSuitePayload,
)
from .params import Params


def _run_workflow_to_eval_suite(params: Params, request: str) -> LabWorkflowResult:
    """Execute the workflow to eval suite evidence workflow."""
    _producer = Provider()
    context = {"request": request, "parameters": params.model_dump(mode="json")}
    context["selected_workflow_contract"] = observe_workflow(params.selected_workflow)
    optimizer_handoff = None
    if params.optimization_receipt_path:
        optimizer_handoff = load_optimizer_candidate_handoff(
            workspace=str(current_run().workspace),
            optimization_receipt_path=params.optimization_receipt_path,
            candidate_id=params.candidate_id or "",
            expected_selected_workflow=context["selected_workflow_contract"]["name"],
            selected_workflow_reference=params.selected_workflow,
            selected_workflow_source_path=context["selected_workflow_contract"][
                "source"
            ]["path"],
            allowed_kinds=("evaluation_case",),
            max_evidence_bytes=params.max_evidence_bytes,
            max_snapshot_bytes=params.max_snapshot_bytes,
        )
        context["optimizer_handoff"] = optimizer_handoff
        context["evaluation_claim_scope"] = "development_cases"
    completed = []
    prior_handles = ()
    frame_evaluation_target_checkpoint = len(completed)
    frame_evaluation_target_reads = prior_handles
    frame_evaluation_target_context = dict(context)
    while True:
        try:
            phase_1 = run_phase(
                phase="frame_evaluation_target",
                returns=EvaluationTargetFramingPayload,
                replan_target="frame_evaluation_target",
                producer=_producer,
                producer_prompt="prompts/frame_producer.md",
                input=context,
                reads=prior_handles,
                writes=(
                    artifact("evaluation_request_brief.md"),
                    artifact("evaluation_dimensions.md"),
                ),
            )
            framing = EvaluationTargetFramingPayload.model_validate(phase_1.value)
            selected_name = context["selected_workflow_contract"]["name"]
            if framing.selected_workflow_name != selected_name:
                raise ValueError("evaluation framing changed the selected workflow")
            completed.append(phase_1)
            prior_handles = prior_handles + phase_1.handles
            design_eval_cases_checkpoint = len(completed)
            design_eval_cases_reads = prior_handles
            design_eval_cases_context = dict(context)
            while True:
                try:
                    phase_2 = run_phase(
                        phase="design_eval_cases",
                        returns=EvalCaseDesignPayload,
                        replan_target="frame_evaluation_target",
                        producer=_producer,
                        producer_prompt="prompts/design_producer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(
                            artifact("benchmark_case_matrix.md"),
                            artifact("edge_case_matrix.md"),
                            artifact("adversarial_case_matrix.md"),
                            artifact("eval_case_manifest.json"),
                            artifact("eval_rubric.md"),
                        ),
                    )
                    design = EvalCaseDesignPayload.model_validate(phase_2.value)
                    if design.selected_workflow_name != selected_name:
                        raise ValueError("eval design changed the selected workflow")
                    completed.append(phase_2)
                    prior_handles = prior_handles + phase_2.handles
                    proposed_manifest = next(
                        handle
                        for handle in phase_2.handles
                        if handle.name == "eval_case_manifest"
                    ).read_json()
                    validated_manifest = validate_selected_eval_manifest(
                        params.selected_workflow,
                        str(current_run().workspace),
                        proposed_manifest,
                    )
                    context["validated_eval_case_manifest"] = (
                        validated_manifest.model_dump(mode="json")
                    )
                    if design.case_ids != validated_manifest.case_ids:
                        raise ValueError(
                            "typed eval case ids must match the validated manifest"
                        )
                    if design.case_kinds != validated_manifest.case_kinds:
                        raise ValueError(
                            "typed eval case kinds must match the validated manifest"
                        )
                    context["evaluation_suite_id"] = evaluation_suite_identity(
                        context["validated_eval_case_manifest"],
                        source_candidate_id=(
                            optimizer_handoff["candidate_id"]
                            if optimizer_handoff is not None
                            else None
                        ),
                    )
                    phase_3 = run_phase(
                        phase="package_workflow_eval_suite",
                        returns=WorkflowEvalSuitePayload,
                        replan_target="design_eval_cases",
                        producer=_producer,
                        producer_prompt="prompts/package_producer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(
                            artifact("workflow_eval_suite.md"),
                            artifact("workflow_eval_suite_summary.json"),
                            artifact("workflow_eval_next_action.md"),
                        ),
                    )
                    completed.append(phase_3)
                    prior_handles = prior_handles + phase_3.handles
                    details = WorkflowEvalSuitePayload.model_validate(
                        phase_3.value
                    )
                    if details.case_ids != validated_manifest.case_ids:
                        raise ValueError("packaged eval case ids drifted from validation")
                    if details.case_kinds != validated_manifest.case_kinds:
                        raise ValueError(
                            "packaged eval case kinds drifted from validation"
                        )
                    if details.case_count != validated_manifest.case_count:
                        raise ValueError(
                            "packaged eval case count drifted from validation"
                        )
                    if (
                        details.evaluation_suite_id
                        != context["evaluation_suite_id"]
                    ):
                        raise ValueError(
                            "eval suite identity must match the validated case manifest"
                        )
                    expected_candidate = (
                        optimizer_handoff["candidate_id"]
                        if optimizer_handoff is not None
                        else None
                    )
                    if details.source_candidate_id != expected_candidate:
                        raise ValueError(
                            "eval suite source_candidate_id must match the optimizer handoff"
                        )
                    break
                except ReplanRequired as change:
                    if change.target != "design_eval_cases":
                        raise
                    del completed[design_eval_cases_checkpoint:]
                    prior_handles = design_eval_cases_reads
                    context = {
                        **design_eval_cases_context,
                        "replan_feedback": change.evidence.model_dump(mode="json"),
                        "replan_artifacts": [
                            str(handle.path) for handle in change.handles
                        ],
                    }
            break
        except ReplanRequired as change:
            if change.target != "frame_evaluation_target":
                raise
            del completed[frame_evaluation_target_checkpoint:]
            prior_handles = frame_evaluation_target_reads
            context = {
                **frame_evaluation_target_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    return finish("workflow_to_eval_suite", completed)


@workflow(name="workflow_to_eval_suite", version="3")
def WorkflowToEvalSuite(params: Params, request: str = "") -> LabWorkflowResult:
    """Execute the SOP within one durable provider-turn budget."""
    with provider_budget(max_turns=params.max_provider_turns):
        return _run_workflow_to_eval_suite(params, request)


workflow_callable = WorkflowToEvalSuite

__all__ = ["WorkflowToEvalSuite", "workflow_callable"]
