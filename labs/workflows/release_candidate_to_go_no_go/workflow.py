"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

from dataclasses import replace

from botpipe import Provider, provider_budget, workflow
from labs.workflows._evidence import (
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
from labs.workflows.publication_validation import validate_release_publication

from .contracts import (
    ReleaseAssessmentPayload,
    ReleaseDecisionPackagePayload,
    ReleaseEvidencePayload,
    ReleaseFramingPayload,
)
from .params import Params


def _run_release_candidate_to_go_no_go(
    params: Params, request: str
) -> LabWorkflowResult:
    """Execute the release candidate to go no go evidence workflow."""
    _producer = Provider()
    _reviewer = _producer.with_config(session=None)
    evidence_intake = capture_declared_evidence(params.evidence_paths)
    verify_evidence_intake(evidence_intake)
    context = {
        "request": request,
        "parameters": params.model_dump(mode="json"),
        "evidence_intake": evidence_intake_context(evidence_intake),
    }
    completed = []
    prior_handles = evidence_intake.handles
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
                producer_prompt="prompts/frame_producer.md",
                input=context,
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
                reviewer=_reviewer,
                producer_prompt="prompts/evidence_producer.md",
                reviewer_prompt="prompts/evidence_reviewer.md",
                input=context,
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
                        reviewer=_reviewer,
                        producer_prompt="prompts/assessment_producer.md",
                        reviewer_prompt="prompts/assessment_reviewer.md",
                        input=context,
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
                        producer_prompt="prompts/package_producer.md",
                        input=context,
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
    completed[0] = replace(
        completed[0], handles=(*evidence_intake.handles, *completed[0].handles)
    )
    return finish("release_candidate_to_go_no_go", completed)


@workflow(name="release_candidate_to_go_no_go", version="3")
def ReleaseCandidateToGoNoGo(
    params: Params, request: str = ""
) -> LabWorkflowResult:
    """Execute the SOP within one durable provider-turn budget."""
    with provider_budget(max_turns=params.max_provider_turns):
        return _run_release_candidate_to_go_no_go(params, request)


workflow_callable = ReleaseCandidateToGoNoGo

__all__ = ["ReleaseCandidateToGoNoGo", "workflow_callable"]
