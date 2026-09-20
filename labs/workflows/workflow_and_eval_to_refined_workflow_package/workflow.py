"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

from pathlib import Path

from botpipe import Session, current_run, workflow
from labs.workflows._shared import (
    LabWorkflowResult,
    ReplanRequired,
    artifact,
    finish,
    observe_workflow,
    prepare_selected_candidate_surface,
    run_phase,
)
from labs.workflows.optimizer_integration import (
    freeze_candidate_baseline,
    load_legacy_evaluation_inputs,
    load_optimizer_candidate_handoff,
    staged_workflow_reference,
    validate_candidate_and_compare,
    validate_materialized_handoff,
)

from .contracts import (
    RefinementRequestFramingPayload,
    WorkflowRefinementBuildPayload,
    WorkflowRefinementEvaluationPayload,
    WorkflowRefinementPlanPayload,
)
from .params import Params


@workflow(name="workflow_and_eval_to_refined_workflow_package", version="2")
def WorkflowAndEvalToRefinedWorkflowPackage(
    params: Params, request: str = ""
) -> LabWorkflowResult:
    """Execute the workflow and eval to refined workflow package evidence workflow."""
    _producer = Session(key="producer")
    _verifier = Session(key="verifier")
    context = {"request": request, "parameters": params.model_dump(mode="json")}
    context["selected_workflow_contract"] = observe_workflow(params.selected_workflow)
    selected_workflow_name = context["selected_workflow_contract"]["name"]
    optimizer_handoff = None
    if params.optimization_receipt_path:
        optimizer_handoff = load_optimizer_candidate_handoff(
            workspace=str(current_run().workspace),
            optimization_receipt_path=params.optimization_receipt_path,
            candidate_id=params.candidate_id or "",
            expected_selected_workflow=selected_workflow_name,
            selected_workflow_reference=params.selected_workflow,
            selected_workflow_source_path=context["selected_workflow_contract"][
                "source"
            ]["path"],
            allowed_kinds=(
                "producer_prompt",
                "verifier_rubric",
                "tokens",
                "workflow",
            ),
        )
        context["optimizer_handoff"] = optimizer_handoff
    else:
        context["legacy_evaluation"] = load_legacy_evaluation_inputs(
            workspace=str(current_run().workspace),
            evaluation_summary_path=params.evaluation_summary_path or "",
            evaluation_findings_path=params.evaluation_findings_path or "",
            expected_selected_workflow=selected_workflow_name,
        )
    source_path = context["selected_workflow_contract"]["source"]["path"]
    if not source_path:
        raise ValueError("selected workflow must expose an inspectable source file")
    run = current_run()
    candidate = prepare_selected_candidate_surface(
        source_path,
        str(run.folder / "candidate-workspace"),
        str(run.workspace),
        (
            optimizer_handoff["candidate_paths"]
            if optimizer_handoff is not None
            else params.candidate_paths
        ),
    )
    if optimizer_handoff is not None:
        validate_materialized_handoff(
            optimizer_handoff,
            candidate.authoritative_hashes,
        )
    relative_source = str(Path(source_path).resolve().relative_to(candidate.repo_root))
    if relative_source not in candidate.authoritative_hashes:
        raise ValueError("candidate_paths must include the selected workflow source")
    validation_reference = staged_workflow_reference(
        params.selected_workflow,
        relative_source=relative_source,
        function=context["selected_workflow_contract"].get("function"),
    )
    context["candidate_surface"] = {
        "relative_path": relative_source,
        "allowed_roots": list(candidate.allowed_roots),
        "allowed_paths": list(candidate.allowed_paths),
        "authoritative_sha256": candidate.authoritative_hashes[relative_source],
    }
    frozen_candidate = freeze_candidate_baseline(
        candidate_workspace=candidate,
        selected_workflow=params.selected_workflow,
        staging_parent=str(run.folder / "candidate-execution" / "frozen"),
        workspace=str(run.workspace),
    )
    context["frozen_candidate"] = {
        "execution_tree_id": frozen_candidate["snapshot"]["execution_tree_id"],
        "baseline_surface_id": frozen_candidate["baseline_surface_manifest"][
            "surface_id"
        ],
    }
    completed = []
    prior_handles = ()
    frame_refinement_request_checkpoint = len(completed)
    frame_refinement_request_reads = prior_handles
    frame_refinement_request_context = dict(context)
    while True:
        try:
            phase_1 = run_phase(
                phase="frame_refinement_request",
                returns=RefinementRequestFramingPayload,
                replan_target="frame_refinement_request",
                producer=_producer,
                verifier=_verifier,
                producer_prompt="prompts/frame_producer.md",
                verifier_prompt="prompts/frame_verifier.md",
                input={
                    **context,
                    "prior_phases": [
                        item.evidence.model_dump(mode="json") for item in completed
                    ],
                },
                reads=prior_handles,
                writes=(
                    artifact("refinement_request_brief.md"),
                    artifact("refinement_success_criteria.md"),
                ),
            )
            completed.append(phase_1)
            prior_handles = prior_handles + phase_1.handles
            design_refinement_plan_checkpoint = len(completed)
            design_refinement_plan_reads = prior_handles
            design_refinement_plan_context = dict(context)
            while True:
                try:
                    phase_2 = run_phase(
                        phase="design_refinement_plan",
                        returns=WorkflowRefinementPlanPayload,
                        replan_target="frame_refinement_request",
                        producer=_producer,
                        verifier=_verifier,
                        producer_prompt="prompts/design_producer.md",
                        verifier_prompt="prompts/design_verifier.md",
                        input={
                            **context,
                            "prior_phases": [
                                item.evidence.model_dump(mode="json")
                                for item in completed
                            ],
                        },
                        reads=prior_handles,
                        writes=(
                            artifact("workflow_refinement_plan.md"),
                            artifact("candidate_change_manifest.json"),
                        ),
                    )
                    completed.append(phase_2)
                    prior_handles = prior_handles + phase_2.handles
                    phase_3 = run_phase(
                        phase="implement_refined_workflow",
                        returns=WorkflowRefinementBuildPayload,
                        replan_target="design_refinement_plan",
                        producer=_producer,
                        verifier=_verifier,
                        producer_prompt="prompts/implement_producer.md",
                        verifier_prompt="prompts/implement_verifier.md",
                        input={
                            **context,
                            "prior_phases": [
                                item.evidence.model_dump(mode="json")
                                for item in completed
                            ],
                        },
                        reads=prior_handles
                        + (candidate.baseline_root / relative_source,),
                        writes=(
                            artifact("candidate_workflow_manifest.json"),
                            artifact("candidate_implementation_notes.md"),
                        ),
                        provider_workspace=candidate.candidate_root,
                    )
                    completed.append(phase_3)
                    prior_handles = prior_handles + phase_3.handles
                    evaluation = validate_candidate_and_compare(
                        candidate_workspace=candidate,
                        frozen_candidate=frozen_candidate,
                        selected_workflow=validation_reference,
                        staging_parent=str(run.folder / "candidate-execution"),
                        target_test_argv=params.target_test_argv or (),
                        validation_timeout=params.validation_timeout,
                        evaluation_spec_path=params.evaluation_spec_path,
                        workspace=str(run.workspace),
                        invocation_id=run.run_id,
                    )
                    context["candidate_evaluation"] = evaluation["validation"]
                    context["candidate_manifest"] = evaluation["candidate_manifest"]
                    context["paired_evaluation"] = evaluation["paired_evaluation"]
                    phase_4 = run_phase(
                        phase="evaluate_refined_workflow",
                        returns=WorkflowRefinementEvaluationPayload,
                        replan_target="design_refinement_plan",
                        producer=_producer,
                        verifier=_verifier,
                        producer_prompt="prompts/evaluate_producer.md",
                        verifier_prompt="prompts/evaluate_verifier.md",
                        input={
                            **context,
                            "prior_phases": [
                                item.evidence.model_dump(mode="json")
                                for item in completed
                            ],
                        },
                        reads=prior_handles,
                        writes=(
                            artifact("candidate_verification_report.md"),
                            artifact("refinement_summary.json"),
                            artifact("refinement_next_action.md"),
                        ),
                    )
                    completed.append(phase_4)
                    prior_handles = prior_handles + phase_4.handles
                    break
                except ReplanRequired as change:
                    if change.target != "design_refinement_plan":
                        raise
                    del completed[design_refinement_plan_checkpoint:]
                    prior_handles = design_refinement_plan_reads
                    context = {
                        **design_refinement_plan_context,
                        "replan_feedback": change.evidence.model_dump(mode="json"),
                        "replan_artifacts": [
                            str(handle.path) for handle in change.handles
                        ],
                    }
            break
        except ReplanRequired as change:
            if change.target != "frame_refinement_request":
                raise
            del completed[frame_refinement_request_checkpoint:]
            prior_handles = frame_refinement_request_reads
            context = {
                **frame_refinement_request_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    return finish("workflow_and_eval_to_refined_workflow_package", completed)


workflow_callable = WorkflowAndEvalToRefinedWorkflowPackage

__all__ = ["WorkflowAndEvalToRefinedWorkflowPackage", "workflow_callable"]
