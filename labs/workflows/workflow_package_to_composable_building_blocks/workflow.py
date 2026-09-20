"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

from pathlib import Path

from botpipe import Session, current_run, workflow
from labs.workflows._shared import (
    LabWorkflowResult,
    ReplanRequired,
    artifact,
    execute_candidate_validation,
    finish,
    observe_workflow,
    prepare_selected_candidate_surface,
    run_phase,
)

from .contracts import (
    CandidateDecompositionBuildPayload,
    CandidateDecompositionEvaluationPayload,
    DecompositionPlanPayload,
    DecompositionRequestFramingPayload,
)
from .params import Params


@workflow(name="workflow_package_to_composable_building_blocks", version="2")
def WorkflowPackageToComposableBuildingBlocks(
    params: Params, request: str = ""
) -> LabWorkflowResult:
    """Execute the workflow package to composable building blocks evidence workflow."""
    _producer = Session(key="producer")
    _verifier = Session(key="verifier")
    context = {"request": request, "parameters": params.model_dump(mode="json")}
    context["selected_workflow_contract"] = observe_workflow(params.selected_workflow)
    source_path = context["selected_workflow_contract"]["source"]["path"]
    if not source_path:
        raise ValueError("selected workflow must expose an inspectable source file")
    run = current_run()
    candidate = prepare_selected_candidate_surface(
        source_path,
        str(run.folder / "candidate-workspace"),
        str(run.workspace),
        params.candidate_paths,
    )
    relative_source = str(Path(source_path).resolve().relative_to(candidate.repo_root))
    if relative_source not in candidate.authoritative_hashes:
        raise ValueError("candidate_paths must include the selected workflow source")
    context["candidate_surface"] = {
        "relative_path": relative_source,
        "allowed_roots": list(candidate.allowed_roots),
        "allowed_paths": list(candidate.allowed_paths),
        "authoritative_sha256": candidate.authoritative_hashes[relative_source],
    }
    completed = []
    prior_handles = ()
    frame_decomposition_request_checkpoint = len(completed)
    frame_decomposition_request_reads = prior_handles
    frame_decomposition_request_context = dict(context)
    while True:
        try:
            phase_1 = run_phase(
                phase="frame_decomposition_request",
                returns=DecompositionRequestFramingPayload,
                replan_target="frame_decomposition_request",
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
                    artifact("decomposition_request_brief.md"),
                    artifact("decomposition_success_criteria.md"),
                ),
            )
            completed.append(phase_1)
            prior_handles = prior_handles + phase_1.handles
            design_decomposition_plan_checkpoint = len(completed)
            design_decomposition_plan_reads = prior_handles
            design_decomposition_plan_context = dict(context)
            while True:
                try:
                    phase_2 = run_phase(
                        phase="design_decomposition_plan",
                        returns=DecompositionPlanPayload,
                        replan_target="frame_decomposition_request",
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
                            artifact("decomposition_plan.md"),
                            artifact("building_block_contracts.json"),
                        ),
                    )
                    completed.append(phase_2)
                    prior_handles = prior_handles + phase_2.handles
                    phase_3 = run_phase(
                        phase="implement_candidate_decomposition",
                        returns=CandidateDecompositionBuildPayload,
                        replan_target="design_decomposition_plan",
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
                            artifact("candidate_decomposition_manifest.json"),
                            artifact("candidate_decomposition_notes.md"),
                        ),
                        provider_workspace=candidate.candidate_root,
                    )
                    completed.append(phase_3)
                    prior_handles = prior_handles + phase_3.handles
                    evaluation = execute_candidate_validation(
                        candidate,
                        params.target_test_argv,
                        params.validation_timeout,
                    )
                    if not evaluation.ok:
                        raise ValueError(
                            "candidate validation command failed: "
                            f"returncode={evaluation.command.returncode}; stderr={evaluation.command.stderr}"
                        )
                    if not evaluation.manifest.changed_paths:
                        raise ValueError(
                            "candidate decomposition must change at least one allowed source file"
                        )
                    context["candidate_evaluation"] = evaluation.to_dict()
                    phase_4 = run_phase(
                        phase="evaluate_candidate_decomposition",
                        returns=CandidateDecompositionEvaluationPayload,
                        replan_target="design_decomposition_plan",
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
                            artifact("decomposition_verification_report.md"),
                            artifact("decomposition_summary.json"),
                            artifact("decomposition_next_action.md"),
                        ),
                    )
                    completed.append(phase_4)
                    prior_handles = prior_handles + phase_4.handles
                    break
                except ReplanRequired as change:
                    if change.target != "design_decomposition_plan":
                        raise
                    del completed[design_decomposition_plan_checkpoint:]
                    prior_handles = design_decomposition_plan_reads
                    context = {
                        **design_decomposition_plan_context,
                        "replan_feedback": change.evidence.model_dump(mode="json"),
                        "replan_artifacts": [
                            str(handle.path) for handle in change.handles
                        ],
                    }
            break
        except ReplanRequired as change:
            if change.target != "frame_decomposition_request":
                raise
            del completed[frame_decomposition_request_checkpoint:]
            prior_handles = frame_decomposition_request_reads
            context = {
                **frame_decomposition_request_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    return finish("workflow_package_to_composable_building_blocks", completed)


workflow_callable = WorkflowPackageToComposableBuildingBlocks

__all__ = ["WorkflowPackageToComposableBuildingBlocks", "workflow_callable"]
