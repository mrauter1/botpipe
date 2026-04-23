"""Release go/no-go workflow package."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from autoloop_v3.stdlib.lifecycle import (
        open_workflow_sessions,
        write_invocation_contract,
        write_publication_receipt,
    )
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from workflow import Artifact, FAIL, PairStep, Session, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event, Outcome

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

    request = Artifact("{run_folder}/request.md")
    framework_architecture_doc = Artifact("{package_folder}/../../docs/architecture.md")
    framework_authoring_doc = Artifact("{package_folder}/../../docs/authoring.md")
    workflow_instructions = Artifact("{package_folder}/../../Workflow_Instructions.md")
    decision_package_checklist = Artifact("{package_folder}/assets/release_decision_package_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json")
    release_scope_brief = Artifact("{workflow_folder}/release_scope_brief.md")
    decision_criteria = Artifact("{workflow_folder}/decision_criteria.md")
    evidence_intake_register = Artifact("{workflow_folder}/evidence_intake_register.md")
    release_inventory = Artifact("{workflow_folder}/release_inventory.md")
    test_evidence_pack = Artifact("{workflow_folder}/test_evidence_pack.md")
    operational_readiness = Artifact("{workflow_folder}/operational_readiness.md")
    rollback_readiness = Artifact("{workflow_folder}/rollback_readiness.md")
    blocking_issues = Artifact("{workflow_folder}/blocking_issues.md")
    go_no_go_assessment = Artifact("{workflow_folder}/go_no_go_assessment.md")
    risk_register = Artifact("{workflow_folder}/risk_register.md")
    decision_summary = Artifact("{workflow_folder}/decision_summary.json")
    release_decision_package = Artifact("{workflow_folder}/release_decision_package.md")
    release_communications_draft = Artifact("{workflow_folder}/release_communications_draft.md")
    decision_receipt = Artifact("{workflow_folder}/decision_receipt.json")

    bootstrap = SystemStep(
        name="bootstrap",
        requires=[request],
        produces={"invocation_contract": invocation_contract},
    )
    frame_release = PairStep(
        name="frame_release",
        session=frame_session,
        producer="prompts/frame_producer.md",
        verifier="prompts/frame_verifier.md",
        requires=[
            request,
            invocation_contract,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        produces={
            "release_scope_brief": release_scope_brief,
            "decision_criteria": decision_criteria,
            "evidence_intake_register": evidence_intake_register,
        },
        expected_output_schema=ReleaseFramingPayload,
        route_contracts=FRAME_RELEASE_ROUTE_CONTRACTS,
    )
    assemble_evidence_pack = PairStep(
        name="assemble_evidence_pack",
        session=evidence_session,
        producer="prompts/evidence_producer.md",
        verifier="prompts/evidence_verifier.md",
        requires=[
            request,
            invocation_contract,
            release_scope_brief,
            decision_criteria,
            evidence_intake_register,
        ],
        produces={
            "release_inventory": release_inventory,
            "test_evidence_pack": test_evidence_pack,
            "operational_readiness": operational_readiness,
            "rollback_readiness": rollback_readiness,
            "blocking_issues": blocking_issues,
        },
        expected_output_schema=ReleaseEvidencePayload,
        route_contracts=ASSEMBLE_EVIDENCE_ROUTE_CONTRACTS,
    )
    assess_go_no_go = PairStep(
        name="assess_go_no_go",
        session=assessment_session,
        producer="prompts/assessment_producer.md",
        verifier="prompts/assessment_verifier.md",
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
        produces={
            "go_no_go_assessment": go_no_go_assessment,
            "risk_register": risk_register,
            "decision_summary": decision_summary,
        },
        expected_output_schema=ReleaseAssessmentPayload,
        route_contracts=ASSESS_GO_NO_GO_ROUTE_CONTRACTS,
    )
    prepare_decision_package = PairStep(
        name="prepare_decision_package",
        session=package_session,
        producer="prompts/package_producer.md",
        verifier="prompts/package_verifier.md",
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
        produces={
            "release_decision_package": release_decision_package,
            "release_communications_draft": release_communications_draft,
        },
        expected_output_schema=ReleaseDecisionPackagePayload,
        route_contracts=PREPARE_DECISION_PACKAGE_ROUTE_CONTRACTS,
    )
    publish_decision = SystemStep(
        name="publish_decision",
        requires=[decision_summary, release_decision_package, release_communications_draft],
        produces={"decision_receipt": decision_receipt},
    )

    entry = bootstrap

    transitions = merge_transitions(
        global_routes(pause_on_outcome_tags("question", "blocked"), failed=FAIL),
        {
            bootstrap: {"inputs_prepared": frame_release},
            frame_release: {
                "release_framed": assemble_evidence_pack,
                "needs_rework": frame_release,
                "needs_replan": frame_release,
            },
            assemble_evidence_pack: {
                "evidence_pack_ready": assess_go_no_go,
                "needs_rework": assemble_evidence_pack,
                "needs_replan": frame_release,
            },
            assess_go_no_go: {
                "assessment_ready": prepare_decision_package,
                "needs_rework": assess_go_no_go,
                "needs_replan": frame_release,
            },
            prepare_decision_package: {
                "decision_package_ready": publish_decision,
                "needs_rework": prepare_decision_package,
                "needs_replan": assess_go_no_go,
            },
            publish_decision: {"decision_published": SUCCESS},
        },
    )

    @staticmethod
    def on_bootstrap(state: State, ctx) -> tuple[State, Event]:
        payload = dict(ctx.workflow_params)
        release_name = str(payload.get("release_name") or "").strip()
        if not release_name:
            raise ValueError("release_candidate_to_go_no_go requires workflow parameter 'release_name'")

        target_date = _normalize_optional_text(payload.get("target_date"))
        deployment_environment = str(payload.get("deployment_environment") or "production").strip() or "production"
        release_owner = _normalize_optional_text(payload.get("release_owner"))
        evidence_paths = _normalize_evidence_paths(payload.get("evidence_paths"))

        next_state = state.model_copy(
            update={
                "release_name": release_name,
                "target_date": target_date,
                "deployment_environment": deployment_environment,
                "release_owner": release_owner,
                "evidence_paths": evidence_paths,
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
        return next_state, Event("inputs_prepared")

    @staticmethod
    def on_frame_release(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"framing_status": outcome.tag})

    @staticmethod
    def on_assemble_evidence_pack(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"evidence_status": outcome.tag})

    @staticmethod
    def on_assess_go_no_go(state: State, outcome: Outcome, artifacts):
        del artifacts
        recommended_decision = outcome.payload.get("recommended_decision")
        return state.model_copy(
            update={
                "assessment_status": outcome.tag,
                "recommended_decision": recommended_decision if isinstance(recommended_decision, str) else state.recommended_decision,
            }
        )

    @staticmethod
    def on_prepare_decision_package(state: State, outcome: Outcome, artifacts):
        del artifacts
        decision = outcome.payload.get("decision")
        return state.model_copy(
            update={
                "packaging_status": outcome.tag,
                "recommended_decision": decision if isinstance(decision, str) else state.recommended_decision,
            }
        )

    @staticmethod
    def on_publish_decision(state: State, ctx) -> tuple[State, Event]:
        summary_path = ctx.workflow_folder / "decision_summary.json"
        decision_package_path = ctx.workflow_folder / "release_decision_package.md"
        communications_path = ctx.workflow_folder / "release_communications_draft.md"
        for artifact_path in (summary_path, decision_package_path, communications_path):
            if not artifact_path.exists():
                raise FileNotFoundError(f"missing required publication artifact at {artifact_path}")

        summary = _read_json(summary_path)
        recommended_decision = summary.get("recommended_decision")
        if not isinstance(recommended_decision, str) or not recommended_decision.strip():
            raise ValueError("decision_summary.json must define a non-empty recommended_decision")

        write_publication_receipt(
            ctx,
            "decision_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "release_name": state.release_name,
                "target_date": state.target_date,
                "deployment_environment": state.deployment_environment,
                "release_owner": state.release_owner,
                "recommended_decision": recommended_decision,
                "blocking_issue_count": summary.get("blocking_issue_count"),
                "decision_summary": str(summary_path),
                "decision_package": str(decision_package_path),
                "communications_draft": str(communications_path),
                "published": True,
            },
        )
        return state.model_copy(update={"published": True, "recommended_decision": recommended_decision}), Event(
            "decision_published"
        )

    on_outcome = staticmethod(event_on_outcome_tags("question", "blocked", "failed"))


def _normalize_optional_text(value) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_evidence_paths(raw_value) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        candidates = raw_value
    else:
        candidates = [raw_value]
    normalized: list[str] = []
    for value in candidates:
        path = str(value).strip()
        if path and path not in normalized:
            normalized.append(path)
    return normalized


def _read_json(path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return raw


__all__ = ["ReleaseCandidateToGoNoGo"]
