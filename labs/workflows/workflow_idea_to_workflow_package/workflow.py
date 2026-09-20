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
    CandidateSelectionPayload,
    WorkflowBuildPayload,
    WorkflowDesignPayload,
    WorkflowEvaluationPayload,
)
from .params import Params


@workflow(name="workflow_idea_to_workflow_package", version="2")
def WorkflowIdeaToWorkflowPackage(
    params: Params, request: str = ""
) -> LabWorkflowResult:
    """Execute the workflow idea to workflow package evidence workflow."""
    _producer = Session(key="producer")
    _verifier = Session(key="verifier")
    context = {"request": request, "parameters": params.model_dump(mode="json")}
    context["workflow_catalog"] = observe_catalog()
    completed = []
    prior_handles = ()
    frame_candidate_checkpoint = len(completed)
    frame_candidate_reads = prior_handles
    frame_candidate_context = dict(context)
    while True:
        try:
            phase_1 = run_phase(
                phase="frame_candidate",
                returns=CandidateSelectionPayload,
                replan_target="frame_candidate",
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
                    artifact("workflow_idea_brief.md"),
                    artifact("candidate_selection_criteria.md"),
                ),
            )
            completed.append(phase_1)
            prior_handles = prior_handles + phase_1.handles
            design_package_checkpoint = len(completed)
            design_package_reads = prior_handles
            design_package_context = dict(context)
            while True:
                try:
                    phase_2 = run_phase(
                        phase="design_package",
                        returns=WorkflowDesignPayload,
                        replan_target="frame_candidate",
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
                            artifact("workflow_design.md"),
                            artifact("workflow_contract.json"),
                        ),
                    )
                    completed.append(phase_2)
                    prior_handles = prior_handles + phase_2.handles
                    phase_3 = run_phase(
                        phase="build_package",
                        returns=WorkflowBuildPayload,
                        replan_target="design_package",
                        producer=_producer,
                        verifier=_verifier,
                        producer_prompt="prompts/build_producer.md",
                        verifier_prompt="prompts/build_verifier.md",
                        input={
                            **context,
                            "prior_phases": [
                                item.evidence.model_dump(mode="json")
                                for item in completed
                            ],
                        },
                        reads=prior_handles,
                        writes=(
                            artifact("workflow_package_manifest.json"),
                            artifact("implementation_notes.md"),
                        ),
                    )
                    completed.append(phase_3)
                    prior_handles = prior_handles + phase_3.handles
                    phase_4 = run_phase(
                        phase="evaluate_package",
                        returns=WorkflowEvaluationPayload,
                        replan_target="design_package",
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
                            artifact("workflow_evaluation.md"),
                            artifact("workflow_package_summary.json"),
                            artifact("workflow_next_action.md"),
                        ),
                    )
                    completed.append(phase_4)
                    prior_handles = prior_handles + phase_4.handles
                    break
                except ReplanRequired as change:
                    if change.target != "design_package":
                        raise
                    del completed[design_package_checkpoint:]
                    prior_handles = design_package_reads
                    context = {
                        **design_package_context,
                        "replan_feedback": change.evidence.model_dump(mode="json"),
                        "replan_artifacts": [
                            str(handle.path) for handle in change.handles
                        ],
                    }
            break
        except ReplanRequired as change:
            if change.target != "frame_candidate":
                raise
            del completed[frame_candidate_checkpoint:]
            prior_handles = frame_candidate_reads
            context = {
                **frame_candidate_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    return finish("workflow_idea_to_workflow_package", completed)


workflow_callable = WorkflowIdeaToWorkflowPackage

__all__ = ["WorkflowIdeaToWorkflowPackage", "workflow_callable"]
