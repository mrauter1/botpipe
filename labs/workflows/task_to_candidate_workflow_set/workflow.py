"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

from botpipe import Provider, provider_budget, workflow
from labs.workflows._shared import (
    LabWorkflowResult,
    ReplanRequired,
    artifact,
    finish,
    observe_catalog,
    run_phase,
)

from .contracts import (
    CandidateRequestFramingPayload,
    CandidateWorkflowAnalysisPayload,
    CandidateWorkflowSetPayload,
)
from .params import Params


def _run_task_to_candidate_workflow_set(
    params: Params, request: str
) -> LabWorkflowResult:
    """Execute the task to candidate workflow set evidence workflow."""
    _producer = Provider()
    context = {"request": request, "parameters": params.model_dump(mode="json")}
    context["workflow_catalog"] = observe_catalog()
    completed = []
    prior_handles = ()
    frame_candidate_request_checkpoint = len(completed)
    frame_candidate_request_reads = prior_handles
    frame_candidate_request_context = dict(context)
    while True:
        try:
            phase_1 = run_phase(
                phase="frame_candidate_request",
                returns=CandidateRequestFramingPayload,
                replan_target="frame_candidate_request",
                producer=_producer,
                producer_prompt="prompts/frame_producer.md",
                input=context,
                reads=prior_handles,
                writes=(
                    artifact("candidate_request_brief.md"),
                    artifact("workflow_fit_criteria.md"),
                ),
            )
            completed.append(phase_1)
            prior_handles = prior_handles + phase_1.handles
            analyze_candidate_workflows_checkpoint = len(completed)
            analyze_candidate_workflows_reads = prior_handles
            analyze_candidate_workflows_context = dict(context)
            while True:
                try:
                    phase_2 = run_phase(
                        phase="analyze_candidate_workflows",
                        returns=CandidateWorkflowAnalysisPayload,
                        replan_target="frame_candidate_request",
                        producer=_producer,
                        producer_prompt="prompts/analyze_producer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(
                            artifact("workflow_comparison_matrix.md"),
                            artifact("fit_gap_analysis.md"),
                        ),
                    )
                    analysis = CandidateWorkflowAnalysisPayload.model_validate(
                        phase_2.value
                    )
                    known_workflows = {
                        entry["name"] for entry in context["workflow_catalog"]
                    }
                    if not set(analysis.compared_workflows) <= known_workflows:
                        raise ValueError("candidate comparison cited an unknown workflow")
                    if not set(analysis.ranked_candidates) <= set(
                        analysis.compared_workflows
                    ):
                        raise ValueError(
                            "ranked candidates must come from compared workflows"
                        )
                    completed.append(phase_2)
                    prior_handles = prior_handles + phase_2.handles
                    phase_3 = run_phase(
                        phase="package_candidate_workflow_set",
                        returns=CandidateWorkflowSetPayload,
                        replan_target="analyze_candidate_workflows",
                        producer=_producer,
                        producer_prompt="prompts/package_producer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(
                            artifact("candidate_workflow_set.md"),
                            artifact("candidate_workflow_set_summary.json"),
                            artifact("candidate_workflow_next_action.md"),
                        ),
                    )
                    package = CandidateWorkflowSetPayload.model_validate(phase_3.value)
                    if package.comparison_candidates != analysis.compared_workflows:
                        raise ValueError(
                            "packaged comparison candidates must match the analysis"
                        )
                    if package.ranked_candidates != analysis.ranked_candidates:
                        raise ValueError("packaged ranking must match the analysis")
                    if not set(package.recommended_candidate_workflows) <= set(
                        package.ranked_candidates
                    ):
                        raise ValueError(
                            "recommended workflows must come from ranked candidates"
                        )
                    if package.builder_baseline_workflow not in known_workflows:
                        raise ValueError("builder baseline must name a known workflow")
                    completed.append(phase_3)
                    prior_handles = prior_handles + phase_3.handles
                    break
                except ReplanRequired as change:
                    if change.target != "analyze_candidate_workflows":
                        raise
                    del completed[analyze_candidate_workflows_checkpoint:]
                    prior_handles = analyze_candidate_workflows_reads
                    context = {
                        **analyze_candidate_workflows_context,
                        "replan_feedback": change.evidence.model_dump(mode="json"),
                        "replan_artifacts": [
                            str(handle.path) for handle in change.handles
                        ],
                    }
            break
        except ReplanRequired as change:
            if change.target != "frame_candidate_request":
                raise
            del completed[frame_candidate_request_checkpoint:]
            prior_handles = frame_candidate_request_reads
            context = {
                **frame_candidate_request_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    return finish("task_to_candidate_workflow_set", completed)


@workflow(name="task_to_candidate_workflow_set", version="3")
def TaskToCandidateWorkflowSet(
    params: Params, request: str = ""
) -> LabWorkflowResult:
    """Execute the SOP within one durable provider-turn budget."""
    with provider_budget(max_turns=params.max_provider_turns):
        return _run_task_to_candidate_workflow_set(params, request)


workflow_callable = TaskToCandidateWorkflowSet

__all__ = ["TaskToCandidateWorkflowSet", "workflow_callable"]
