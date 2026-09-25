"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

from botpipe import Provider, workflow
from labs.workflows._shared import (
    LabWorkflowResult,
    ReplanRequired,
    artifact,
    finish,
    read_publication_json,
    run_phase,
)
from labs.workflows.publication_validation import validate_incident_publication

from .contracts import (
    IncidentEvidencePayload,
    IncidentFramingPayload,
    IncidentHardeningProgramPayload,
    IncidentHypothesisPayload,
)
from .params import Params


@workflow(name="incident_to_hardening_program", version="2")
def IncidentToHardeningProgram(params: Params, request: str = "") -> LabWorkflowResult:
    """Execute the incident to hardening program evidence workflow."""
    _producer = Provider()
    _reviewer = _producer.with_config(session=None)
    context = {"request": request, "parameters": params.model_dump(mode="json")}
    completed = []
    prior_handles = ()
    frame_incident_checkpoint = len(completed)
    frame_incident_reads = prior_handles
    frame_incident_context = dict(context)
    while True:
        try:
            phase_1 = run_phase(
                phase="frame_incident",
                returns=IncidentFramingPayload,
                replan_target="frame_incident",
                producer=_producer,
                producer_prompt="prompts/frame_producer.md",
                input=context,
                reads=prior_handles,
                writes=(
                    artifact("incident_scope_brief.md"),
                    artifact("response_objectives.md"),
                    artifact("evidence_intake_register.md"),
                ),
            )
            completed.append(phase_1)
            prior_handles = prior_handles + phase_1.handles
            phase_2 = run_phase(
                phase="assemble_evidence_pack",
                returns=IncidentEvidencePayload,
                replan_target="frame_incident",
                producer=_producer,
                reviewer=_reviewer,
                producer_prompt="prompts/evidence_producer.md",
                reviewer_prompt="prompts/evidence_reviewer.md",
                input=context,
                reads=prior_handles,
                writes=(
                    artifact("incident_timeline.md"),
                    artifact("affected_surface.md"),
                    artifact("blast_radius.md"),
                    artifact("observability_gaps.md"),
                    artifact("evidence_gap_register.md"),
                ),
            )
            completed.append(phase_2)
            prior_handles = prior_handles + phase_2.handles
            rank_cause_hypotheses_checkpoint = len(completed)
            rank_cause_hypotheses_reads = prior_handles
            rank_cause_hypotheses_context = dict(context)
            while True:
                try:
                    phase_3 = run_phase(
                        phase="rank_cause_hypotheses",
                        returns=IncidentHypothesisPayload,
                        replan_target="frame_incident",
                        producer=_producer,
                        producer_prompt="prompts/analysis_producer.md",
                        reviewer=_reviewer,
                        reviewer_prompt="prompts/analysis_reviewer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(
                            artifact("cause_hypothesis_ranking.md"),
                            artifact("immediate_mitigation_plan.md"),
                            artifact("validation_plan.md"),
                            artifact("incident_summary.json"),
                        ),
                    )
                    completed.append(phase_3)
                    prior_handles = prior_handles + phase_3.handles
                    phase_4 = run_phase(
                        phase="prepare_hardening_program",
                        returns=IncidentHardeningProgramPayload,
                        replan_target="rank_cause_hypotheses",
                        producer=_producer,
                        producer_prompt="prompts/program_producer.md",
                        reviewer=_reviewer,
                        reviewer_prompt="prompts/program_reviewer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(
                            artifact("hardening_program.md"),
                            artifact("hardening_backlog.json"),
                            artifact("follow_up_owners.md"),
                            artifact("stakeholder_communications_draft.md"),
                            artifact("incident_resolution_package.md"),
                        ),
                    )
                    completed.append(phase_4)
                    prior_handles = prior_handles + phase_4.handles
                    break
                except ReplanRequired as change:
                    if change.target != "rank_cause_hypotheses":
                        raise
                    del completed[rank_cause_hypotheses_checkpoint:]
                    prior_handles = rank_cause_hypotheses_reads
                    context = {
                        **rank_cause_hypotheses_context,
                        "replan_feedback": change.evidence.model_dump(mode="json"),
                        "replan_artifacts": [
                            str(handle.path) for handle in change.handles
                        ],
                    }
            break
        except ReplanRequired as change:
            if change.target != "frame_incident":
                raise
            del completed[frame_incident_checkpoint:]
            prior_handles = frame_incident_reads
            context = {
                **frame_incident_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    publication = read_publication_json(
        tuple(handle for phase in completed for handle in phase.handles),
        ("incident_summary",),
    )
    validate_incident_publication(publication["incident_summary"])
    return finish("incident_to_hardening_program", completed)


workflow_callable = IncidentToHardeningProgram

__all__ = ["IncidentToHardeningProgram", "workflow_callable"]
