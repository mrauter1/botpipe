"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

from dataclasses import replace

from botpipe import Provider, provider_budget, workflow
from labs.workflows._evidence import (
    EvidenceIntake,
    capture_declared_evidence,
    evidence_intake_context,
    verify_evidence_intake,
)
from labs.workflows._shared import (
    LabWorkflowResult,
    ReplanRequired,
    artifact,
    finish,
    read_publication_json,
    run_phase,
)
from labs.workflows.publication_validation import validate_investigation_summary

from .contracts import (
    InvestigationEvidencePackPayload,
    InvestigationFramingPayload,
)
from .params import Params


def _run_investigation_request_to_evidence_pack(
    params: Params,
    request: str,
    captured_evidence: EvidenceIntake | None = None,
) -> LabWorkflowResult:
    """Execute the investigation request to evidence pack evidence workflow."""
    _producer = Provider()
    _reviewer = _producer.with_config(session=None)
    evidence_intake = captured_evidence or capture_declared_evidence(
        params.evidence_paths
    )
    if tuple(record.declared_path for record in evidence_intake.records) != tuple(
        params.evidence_paths
    ):
        raise ValueError("captured evidence does not match declared evidence_paths")
    verify_evidence_intake(evidence_intake)
    context = {
        "request": request,
        "parameters": params.model_dump(mode="json"),
        "evidence_intake": evidence_intake_context(evidence_intake),
    }
    completed = []
    prior_handles = evidence_intake.handles
    frame_investigation_checkpoint = len(completed)
    frame_investigation_reads = prior_handles
    frame_investigation_context = dict(context)
    while True:
        try:
            phase_1 = run_phase(
                phase="frame_investigation",
                returns=InvestigationFramingPayload,
                replan_target="frame_investigation",
                producer=_producer,
                producer_prompt="prompts/frame_producer.md",
                input=context,
                reads=prior_handles,
                writes=(
                    artifact("investigation_scope_brief.md"),
                    artifact("evidence_intake_plan.md"),
                ),
            )
            completed.append(phase_1)
            prior_handles = prior_handles + phase_1.handles
            phase_2 = run_phase(
                phase="assemble_evidence_pack",
                returns=InvestigationEvidencePackPayload,
                replan_target="frame_investigation",
                producer=_producer,
                reviewer=_reviewer,
                producer_prompt="prompts/evidence_producer.md",
                reviewer_prompt="prompts/evidence_reviewer.md",
                input=context,
                reads=prior_handles,
                writes=(
                    artifact("evidence_pack.md"),
                    artifact("source_register.json"),
                    artifact("evidence_gaps.md"),
                    artifact("investigation_summary.json"),
                ),
            )
            completed.append(phase_2)
            prior_handles = prior_handles + phase_2.handles
            break
        except ReplanRequired as change:
            if change.target != "frame_investigation":
                raise
            del completed[frame_investigation_checkpoint:]
            prior_handles = frame_investigation_reads
            context = {
                **frame_investigation_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    publication = read_publication_json(
        tuple(handle for phase in completed for handle in phase.handles),
        ("investigation_summary",),
    )
    validate_investigation_summary(
        publication["investigation_summary"],
        expected_kind=params.investigation_kind,
    )
    completed[0] = replace(
        completed[0], handles=(*evidence_intake.handles, *completed[0].handles)
    )
    return finish("investigation_request_to_evidence_pack", completed)


@workflow(name="investigation_request_to_evidence_pack", version="3")
def InvestigationRequestToEvidencePack(
    params: Params,
    request: str = "",
    captured_evidence: EvidenceIntake | None = None,
) -> LabWorkflowResult:
    """Execute the SOP within one durable provider-turn budget."""
    with provider_budget(max_turns=params.max_provider_turns):
        return _run_investigation_request_to_evidence_pack(
            params, request, captured_evidence
        )


workflow_callable = InvestigationRequestToEvidencePack

__all__ = ["InvestigationRequestToEvidencePack", "workflow_callable"]
