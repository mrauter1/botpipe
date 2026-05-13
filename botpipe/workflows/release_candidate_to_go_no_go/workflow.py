"""Release go/no-go workflow package."""

from __future__ import annotations

from pydantic import BaseModel, Field

from botpipe.stdlib import (
    read_json_object,
    require_non_empty_string,
)
from botpipe.stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from botpipe import Event, FAIL, FINISH, Outcome, Prompt, Session, Workflow, produce_verify_step, python_step
from botpipe.core import Artifact

from .contracts import (
    ASSEMBLE_EVIDENCE_ROUTE_CONTRACTS,
    ASSESS_GO_NO_GO_ROUTE_CONTRACTS,
    FRAME_RELEASE_ROUTE_CONTRACTS,
    PREPARE_DECISION_PACKAGE_ROUTE_CONTRACTS,
    ReleaseAssessmentPayload,
    ReleaseDecisionPackagePayload,
    ReleaseEvidencePayload,
    ReleaseFramingPayload,
)


def _after_frame_release(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    ctx.state.framing_status = outcome.tag
    return None


def _after_assemble_evidence_pack(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    ctx.state.evidence_status = outcome.tag
    return None


def _after_assess_go_no_go(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    recommended_decision = outcome.payload.get("recommended_decision")
    ctx.state.assessment_status = outcome.tag
    if isinstance(recommended_decision, str):
        ctx.state.recommended_decision = recommended_decision
    return None


def _after_prepare_decision_package(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    decision = outcome.payload.get("decision")
    ctx.state.packaging_status = outcome.tag
    if isinstance(decision, str):
        ctx.state.recommended_decision = decision
    return None


class ReleaseCandidateToGoNoGo(Workflow):
    """Turn a release candidate into a durable go/no-go decision package."""

    name = "release_candidate_to_go_no_go"

    class State(BaseModel):
        release_name: str = ""
        target_date: str | None = None
        deployment_environment: str = "production"
        release_owner: str | None = None
        evidence_paths: list[str] = Field(default_factory=list)
        framing_status: str | None = None
        evidence_status: str | None = None
        assessment_status: str | None = None
        packaging_status: str | None = None
        recommended_decision: str | None = None
        published: bool = False

    frame_session = Session()
    evidence_session = Session()
    assessment_session = Session()
    package_session = Session()

    request = Artifact("{{ run.folder }}/request.md")
    framework_architecture_doc = Artifact("{{ root }}/docs/architecture.md")
    framework_authoring_doc = Artifact("{{ root }}/docs/authoring.md")
    workflow_instructions = Artifact("{{ root }}/Workflow_Instructions.md")
    decision_package_checklist = Artifact("{{ package.folder }}/assets/release_decision_package_checklist.md")

    invocation_contract = Artifact("{{ workflow.folder }}/invocation_contract.json")
    release_scope_brief = Artifact("{{ workflow.folder }}/release_scope_brief.md")
    decision_criteria = Artifact("{{ workflow.folder }}/decision_criteria.md")
    evidence_intake_register = Artifact("{{ workflow.folder }}/evidence_intake_register.md")
    release_inventory = Artifact("{{ workflow.folder }}/release_inventory.md")
    test_evidence_pack = Artifact("{{ workflow.folder }}/test_evidence_pack.md")
    operational_readiness = Artifact("{{ workflow.folder }}/operational_readiness.md")
    rollback_readiness = Artifact("{{ workflow.folder }}/rollback_readiness.md")
    blocking_issues = Artifact("{{ workflow.folder }}/blocking_issues.md")
    go_no_go_assessment = Artifact("{{ workflow.folder }}/go_no_go_assessment.md")
    risk_register = Artifact("{{ workflow.folder }}/risk_register.md")
    decision_summary = Artifact("{{ workflow.folder }}/decision_summary.json")
    release_decision_package = Artifact("{{ workflow.folder }}/release_decision_package.md")
    release_communications_draft = Artifact("{{ workflow.folder }}/release_communications_draft.md")
    decision_receipt = Artifact("{{ workflow.folder }}/decision_receipt.json")

    frame_release = produce_verify_step(
        producer_prompt=Prompt.file("prompts/frame_producer.md"),
        verifier_prompt=Prompt.file("prompts/frame_verifier.md"),
        session=frame_session,
        requires=[
            request,
            invocation_contract,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        producer_writes=[release_scope_brief, decision_criteria, evidence_intake_register],
        control_schema=ReleaseFramingPayload,
        routes=FRAME_RELEASE_ROUTE_CONTRACTS,
        after_verifier=_after_frame_release,
    )
    assemble_evidence_pack = produce_verify_step(
        producer_prompt=Prompt.file("prompts/evidence_producer.md"),
        verifier_prompt=Prompt.file("prompts/evidence_verifier.md"),
        session=evidence_session,
        requires=[
            request,
            invocation_contract,
            release_scope_brief,
            decision_criteria,
            evidence_intake_register,
        ],
        producer_writes=[release_inventory, test_evidence_pack, operational_readiness, rollback_readiness, blocking_issues],
        control_schema=ReleaseEvidencePayload,
        routes=ASSEMBLE_EVIDENCE_ROUTE_CONTRACTS,
        after_verifier=_after_assemble_evidence_pack,
    )
    assess_go_no_go = produce_verify_step(
        producer_prompt=Prompt.file("prompts/assessment_producer.md"),
        verifier_prompt=Prompt.file("prompts/assessment_verifier.md"),
        session=assessment_session,
        requires=[
            release_scope_brief,
            decision_criteria,
            evidence_intake_register,
            release_inventory,
            test_evidence_pack,
            operational_readiness,
            rollback_readiness,
            blocking_issues,
        ],
        producer_writes=[go_no_go_assessment, risk_register, decision_summary],
        control_schema=ReleaseAssessmentPayload,
        routes=ASSESS_GO_NO_GO_ROUTE_CONTRACTS,
        after_verifier=_after_assess_go_no_go,
    )
    prepare_decision_package = produce_verify_step(
        producer_prompt=Prompt.file("prompts/package_producer.md"),
        verifier_prompt=Prompt.file("prompts/package_verifier.md"),
        session=package_session,
        requires=[
            request,
            invocation_contract,
            decision_package_checklist,
            release_scope_brief,
            decision_criteria,
            release_inventory,
            test_evidence_pack,
            operational_readiness,
            rollback_readiness,
            blocking_issues,
            go_no_go_assessment,
            risk_register,
            decision_summary,
        ],
        producer_writes=[release_decision_package, release_communications_draft],
        control_schema=ReleaseDecisionPackagePayload,
        routes=PREPARE_DECISION_PACKAGE_ROUTE_CONTRACTS,
        after_verifier=_after_prepare_decision_package,
    )

    @python_step(
        name="bootstrap",
        requires=[request],
        writes=[invocation_contract],
        routes={"inputs_prepared": "frame_release"},
    )
    def bootstrap(ctx):
        params = ctx.params
        next_state = ctx.state.model_copy(
            update={
                "release_name": params.release_name,
                "target_date": params.target_date,
                "deployment_environment": params.deployment_environment,
                "release_owner": params.release_owner,
                "evidence_paths": list(params.evidence_paths),
                "framing_status": None,
                "evidence_status": None,
                "assessment_status": None,
                "packaging_status": None,
                "recommended_decision": None,
                "published": False,
            }
        )
        open_workflow_sessions(ctx, "frame_session", "evidence_session", "assessment_session", "package_session")
        write_invocation_contract(
            ctx,
            {
                "release_name": next_state.release_name,
                "target_date": next_state.target_date,
                "deployment_environment": next_state.deployment_environment,
                "release_owner": next_state.release_owner,
                "evidence_paths": next_state.evidence_paths,
            },
        )
        ctx.state = next_state
        return "inputs_prepared"

    @python_step(
        name="publish_decision",
        requires=[decision_summary, release_decision_package, release_communications_draft],
        writes=[decision_receipt],
        routes={"decision_published": FINISH},
    )
    def publish_decision(ctx):
        summary_path = ctx.workflow_folder / "decision_summary.json"
        decision_package_path = ctx.workflow_folder / "release_decision_package.md"
        communications_path = ctx.workflow_folder / "release_communications_draft.md"
        for artifact_path in (summary_path, decision_package_path, communications_path):
            if not artifact_path.exists():
                raise FileNotFoundError(f"missing required publication artifact at {artifact_path}")

        summary = read_json_object(summary_path)
        recommended_decision = require_non_empty_string(
            summary.get("recommended_decision"),
            error_message="decision_summary.json must define a non-empty recommended_decision",
            coerce=False,
        )

        write_publication_receipt(
            ctx,
            "decision_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "release_name": ctx.state.release_name,
                "target_date": ctx.state.target_date,
                "deployment_environment": ctx.state.deployment_environment,
                "release_owner": ctx.state.release_owner,
                "recommended_decision": recommended_decision,
                "blocking_issue_count": summary.get("blocking_issue_count"),
                "decision_summary": str(summary_path),
                "decision_package": str(decision_package_path),
                "communications_draft": str(communications_path),
                "published": True,
            },
        )
        ctx.state.published = True
        ctx.state.recommended_decision = recommended_decision
        return "decision_published"

    entry = bootstrap



__all__ = ["ReleaseCandidateToGoNoGo"]
