"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

from botpipe import Provider, current_run, workflow
from labs.workflows._shared import (
    LabWorkflowResult,
    ReplanRequired,
    artifact,
    finish,
    observe_workflow,
    run_phase,
    validate_selected_workflow_parameters,
)

from .contracts import (
    AdaptationRequestFramingPayload,
    AdaptationSurfaceAnalysisPayload,
    AdaptedExecutionPlanPayload,
)
from .params import Params


@workflow(name="candidate_workflow_to_adapted_execution_plan", version="2")
def CandidateWorkflowToAdaptedExecutionPlan(
    params: Params, request: str = ""
) -> LabWorkflowResult:
    """Execute the candidate workflow to adapted execution plan evidence workflow."""
    _producer = Provider()
    _verifier = _producer.with_config(session=None)
    context = {"request": request, "parameters": params.model_dump(mode="json")}
    context["selected_workflow_contract"] = observe_workflow(params.selected_workflow)
    completed = []
    prior_handles = ()
    frame_adaptation_request_checkpoint = len(completed)
    frame_adaptation_request_reads = prior_handles
    frame_adaptation_request_context = dict(context)
    while True:
        try:
            phase_1 = run_phase(
                phase="frame_adaptation_request",
                returns=AdaptationRequestFramingPayload,
                replan_target="frame_adaptation_request",
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
                    artifact("adaptation_request_brief.md"),
                    artifact("adaptation_success_criteria.md"),
                ),
            )
            completed.append(phase_1)
            prior_handles = prior_handles + phase_1.handles
            analyze_adaptation_surface_checkpoint = len(completed)
            analyze_adaptation_surface_reads = prior_handles
            analyze_adaptation_surface_context = dict(context)
            while True:
                try:
                    phase_2 = run_phase(
                        phase="analyze_adaptation_surface",
                        returns=AdaptationSurfaceAnalysisPayload,
                        replan_target="frame_adaptation_request",
                        producer=_producer,
                        verifier=_verifier,
                        producer_prompt="prompts/analyze_producer.md",
                        verifier_prompt="prompts/analyze_verifier.md",
                        input={
                            **context,
                            "prior_phases": [
                                item.evidence.model_dump(mode="json")
                                for item in completed
                            ],
                        },
                        reads=prior_handles,
                        writes=(
                            artifact("workflow_fit_assessment.md"),
                            artifact("step_adaptation_matrix.md"),
                        ),
                    )
                    completed.append(phase_2)
                    prior_handles = prior_handles + phase_2.handles
                    phase_3 = run_phase(
                        phase="package_adapted_execution_plan",
                        returns=AdaptedExecutionPlanPayload,
                        replan_target="analyze_adaptation_surface",
                        producer=_producer,
                        verifier=_verifier,
                        producer_prompt="prompts/package_producer.md",
                        verifier_prompt="prompts/package_verifier.md",
                        input={
                            **context,
                            "prior_phases": [
                                item.evidence.model_dump(mode="json")
                                for item in completed
                            ],
                        },
                        reads=prior_handles,
                        writes=(
                            artifact("adapted_execution_plan.md"),
                            artifact("proposed_workflow_parameters.json"),
                            artifact("adapted_execution_summary.json"),
                            artifact("adapted_execution_next_action.md"),
                        ),
                    )
                    completed.append(phase_3)
                    prior_handles = prior_handles + phase_3.handles
                    proposed_parameters = next(
                        handle
                        for handle in phase_3.handles
                        if handle.name == "proposed_workflow_parameters"
                    ).read_json()
                    validate_selected_workflow_parameters(
                        params.selected_workflow,
                        str(current_run().workspace),
                        proposed_parameters,
                    )
                    break
                except ReplanRequired as change:
                    if change.target != "analyze_adaptation_surface":
                        raise
                    del completed[analyze_adaptation_surface_checkpoint:]
                    prior_handles = analyze_adaptation_surface_reads
                    context = {
                        **analyze_adaptation_surface_context,
                        "replan_feedback": change.evidence.model_dump(mode="json"),
                        "replan_artifacts": [
                            str(handle.path) for handle in change.handles
                        ],
                    }
            break
        except ReplanRequired as change:
            if change.target != "frame_adaptation_request":
                raise
            del completed[frame_adaptation_request_checkpoint:]
            prior_handles = frame_adaptation_request_reads
            context = {
                **frame_adaptation_request_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    return finish("candidate_workflow_to_adapted_execution_plan", completed)


workflow_callable = CandidateWorkflowToAdaptedExecutionPlan

__all__ = ["CandidateWorkflowToAdaptedExecutionPlan", "workflow_callable"]
