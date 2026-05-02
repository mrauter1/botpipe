"""Security remediation workflow package."""

from __future__ import annotations

from pydantic import BaseModel, Field

from autoloop.stdlib import (
    adopt_child_artifacts,
    read_json_object,
    require_child_workflow_result,
    require_non_empty_string,
    require_non_negative_int,
    require_string_list,
    run_child_workflow,
)
from autoloop.stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from autoloop import Event, FINISH, Outcome, Prompt, Session, Workflow, produce_verify_step, python_step
from autoloop.core import Artifact

from .contracts import (
    ASSESS_SECURITY_FINDING_ROUTE_CONTRACTS,
    PLAN_VERIFIED_REMEDIATION_ROUTE_CONTRACTS,
    PREPARE_CLOSURE_PACKAGE_ROUTE_CONTRACTS,
    SecurityAssessmentPayload,
    SecurityClosurePackagePayload,
    VerifiedRemediationPayload,
)


def _after_assess_security_finding(ctx, outcome: Outcome):
    preferred_option = outcome.payload.get("preferred_remediation_option")
    return ctx.state.model_copy(
        update={
            "assessment_status": outcome.tag,
            "selected_remediation": (
                preferred_option if isinstance(preferred_option, str) and preferred_option.strip() else ctx.state.selected_remediation
            ),
        }
    )


def _after_plan_verified_remediation(ctx, outcome: Outcome):
    selected_remediation = outcome.payload.get("selected_remediation")
    return ctx.state.model_copy(
        update={
            "remediation_status": outcome.tag,
            "selected_remediation": (
                selected_remediation
                if isinstance(selected_remediation, str) and selected_remediation.strip()
                else ctx.state.selected_remediation
            ),
        }
    )


def _after_prepare_closure_package(ctx, outcome: Outcome):
    return ctx.state.model_copy(update={"closure_status": outcome.tag})


class SecurityFindingToVerifiedRemediation(Workflow):
    """Turn a security finding into a durable remediation and closure package."""

    name = "security_finding_to_verified_remediation"

    class State(BaseModel):
        finding_title: str = ""
        finding_source: str = "other"
        severity: str = "unknown"
        affected_system: str | None = None
        sponsor_role: str | None = None
        evidence_paths: list[str] = Field(default_factory=list)
        deployment_constraints: list[str] = Field(default_factory=list)
        evidence_pack_status: str | None = None
        evidence_pack_child_run_id: str | None = None
        ready_for_downstream_assessment: bool = False
        assessment_status: str | None = None
        remediation_status: str | None = None
        closure_status: str | None = None
        selected_remediation: str | None = None
        published: bool = False

    assessment_session = Session()
    remediation_session = Session()
    closure_session = Session()

    request = Artifact("{run_folder}/request.md")
    security_package_checklist = Artifact("{package_folder}/assets/security_remediation_package_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json")
    finding_scope_brief = Artifact("{workflow_folder}/finding_scope_brief.md")
    security_evidence_pack = Artifact("{workflow_folder}/security_evidence_pack.md")
    security_evidence_pack_summary = Artifact("{workflow_folder}/security_evidence_pack_summary.json")
    security_evidence_gap_register = Artifact("{workflow_folder}/security_evidence_gap_register.md")
    security_evidence_pack_receipt = Artifact("{workflow_folder}/security_evidence_pack_receipt.json")
    exploit_summary = Artifact("{workflow_folder}/exploit_summary.md")
    affected_surface = Artifact("{workflow_folder}/affected_surface.md")
    root_cause_analysis = Artifact("{workflow_folder}/root_cause_analysis.md")
    remediation_options = Artifact("{workflow_folder}/remediation_options.md")
    assessment_summary = Artifact("{workflow_folder}/assessment_summary.json")
    selected_remediation_plan = Artifact("{workflow_folder}/selected_remediation_plan.md")
    verification_plan = Artifact("{workflow_folder}/verification_plan.md")
    rollout_plan = Artifact("{workflow_folder}/rollout_plan.md")
    rollback_safety_plan = Artifact("{workflow_folder}/rollback_safety_plan.md")
    remediation_summary = Artifact("{workflow_folder}/remediation_summary.json")
    security_remediation_package = Artifact("{workflow_folder}/security_remediation_package.md")
    stakeholder_communication_draft = Artifact("{workflow_folder}/stakeholder_communication_draft.md")
    closure_evidence_requirements = Artifact("{workflow_folder}/closure_evidence_requirements.md")
    remediation_receipt = Artifact("{workflow_folder}/remediation_receipt.json")

    assess_security_finding = produce_verify_step(
        producer_prompt=Prompt.file("prompts/assessment_producer.md"),
        verifier_prompt=Prompt.file("prompts/assessment_verifier.md"),
        session=assessment_session,
        requires=[
            request,
            invocation_contract,
            finding_scope_brief,
            security_evidence_pack,
            security_evidence_pack_summary,
            security_evidence_gap_register,
            security_evidence_pack_receipt,
        ],
        producer_writes=[
            exploit_summary,
            affected_surface,
            root_cause_analysis,
            remediation_options,
            assessment_summary,
        ],
        control_schema=SecurityAssessmentPayload,
        routes=ASSESS_SECURITY_FINDING_ROUTE_CONTRACTS,
        after_verifier=_after_assess_security_finding,
    )
    plan_verified_remediation = produce_verify_step(
        producer_prompt=Prompt.file("prompts/remediation_producer.md"),
        verifier_prompt=Prompt.file("prompts/remediation_verifier.md"),
        session=remediation_session,
        requires=[
            invocation_contract,
            security_evidence_pack_summary,
            exploit_summary,
            affected_surface,
            root_cause_analysis,
            remediation_options,
            assessment_summary,
        ],
        producer_writes=[
            selected_remediation_plan,
            verification_plan,
            rollout_plan,
            rollback_safety_plan,
            remediation_summary,
        ],
        control_schema=VerifiedRemediationPayload,
        routes=PLAN_VERIFIED_REMEDIATION_ROUTE_CONTRACTS,
        after_verifier=_after_plan_verified_remediation,
    )
    prepare_closure_package = produce_verify_step(
        producer_prompt=Prompt.file("prompts/closure_producer.md"),
        verifier_prompt=Prompt.file("prompts/closure_verifier.md"),
        session=closure_session,
        requires=[
            request,
            invocation_contract,
            security_package_checklist,
            finding_scope_brief,
            security_evidence_pack,
            security_evidence_pack_summary,
            security_evidence_gap_register,
            exploit_summary,
            affected_surface,
            root_cause_analysis,
            remediation_options,
            selected_remediation_plan,
            verification_plan,
            rollout_plan,
            rollback_safety_plan,
            remediation_summary,
        ],
        producer_writes=[
            security_remediation_package,
            stakeholder_communication_draft,
            closure_evidence_requirements,
        ],
        control_schema=SecurityClosurePackagePayload,
        routes=PREPARE_CLOSURE_PACKAGE_ROUTE_CONTRACTS,
        after_verifier=_after_prepare_closure_package,
    )

    @python_step(
        name="bootstrap",
        requires=[request],
        writes=[invocation_contract],
        routes={"inputs_prepared": "compose_evidence_pack"},
    )
    def bootstrap(state: State, ctx):
        params = ctx.params
        next_state = state.model_copy(
            update={
                "finding_title": params.finding_title,
                "finding_source": params.finding_source,
                "severity": params.severity,
                "affected_system": params.affected_system,
                "sponsor_role": params.sponsor_role,
                "evidence_paths": list(params.evidence_paths),
                "deployment_constraints": list(params.deployment_constraints),
                "evidence_pack_status": None,
                "evidence_pack_child_run_id": None,
                "ready_for_downstream_assessment": False,
                "assessment_status": None,
                "remediation_status": None,
                "closure_status": None,
                "selected_remediation": None,
                "published": False,
            }
        )
        open_workflow_sessions(ctx, "assessment_session", "remediation_session", "closure_session")
        write_invocation_contract(
            ctx,
            {
                "finding_title": next_state.finding_title,
                "finding_source": next_state.finding_source,
                "severity": next_state.severity,
                "affected_system": next_state.affected_system,
                "sponsor_role": next_state.sponsor_role,
                "evidence_paths": next_state.evidence_paths,
                "deployment_constraints": next_state.deployment_constraints,
            },
        )
        return next_state, Event("inputs_prepared")

    @python_step(
        name="compose_evidence_pack",
        requires=[request, invocation_contract],
        writes=[
            finding_scope_brief,
            security_evidence_pack,
            security_evidence_pack_summary,
            security_evidence_gap_register,
            security_evidence_pack_receipt,
        ],
        routes={"evidence_pack_adopted": "assess_security_finding"},
    )
    def compose_evidence_pack(state: State, ctx):
        child = run_child_workflow(
            ctx,
            "investigation_request_to_evidence_pack",
            message=_child_message(state),
            parameters={
                "investigation_title": state.finding_title,
                "investigation_kind": "security_remediation",
                "sponsor_role": state.sponsor_role,
                "evidence_paths": state.evidence_paths,
            },
        )
        if child.last_event is not None and child.last_event.tag == "question":
            return state.model_copy(
                update={
                    "evidence_pack_status": "question",
                    "evidence_pack_child_run_id": child.run_id,
                }
            ), Event("question", reason=child.last_event.reason, question=child.last_event.question)
        if child.last_event is not None and child.last_event.tag == "blocked":
            return state.model_copy(
                update={
                    "evidence_pack_status": "blocked",
                    "evidence_pack_child_run_id": child.run_id,
                }
            ), Event("blocked", reason=child.last_event.reason, question=child.last_event.question)

        require_child_workflow_result(
            child,
            status="success",
            last_event="evidence_pack_published",
            required_artifacts=(
                "investigation_scope_brief",
                "evidence_pack",
                "evidence_pack_summary",
                "evidence_gap_register",
                "evidence_pack_receipt",
            ),
        )
        summary = read_json_object(child.output_artifacts["evidence_pack_summary"])
        if summary.get("investigation_kind") != "security_remediation":
            raise ValueError("adopted security_evidence_pack_summary.json must report investigation_kind=security_remediation")
        ready_for_downstream_assessment = summary.get("ready_for_downstream_assessment")
        if not isinstance(ready_for_downstream_assessment, bool):
            raise ValueError(
                "adopted security_evidence_pack_summary.json must define boolean ready_for_downstream_assessment"
            )
        if not ready_for_downstream_assessment:
            return state.model_copy(
                update={
                    "evidence_pack_status": "blocked",
                    "evidence_pack_child_run_id": child.run_id,
                    "ready_for_downstream_assessment": False,
                }
            ), Event(
                "blocked",
                reason="Child evidence pack published without downstream-readiness approval.",
            )
        adopt_child_artifacts(
            ctx,
            child,
            mapping={
                "investigation_scope_brief": "finding_scope_brief.md",
                "evidence_pack": "security_evidence_pack.md",
                "evidence_pack_summary": "security_evidence_pack_summary.json",
                "evidence_gap_register": "security_evidence_gap_register.md",
                "evidence_pack_receipt": "security_evidence_pack_receipt.json",
            },
        )
        return state.model_copy(
            update={
                "evidence_pack_status": "evidence_pack_adopted",
                "evidence_pack_child_run_id": child.run_id,
                "ready_for_downstream_assessment": ready_for_downstream_assessment,
            }
        ), Event("evidence_pack_adopted")

    @python_step(
        name="publish_remediation",
        requires=[
            security_evidence_pack_summary,
            remediation_summary,
            selected_remediation_plan,
            verification_plan,
            rollout_plan,
            rollback_safety_plan,
            security_remediation_package,
            stakeholder_communication_draft,
            closure_evidence_requirements,
        ],
        writes=[remediation_receipt],
        routes={"remediation_published": FINISH},
    )
    def publish_remediation(state: State, ctx):
        required_paths = {
            "security_evidence_pack_summary": ctx.workflow_folder / "security_evidence_pack_summary.json",
            "security_evidence_pack_receipt": ctx.workflow_folder / "security_evidence_pack_receipt.json",
            "remediation_summary": ctx.workflow_folder / "remediation_summary.json",
            "selected_remediation_plan": ctx.workflow_folder / "selected_remediation_plan.md",
            "verification_plan": ctx.workflow_folder / "verification_plan.md",
            "rollout_plan": ctx.workflow_folder / "rollout_plan.md",
            "rollback_safety_plan": ctx.workflow_folder / "rollback_safety_plan.md",
            "security_remediation_package": ctx.workflow_folder / "security_remediation_package.md",
            "stakeholder_communication_draft": ctx.workflow_folder / "stakeholder_communication_draft.md",
            "closure_evidence_requirements": ctx.workflow_folder / "closure_evidence_requirements.md",
        }
        for artifact_path in required_paths.values():
            if not artifact_path.exists():
                raise FileNotFoundError(f"missing required publication artifact at {artifact_path}")

        evidence_summary = read_json_object(required_paths["security_evidence_pack_summary"])
        if evidence_summary.get("investigation_kind") != "security_remediation":
            raise ValueError("security_evidence_pack_summary.json must define investigation_kind=security_remediation")
        source_count = require_non_negative_int(
            evidence_summary.get("source_count"),
            "security_evidence_pack_summary.json must define non-negative source_count",
        )
        finding_count = require_non_negative_int(
            evidence_summary.get("finding_count"),
            "security_evidence_pack_summary.json must define non-negative finding_count",
        )
        unresolved_gap_count = require_non_negative_int(
            evidence_summary.get("unresolved_gap_count"),
            "security_evidence_pack_summary.json must define non-negative unresolved_gap_count",
        )
        key_findings = require_string_list(
            evidence_summary.get("key_findings"),
            "security_evidence_pack_summary.json must define non-empty key_findings",
        )

        summary = read_json_object(required_paths["remediation_summary"])
        selected_remediation = require_non_empty_string(
            summary.get("selected_remediation"),
            error_message="remediation_summary.json must define a non-empty selected_remediation",
            coerce=True,
        )
        verification_ready = summary.get("verification_ready")
        rollout_ready = summary.get("rollout_ready")
        if not isinstance(verification_ready, bool):
            raise ValueError("remediation_summary.json must define boolean verification_ready")
        if not isinstance(rollout_ready, bool):
            raise ValueError("remediation_summary.json must define boolean rollout_ready")
        authoritative_artifacts = require_string_list(
            summary.get("authoritative_artifacts"),
            "remediation_summary.json must define non-empty authoritative_artifacts",
        )

        write_publication_receipt(
            ctx,
            "remediation_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "finding_title": state.finding_title,
                "finding_source": state.finding_source,
                "severity": state.severity,
                "affected_system": state.affected_system,
                "sponsor_role": state.sponsor_role,
                "evidence_paths": state.evidence_paths,
                "deployment_constraints": state.deployment_constraints,
                "evidence_pack_child_run_id": state.evidence_pack_child_run_id,
                "ready_for_downstream_assessment": state.ready_for_downstream_assessment,
                "selected_remediation": selected_remediation,
                "verification_ready": verification_ready,
                "rollout_ready": rollout_ready,
                "source_count": source_count,
                "finding_count": finding_count,
                "unresolved_gap_count": unresolved_gap_count,
                "key_findings": key_findings,
                "authoritative_artifacts": authoritative_artifacts,
                **{name: str(path) for name, path in required_paths.items()},
                "published": True,
            },
        )
        return state.model_copy(
            update={
                "selected_remediation": selected_remediation,
                "published": True,
            }
        ), Event("remediation_published")

    entry = bootstrap



def _child_message(state: SecurityFindingToVerifiedRemediation.State) -> str:
    if state.affected_system:
        return f'Assemble the evidence pack for the security finding "{state.finding_title}" affecting {state.affected_system}.'
    return f'Assemble the evidence pack for the security finding "{state.finding_title}".'


__all__ = ["SecurityFindingToVerifiedRemediation"]
