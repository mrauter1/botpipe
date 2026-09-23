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
from labs.workflows.publication_validation import validate_investigation_summary

from .contracts import (
    InvestigationEvidencePackPayload,
    InvestigationFramingPayload,
)
from .params import Params


@workflow(name="investigation_request_to_evidence_pack", version="2")
def InvestigationRequestToEvidencePack(
    params: Params, request: str = ""
) -> LabWorkflowResult:
    """Execute the investigation request to evidence pack evidence workflow."""
    _producer = Provider()
    _verifier = _producer.with_config(session=None)
    context = {"request": request, "parameters": params.model_dump(mode="json")}
    completed = []
    prior_handles = ()
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
                verifier=_verifier,
                producer_prompt="prompts/evidence_producer.md",
                verifier_prompt="prompts/evidence_verifier.md",
                input={
                    **context,
                    "prior_phases": [
                        item.evidence.model_dump(mode="json") for item in completed
                    ],
                },
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
    return finish("investigation_request_to_evidence_pack", completed)


workflow_callable = InvestigationRequestToEvidencePack

__all__ = ["InvestigationRequestToEvidencePack", "workflow_callable"]
