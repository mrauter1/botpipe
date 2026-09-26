"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

from botpipe import Provider, provider_budget, workflow
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
from labs.workflows.publication_validation import validate_portfolio_publication

from .contracts import (
    PortfolioGovernanceFramingPayload,
    PortfolioOperatingModelPayload,
    PortfolioOperatingSystemPayload,
)
from .params import Params


def _run_workflow_portfolio_to_operating_system(
    params: Params, request: str
) -> LabWorkflowResult:
    """Execute the workflow portfolio to operating system evidence workflow."""
    _producer = Provider()
    context = {"request": request, "parameters": params.model_dump(mode="json")}
    context["workflow_catalog"] = observe_catalog()
    context["observed_run_health"] = observe_run_history(
        statuses=(),
        limit=params.max_runs_per_workflow * max(1, len(params.focus_workflows) or 1),
    )
    completed = []
    prior_handles = ()
    frame_portfolio_governance_checkpoint = len(completed)
    frame_portfolio_governance_reads = prior_handles
    frame_portfolio_governance_context = dict(context)
    while True:
        try:
            phase_1 = run_phase(
                phase="frame_portfolio_governance",
                returns=PortfolioGovernanceFramingPayload,
                replan_target="frame_portfolio_governance",
                producer=_producer,
                producer_prompt="prompts/frame_producer.md",
                input=context,
                reads=prior_handles,
                writes=(
                    artifact("portfolio_governance_brief.md"),
                    artifact("lifecycle_criteria.md"),
                ),
            )
            completed.append(phase_1)
            prior_handles = prior_handles + phase_1.handles
            analyze_portfolio_operating_model_checkpoint = len(completed)
            analyze_portfolio_operating_model_reads = prior_handles
            analyze_portfolio_operating_model_context = dict(context)
            while True:
                try:
                    phase_2 = run_phase(
                        phase="analyze_portfolio_operating_model",
                        returns=PortfolioOperatingModelPayload,
                        replan_target="frame_portfolio_governance",
                        producer=_producer,
                        producer_prompt="prompts/analyze_producer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(
                            artifact("portfolio_health_analysis.md"),
                            artifact("lifecycle_recommendations.json"),
                            artifact("portfolio_change_candidates.json"),
                        ),
                    )
                    completed.append(phase_2)
                    prior_handles = prior_handles + phase_2.handles
                    phase_3 = run_phase(
                        phase="package_portfolio_operating_system",
                        returns=PortfolioOperatingSystemPayload,
                        replan_target="analyze_portfolio_operating_model",
                        producer=_producer,
                        producer_prompt="prompts/package_producer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(
                            artifact("workflow_portfolio_operating_system.md"),
                            artifact("portfolio_operating_summary.json"),
                            artifact("portfolio_next_actions.md"),
                        ),
                    )
                    completed.append(phase_3)
                    prior_handles = prior_handles + phase_3.handles
                    break
                except ReplanRequired as change:
                    if change.target != "analyze_portfolio_operating_model":
                        raise
                    del completed[analyze_portfolio_operating_model_checkpoint:]
                    prior_handles = analyze_portfolio_operating_model_reads
                    context = {
                        **analyze_portfolio_operating_model_context,
                        "replan_feedback": change.evidence.model_dump(mode="json"),
                        "replan_artifacts": [
                            str(handle.path) for handle in change.handles
                        ],
                    }
            break
        except ReplanRequired as change:
            if change.target != "frame_portfolio_governance":
                raise
            del completed[frame_portfolio_governance_checkpoint:]
            prior_handles = frame_portfolio_governance_reads
            context = {
                **frame_portfolio_governance_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    publication = read_publication_json(
        tuple(handle for phase in completed for handle in phase.handles),
        ("portfolio_change_candidates", "portfolio_operating_summary"),
    )
    catalog_names = [
        str(item["name"]) for item in context["workflow_catalog"] if item.get("name")
    ]
    validate_portfolio_publication(
        publication["portfolio_operating_summary"],
        analysis=completed[-2].evidence.details,
        package=completed[-1].evidence.details,
        change_candidates=publication["portfolio_change_candidates"],
        allowed_workflows=catalog_names,
        expected_focus_workflows=params.focus_workflows or None,
    )
    return finish("workflow_portfolio_to_operating_system", completed)


@workflow(name="workflow_portfolio_to_operating_system", version="3")
def WorkflowPortfolioToOperatingSystem(
    params: Params, request: str = ""
) -> LabWorkflowResult:
    """Execute the SOP within one durable provider-turn budget."""
    with provider_budget(max_turns=params.max_provider_turns):
        return _run_workflow_portfolio_to_operating_system(params, request)


workflow_callable = WorkflowPortfolioToOperatingSystem

__all__ = ["WorkflowPortfolioToOperatingSystem", "workflow_callable"]
