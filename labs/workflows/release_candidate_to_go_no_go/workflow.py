"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

from botpipe import Session, workflow
from labs.workflows._shared import (
    LabWorkflowResult,
    ReplanRequired,
    artifact,
    finish,
    read_publication_json,
    run_phase,
)
from labs.workflows.publication_validation import validate_release_publication

from .contracts import (
    ReleaseAssessmentPayload,
    ReleaseDecisionPackagePayload,
    ReleaseEvidencePayload,
    ReleaseFramingPayload,
)
from .params import Params


@workflow(name="release_candidate_to_go_no_go", version="2")
def ReleaseCandidateToGoNoGo(params: Params, request: str = "") -> LabWorkflowResult:
    """Execute the release candidate to go no go evidence workflow."""
    _producer = Session(key="producer")
    _verifier = Session(key="verifier")
    context = {"request": request, "parameters": params.model_dump(mode="json")}
    completed = []
    prior_handles = ()
    frame_release_checkpoint = len(completed)
    frame_release_reads = prior_handles
    frame_release_context = dict(context)
    while True:
        try:
            phase_1 = run_phase(
                phase="frame_release",
                returns=ReleaseFramingPayload,
                replan_target="frame_release",
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
                    artifact("release_scope_brief.md"),
                    artifact("decision_criteria.md"),
                    artifact("evidence_intake_register.md"),
                ),
            )
            completed.append(phase_1)
            prior_handles = prior_handles + phase_1.handles
            phase_2 = run_phase(
                phase="assemble_evidence_pack",
                returns=ReleaseEvidencePayload,
                replan_target="frame_release",
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
                    artifact("release_inventory.md"),
                    artifact("test_evidence_pack.md"),
                    artifact("operational_readiness.md"),
                    artifact("rollback_readiness.md"),
                    artifact("blocking_issues.md"),
                ),
            )
            completed.append(phase_2)
            prior_handles = prior_handles + phase_2.handles
            assess_go_no_go_checkpoint = len(completed)
            assess_go_no_go_reads = prior_handles
            assess_go_no_go_context = dict(context)
            while True:
                try:
                    phase_3 = run_phase(
                        phase="assess_go_no_go",
                        returns=ReleaseAssessmentPayload,
                        replan_target="frame_release",
                        producer=_producer,
                        verifier=_verifier,
                        producer_prompt="prompts/assessment_producer.md",
                        verifier_prompt="prompts/assessment_verifier.md",
                        input={
                            **context,
                            "prior_phases": [
                                item.evidence.model_dump(mode="json")
                                for item in completed
                            ],
                        },
                        reads=prior_handles,
                        writes=(
                            artifact("go_no_go_assessment.md"),
                            artifact("risk_register.json"),
                            artifact("decision_summary.json"),
                        ),
                    )
                    completed.append(phase_3)
                    prior_handles = prior_handles + phase_3.handles
                    phase_4 = run_phase(
                        phase="prepare_decision_package",
                        returns=ReleaseDecisionPackagePayload,
                        replan_target="assess_go_no_go",
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
                            artifact("release_decision_package.md"),
                            artifact("release_communications_draft.md"),
                        ),
                    )
                    completed.append(phase_4)
                    prior_handles = prior_handles + phase_4.handles
                    break
                except ReplanRequired as change:
                    if change.target != "assess_go_no_go":
                        raise
                    del completed[assess_go_no_go_checkpoint:]
                    prior_handles = assess_go_no_go_reads
                    context = {
                        **assess_go_no_go_context,
                        "replan_feedback": change.evidence.model_dump(mode="json"),
                        "replan_artifacts": [
                            str(handle.path) for handle in change.handles
                        ],
                    }
            break
        except ReplanRequired as change:
            if change.target != "frame_release":
                raise
            del completed[frame_release_checkpoint:]
            prior_handles = frame_release_reads
            context = {
                **frame_release_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    publication = read_publication_json(
        tuple(handle for phase in completed for handle in phase.handles),
        ("decision_summary",),
    )
    validate_release_publication(publication["decision_summary"])
    return finish("release_candidate_to_go_no_go", completed)


workflow_callable = ReleaseCandidateToGoNoGo

__all__ = ["ReleaseCandidateToGoNoGo", "workflow_callable"]
