"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

from botpipe import Session, workflow
from labs.workflows._shared import (
    LabWorkflowResult,
    ReplanRequired,
    artifact,
    finish,
    observe_run_history,
    observe_workflow,
    run_phase,
)

from .contracts import (
    DiagnosticScopePayload,
    FailureModeMapPayload,
    ImprovementPressurePayload,
)
from .params import Params


@workflow(name="workflow_run_history_to_failure_modes", version="2")
def WorkflowRunHistoryToFailureModes(
    params: Params, request: str = ""
) -> LabWorkflowResult:
    """Execute the workflow run history to failure modes evidence workflow."""
    _producer = Session(key="producer")
    _verifier = Session(key="verifier")
    context = {"request": request, "parameters": params.model_dump(mode="json")}
    context["selected_workflow_contract"] = observe_workflow(params.selected_workflow)
    context["observed_run_history"] = observe_run_history(
        params.selected_workflow, statuses=params.statuses, limit=params.max_runs
    )
    completed = []
    prior_handles = ()
    frame_diagnostic_scope_checkpoint = len(completed)
    frame_diagnostic_scope_reads = prior_handles
    frame_diagnostic_scope_context = dict(context)
    while True:
        try:
            phase_1 = run_phase(
                phase="frame_diagnostic_scope",
                returns=DiagnosticScopePayload,
                replan_target="frame_diagnostic_scope",
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
                    artifact("diagnostic_scope_brief.md"),
                    artifact("run_history_scope.md"),
                ),
            )
            completed.append(phase_1)
            prior_handles = prior_handles + phase_1.handles
            map_failure_modes_checkpoint = len(completed)
            map_failure_modes_reads = prior_handles
            map_failure_modes_context = dict(context)
            while True:
                try:
                    phase_2 = run_phase(
                        phase="map_failure_modes",
                        returns=FailureModeMapPayload,
                        replan_target="frame_diagnostic_scope",
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
                            artifact("failure_mode_map.md"),
                            artifact("failure_mode_manifest.json"),
                            artifact("recurring_weak_points.md"),
                        ),
                    )
                    completed.append(phase_2)
                    prior_handles = prior_handles + phase_2.handles
                    phase_3 = run_phase(
                        phase="package_improvement_pressure",
                        returns=ImprovementPressurePayload,
                        replan_target="map_failure_modes",
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
                            artifact("improvement_opportunities.json"),
                            artifact("improvement_opportunities_summary.json"),
                            artifact("diagnostic_next_actions.md"),
                        ),
                    )
                    completed.append(phase_3)
                    prior_handles = prior_handles + phase_3.handles
                    break
                except ReplanRequired as change:
                    if change.target != "map_failure_modes":
                        raise
                    del completed[map_failure_modes_checkpoint:]
                    prior_handles = map_failure_modes_reads
                    context = {
                        **map_failure_modes_context,
                        "replan_feedback": change.evidence.model_dump(mode="json"),
                        "replan_artifacts": [
                            str(handle.path) for handle in change.handles
                        ],
                    }
            break
        except ReplanRequired as change:
            if change.target != "frame_diagnostic_scope":
                raise
            del completed[frame_diagnostic_scope_checkpoint:]
            prior_handles = frame_diagnostic_scope_reads
            context = {
                **frame_diagnostic_scope_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    return finish("workflow_run_history_to_failure_modes", completed)


workflow_callable = WorkflowRunHistoryToFailureModes

__all__ = ["WorkflowRunHistoryToFailureModes", "workflow_callable"]
