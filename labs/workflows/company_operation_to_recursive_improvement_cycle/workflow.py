"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

from botpipe import Provider, workflow
from labs.workflows._shared import (
    LabWorkflowResult,
    ReplanRequired,
    artifact,
    finish,
    observe_catalog,
    observe_run_history,
    read_publication_json,
    run_phase,
)
from labs.workflows.publication_validation import validate_company_publication

from .contracts import (
    CompanyOperationFramingPayload,
    RecursiveImprovementAnalysisPayload,
    RecursiveImprovementCyclePayload,
)
from .params import Params


@workflow(name="company_operation_to_recursive_improvement_cycle", version="2")
def CompanyOperationToRecursiveImprovementCycle(
    params: Params, request: str = ""
) -> LabWorkflowResult:
    """Execute the company operation to recursive improvement cycle evidence workflow."""
    _producer = Provider()
    context = {"request": request, "parameters": params.model_dump(mode="json")}
    context["workflow_catalog"] = observe_catalog()
    context["observed_company_runs"] = observe_run_history(
        statuses=params.statuses,
        limit=params.max_tasks * params.max_runs_per_workflow,
        task_ids=params.focus_tasks,
    )
    completed = []
    prior_handles = ()
    frame_company_operation_checkpoint = len(completed)
    frame_company_operation_reads = prior_handles
    frame_company_operation_context = dict(context)
    while True:
        try:
            phase_1 = run_phase(
                phase="frame_company_operation",
                returns=CompanyOperationFramingPayload,
                replan_target="frame_company_operation",
                producer=_producer,
                producer_prompt="prompts/frame_producer.md",
                input=context,
                reads=prior_handles,
                writes=(
                    artifact("company_operation_brief.md"),
                    artifact("recursive_improvement_criteria.md"),
                ),
            )
            completed.append(phase_1)
            prior_handles = prior_handles + phase_1.handles
            analyze_recursive_improvement_pressures_checkpoint = len(completed)
            analyze_recursive_improvement_pressures_reads = prior_handles
            analyze_recursive_improvement_pressures_context = dict(context)
            while True:
                try:
                    phase_2 = run_phase(
                        phase="analyze_recursive_improvement_pressures",
                        returns=RecursiveImprovementAnalysisPayload,
                        replan_target="frame_company_operation",
                        producer=_producer,
                        producer_prompt="prompts/analyze_producer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(
                            artifact("company_pressure_map.md"),
                            artifact("recursive_improvement_priority_matrix.md"),
                            artifact("recursive_improvement_candidates.json"),
                        ),
                    )
                    completed.append(phase_2)
                    prior_handles = prior_handles + phase_2.handles
                    phase_3 = run_phase(
                        phase="package_recursive_improvement_cycle",
                        returns=RecursiveImprovementCyclePayload,
                        replan_target="analyze_recursive_improvement_pressures",
                        producer=_producer,
                        producer_prompt="prompts/package_producer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(
                            artifact("recursive_improvement_cycle.md"),
                            artifact("recursive_improvement_summary.json"),
                            artifact("recursive_improvement_next_actions.md"),
                        ),
                    )
                    completed.append(phase_3)
                    prior_handles = prior_handles + phase_3.handles
                    break
                except ReplanRequired as change:
                    if change.target != "analyze_recursive_improvement_pressures":
                        raise
                    del completed[analyze_recursive_improvement_pressures_checkpoint:]
                    prior_handles = analyze_recursive_improvement_pressures_reads
                    context = {
                        **analyze_recursive_improvement_pressures_context,
                        "replan_feedback": change.evidence.model_dump(mode="json"),
                        "replan_artifacts": [
                            str(handle.path) for handle in change.handles
                        ],
                    }
            break
        except ReplanRequired as change:
            if change.target != "frame_company_operation":
                raise
            del completed[frame_company_operation_checkpoint:]
            prior_handles = frame_company_operation_reads
            context = {
                **frame_company_operation_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    publication = read_publication_json(
        tuple(handle for phase in completed for handle in phase.handles),
        ("recursive_improvement_candidates", "recursive_improvement_summary"),
    )
    catalog_names = [
        str(item["name"]) for item in context["workflow_catalog"] if item.get("name")
    ]
    observed_task_ids = list(
        dict.fromkeys(
            str(item["run"]["task_id"])
            for item in context["observed_company_runs"]
            if isinstance(item.get("run"), dict) and item["run"].get("task_id")
        )
    )
    validate_company_publication(
        publication["recursive_improvement_summary"],
        analysis=completed[-2].evidence.details,
        package=completed[-1].evidence.details,
        candidates=publication["recursive_improvement_candidates"],
        allowed_workflows=catalog_names,
        expected_focus_workflows=params.focus_workflows or None,
        expected_focus_task_ids=params.focus_tasks or observed_task_ids,
    )
    return finish("company_operation_to_recursive_improvement_cycle", completed)


workflow_callable = CompanyOperationToRecursiveImprovementCycle

__all__ = ["CompanyOperationToRecursiveImprovementCycle", "workflow_callable"]
