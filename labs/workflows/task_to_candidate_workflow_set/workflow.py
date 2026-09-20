"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

from botpipe import Session, workflow
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


@workflow(name="task_to_candidate_workflow_set", version="2")
def TaskToCandidateWorkflowSet(params: Params, request: str = "") -> LabWorkflowResult:
    """Execute the task to candidate workflow set evidence workflow."""
    _producer = Session(key="producer")
    _verifier = Session(key="verifier")
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
                            artifact("workflow_comparison_matrix.md"),
                            artifact("fit_gap_analysis.md"),
                        ),
                    )
                    completed.append(phase_2)
                    prior_handles = prior_handles + phase_2.handles
                    phase_3 = run_phase(
                        phase="package_candidate_workflow_set",
                        returns=CandidateWorkflowSetPayload,
                        replan_target="analyze_candidate_workflows",
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
                            artifact("candidate_workflow_set.md"),
                            artifact("candidate_workflow_set_summary.json"),
                            artifact("candidate_workflow_next_action.md"),
                        ),
                    )
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


workflow_callable = TaskToCandidateWorkflowSet

__all__ = ["TaskToCandidateWorkflowSet", "workflow_callable"]
