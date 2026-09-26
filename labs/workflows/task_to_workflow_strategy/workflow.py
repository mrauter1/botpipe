"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

import json

from botpipe import Provider, provider_budget, workflow
from labs.workflows._shared import (
    LabWorkflowResult,
    ReplanRequired,
    artifact,
    finish,
    observe_catalog,
    run_phase,
)
from labs.workflows.task_to_candidate_workflow_set import (
    Params as CandidateParams,
)
from labs.workflows.task_to_candidate_workflow_set import (
    TaskToCandidateWorkflowSet,
)

from .contracts import (
    StrategyPackagePayload,
    StrategySelectionPayload,
    TaskFramingPayload,
)
from .params import Params


def _run_task_to_workflow_strategy(params: Params, request: str) -> LabWorkflowResult:
    """Execute the task to workflow strategy evidence workflow."""
    _producer = Provider()
    context = {"request": request, "parameters": params.model_dump(mode="json")}
    context["workflow_catalog"] = observe_catalog()
    completed = []
    prior_handles = ()
    frame_task_checkpoint = len(completed)
    frame_task_reads = prior_handles
    frame_task_context = dict(context)
    while True:
        try:
            phase_1 = run_phase(
                phase="frame_task",
                returns=TaskFramingPayload,
                replan_target="frame_task",
                producer=_producer,
                producer_prompt="prompts/frame_producer.md",
                input=context,
                reads=prior_handles,
                writes=(
                    artifact("task_strategy_brief.md"),
                    artifact("workflow_selection_criteria.md"),
                ),
            )
            completed.append(phase_1)
            prior_handles = prior_handles + phase_1.handles
            candidate_result = TaskToCandidateWorkflowSet(
                CandidateParams(
                    task_title=params.task_title,
                    sponsor_role=params.sponsor_role,
                    desired_outcome=params.desired_outcome,
                    constraints=params.constraints,
                    evidence_expectations=params.evidence_expectations,
                ),
                request=request
                + "\n\nParent framing:\n"
                + json.dumps(
                    {
                        "evidence": phase_1.evidence.model_dump(mode="json"),
                        "artifacts": [str(handle.path) for handle in phase_1.handles],
                    }
                ),
            )
            context["candidate_workflow_set"] = candidate_result.model_dump(mode="json")
            prior_handles = prior_handles + tuple(candidate_result.artifacts.values())
            select_strategy_checkpoint = len(completed)
            select_strategy_reads = prior_handles
            select_strategy_context = dict(context)
            while True:
                try:
                    phase_2 = run_phase(
                        phase="select_strategy",
                        returns=StrategySelectionPayload,
                        replan_target="frame_task",
                        producer=_producer,
                        producer_prompt="prompts/select_producer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(artifact("strategy_decision.md"),),
                    )
                    selection = StrategySelectionPayload.model_validate(phase_2.value)
                    child_details = context["candidate_workflow_set"]["phases"][-1][
                        "details"
                    ]
                    child_recommendations = set(
                        child_details["recommended_candidate_workflows"]
                    )
                    if not set(selection.recommended_workflows) <= child_recommendations:
                        raise ValueError(
                            "strategy recommendations must come from the candidate set"
                        )
                    completed.append(phase_2)
                    prior_handles = prior_handles + phase_2.handles
                    phase_3 = run_phase(
                        phase="package_strategy",
                        returns=StrategyPackagePayload,
                        replan_target="select_strategy",
                        producer=_producer,
                        producer_prompt="prompts/package_producer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(
                            artifact("workflow_strategy_package.md"),
                            artifact("strategy_summary.json"),
                            artifact("strategy_next_action.md"),
                        ),
                    )
                    package = StrategyPackagePayload.model_validate(phase_3.value)
                    if package.selected_strategy != selection.selected_strategy:
                        raise ValueError("strategy package changed the selected route")
                    if package.recommended_workflows != selection.recommended_workflows:
                        raise ValueError(
                            "strategy package changed the recommended workflows"
                        )
                    completed.append(phase_3)
                    prior_handles = prior_handles + phase_3.handles
                    break
                except ReplanRequired as change:
                    if change.target != "select_strategy":
                        raise
                    del completed[select_strategy_checkpoint:]
                    prior_handles = select_strategy_reads
                    context = {
                        **select_strategy_context,
                        "replan_feedback": change.evidence.model_dump(mode="json"),
                        "replan_artifacts": [
                            str(handle.path) for handle in change.handles
                        ],
                    }
            break
        except ReplanRequired as change:
            if change.target != "frame_task":
                raise
            del completed[frame_task_checkpoint:]
            prior_handles = frame_task_reads
            context = {
                **frame_task_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    return finish("task_to_workflow_strategy", completed)


@workflow(name="task_to_workflow_strategy", version="3")
def TaskToWorkflowStrategy(params: Params, request: str = "") -> LabWorkflowResult:
    """Execute the SOP within one durable provider-turn budget."""
    with provider_budget(max_turns=params.max_provider_turns):
        return _run_task_to_workflow_strategy(params, request)


workflow_callable = TaskToWorkflowStrategy

__all__ = ["TaskToWorkflowStrategy", "workflow_callable"]
