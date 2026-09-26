"""Durable Python workflow with domain review and replanning."""

from __future__ import annotations

import json
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
from labs.workflows.investigation_request_to_evidence_pack import (
    InvestigationRequestToEvidencePack,
)
from labs.workflows.investigation_request_to_evidence_pack import (
    Params as InvestigationParams,
)
from labs.workflows.publication_validation import (
    validate_security_child_result,
    validate_security_publication,
)

from .contracts import (
    SecurityAssessmentPayload,
    SecurityClosurePackagePayload,
    VerifiedRemediationPayload,
)
from .params import Params


def _run_security_finding_to_verified_remediation(
    params: Params, request: str
) -> LabWorkflowResult:
    """Execute the security finding to verified remediation evidence workflow."""
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
    compose_evidence_pack_checkpoint = len(completed)
    compose_evidence_pack_reads = prior_handles
    compose_evidence_pack_context = dict(context)
    while True:
        try:
            evidence_pack = InvestigationRequestToEvidencePack(
                InvestigationParams(
                    investigation_title=params.finding_title,
                    investigation_kind="security_remediation",
                    sponsor_role=params.sponsor_role,
                    evidence_paths=params.evidence_paths,
                    source_constraints=params.deployment_constraints,
                ),
                request=request
                + "\n\nReplanning context:\n"
                + json.dumps(
                    {
                        "feedback": context.get("replan_feedback"),
                        "artifacts": context.get("replan_artifacts", []),
                    }
                ),
                captured_evidence=evidence_intake,
            )
            validate_security_child_result(evidence_pack.model_dump(mode="json"))
            context["security_evidence_pack"] = evidence_pack.model_dump(mode="json")
            intake_names = {handle.name for handle in evidence_intake.handles}
            child_handles = tuple(
                evidence_pack.artifacts[name]
                for name in evidence_pack.artifact_names
                if name not in intake_names
            )
            prior_handles = prior_handles + child_handles
            assess_security_finding_checkpoint = len(completed)
            assess_security_finding_reads = prior_handles
            assess_security_finding_context = dict(context)
            while True:
                try:
                    phase_1 = run_phase(
                        phase="assess_security_finding",
                        returns=SecurityAssessmentPayload,
                        replan_target="compose_evidence_pack",
                        producer=_producer,
                        reviewer=_reviewer,
                        producer_prompt="prompts/assessment_producer.md",
                        reviewer_prompt="prompts/assessment_reviewer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(
                            artifact("security_assessment.md"),
                            artifact("threat_scenario.md"),
                            artifact("remediation_acceptance_criteria.md"),
                        ),
                    )
                    completed.append(phase_1)
                    prior_handles = prior_handles + phase_1.handles
                    plan_verified_remediation_checkpoint = len(completed)
                    plan_verified_remediation_reads = prior_handles
                    plan_verified_remediation_context = dict(context)
                    while True:
                        try:
                            phase_2 = run_phase(
                                phase="plan_verified_remediation",
                                returns=VerifiedRemediationPayload,
                                replan_target="assess_security_finding",
                                producer=_producer,
                                reviewer=_reviewer,
                                producer_prompt="prompts/remediation_producer.md",
                                reviewer_prompt="prompts/remediation_reviewer.md",
                                input=context,
                                reads=prior_handles,
                                writes=(
                                    artifact("remediation_plan.md"),
                                    artifact("verification_evidence.md"),
                                    artifact("residual_risk.json"),
                                ),
                            )
                            completed.append(phase_2)
                            prior_handles = prior_handles + phase_2.handles
                            phase_3 = run_phase(
                                phase="prepare_closure_package",
                                returns=SecurityClosurePackagePayload,
                                replan_target="plan_verified_remediation",
                                producer=_producer,
                                producer_prompt="prompts/closure_producer.md",
                                input=context,
                                reads=prior_handles,
                                writes=(
                                    artifact("security_remediation_package.md"),
                                    artifact("security_remediation_summary.json"),
                                    artifact("security_next_action.md"),
                                ),
                            )
                            completed.append(phase_3)
                            prior_handles = prior_handles + phase_3.handles
                            break
                        except ReplanRequired as change:
                            if change.target != "plan_verified_remediation":
                                raise
                            del completed[plan_verified_remediation_checkpoint:]
                            prior_handles = plan_verified_remediation_reads
                            context = {
                                **plan_verified_remediation_context,
                                "replan_feedback": change.evidence.model_dump(
                                    mode="json"
                                ),
                                "replan_artifacts": [
                                    str(handle.path) for handle in change.handles
                                ],
                            }
                    break
                except ReplanRequired as change:
                    if change.target != "assess_security_finding":
                        raise
                    del completed[assess_security_finding_checkpoint:]
                    prior_handles = assess_security_finding_reads
                    context = {
                        **assess_security_finding_context,
                        "replan_feedback": change.evidence.model_dump(mode="json"),
                        "replan_artifacts": [
                            str(handle.path) for handle in change.handles
                        ],
                    }
            break
        except ReplanRequired as change:
            if change.target != "compose_evidence_pack":
                raise
            del completed[compose_evidence_pack_checkpoint:]
            prior_handles = compose_evidence_pack_reads
            context = {
                **compose_evidence_pack_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    publication = read_publication_json(
        (
            *tuple(
                evidence_pack.artifacts[name]
                for name in evidence_pack.artifact_names
            ),
            *tuple(handle for phase in completed for handle in phase.handles),
        ),
        ("investigation_summary", "security_remediation_summary"),
    )
    validate_security_publication(
        publication["investigation_summary"],
        publication["security_remediation_summary"],
    )
    completed[0] = replace(
        completed[0], handles=(*evidence_intake.handles, *completed[0].handles)
    )
    return finish("security_finding_to_verified_remediation", completed)


@workflow(name="security_finding_to_verified_remediation", version="3")
def SecurityFindingToVerifiedRemediation(
    params: Params, request: str = ""
) -> LabWorkflowResult:
    """Execute the SOP within one durable provider-turn budget."""
    with provider_budget(max_turns=params.max_provider_turns):
        return _run_security_finding_to_verified_remediation(params, request)


workflow_callable = SecurityFindingToVerifiedRemediation

__all__ = ["SecurityFindingToVerifiedRemediation", "workflow_callable"]
