"""Incident hardening workflow package."""

from __future__ import annotations

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.stdlib import (
        read_json_object,
        require_non_empty_string,
        require_non_negative_int,
    )
    from autoloop_v3.stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from autoloop_v3.stdlib.lifecycle import (
        open_workflow_sessions,
        write_invocation_contract,
        write_publication_receipt,
    )
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from stdlib import (
        read_json_object,
        require_non_empty_string,
        require_non_negative_int,
    )
    from stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from workflow import Artifact, FAIL, PairStep, Session, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event, Outcome

from .contracts import (
    ASSEMBLE_EVIDENCE_ROUTE_CONTRACTS,
    FRAME_INCIDENT_ROUTE_CONTRACTS,
    PREPARE_HARDENING_PROGRAM_ROUTE_CONTRACTS,
    RANK_CAUSE_HYPOTHESES_ROUTE_CONTRACTS,
    IncidentEvidencePayload,
    IncidentFramingPayload,
    IncidentHardeningProgramPayload,
    IncidentHypothesisPayload,
)


class IncidentToHardeningProgram(Workflow):
    """Turn an incident into a durable hardening program and response package."""

    name = "incident_to_hardening_program"

    class State(BaseModel):
        incident_title: str = ""
        incident_window: str | None = None
        affected_system: str | None = None
        severity: str | None = None
        incident_commander: str | None = None
        evidence_paths: list[str] = Field(default_factory=list)
        framing_status: str | None = None
        evidence_status: str | None = None
        analysis_status: str | None = None
        program_status: str | None = None
        recommended_posture: str | None = None
        published: bool = False

    frame_session = Session()
    evidence_session = Session()
    analysis_session = Session()
    program_session = Session()

    request = Artifact("{run_folder}/request.md")
    framework_architecture_doc = Artifact("{package_folder}/../../docs/architecture.md")
    framework_authoring_doc = Artifact("{package_folder}/../../docs/authoring.md")
    workflow_instructions = Artifact("{package_folder}/../../Workflow_Instructions.md")
    incident_package_checklist = Artifact("{package_folder}/assets/incident_hardening_package_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json")
    incident_scope_brief = Artifact("{workflow_folder}/incident_scope_brief.md")
    response_objectives = Artifact("{workflow_folder}/response_objectives.md")
    evidence_intake_register = Artifact("{workflow_folder}/evidence_intake_register.md")
    incident_timeline = Artifact("{workflow_folder}/incident_timeline.md")
    affected_surface = Artifact("{workflow_folder}/affected_surface.md")
    blast_radius = Artifact("{workflow_folder}/blast_radius.md")
    observability_gaps = Artifact("{workflow_folder}/observability_gaps.md")
    evidence_gap_register = Artifact("{workflow_folder}/evidence_gap_register.md")
    cause_hypothesis_ranking = Artifact("{workflow_folder}/cause_hypothesis_ranking.md")
    immediate_mitigation_plan = Artifact("{workflow_folder}/immediate_mitigation_plan.md")
    validation_plan = Artifact("{workflow_folder}/validation_plan.md")
    incident_summary = Artifact("{workflow_folder}/incident_summary.json")
    hardening_program = Artifact("{workflow_folder}/hardening_program.md")
    hardening_backlog = Artifact("{workflow_folder}/hardening_backlog.md")
    follow_up_owners = Artifact("{workflow_folder}/follow_up_owners.md")
    stakeholder_communications_draft = Artifact("{workflow_folder}/stakeholder_communications_draft.md")
    incident_resolution_package = Artifact("{workflow_folder}/incident_resolution_package.md")
    incident_receipt = Artifact("{workflow_folder}/incident_receipt.json")

    bootstrap = SystemStep(
        name="bootstrap",
        requires=[request],
        produces={"invocation_contract": invocation_contract},
    )
    frame_incident = PairStep(
        name="frame_incident",
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
            "incident_scope_brief": incident_scope_brief,
            "response_objectives": response_objectives,
            "evidence_intake_register": evidence_intake_register,
        },
        expected_output_schema=IncidentFramingPayload,
        route_contracts=FRAME_INCIDENT_ROUTE_CONTRACTS,
    )
    assemble_evidence_pack = PairStep(
        name="assemble_evidence_pack",
        session=evidence_session,
        producer="prompts/evidence_producer.md",
        verifier="prompts/evidence_verifier.md",
        requires=[
            incident_scope_brief,
            response_objectives,
            evidence_intake_register,
        ],
        produces={
            "incident_timeline": incident_timeline,
            "affected_surface": affected_surface,
            "blast_radius": blast_radius,
            "observability_gaps": observability_gaps,
            "evidence_gap_register": evidence_gap_register,
        },
        expected_output_schema=IncidentEvidencePayload,
        route_contracts=ASSEMBLE_EVIDENCE_ROUTE_CONTRACTS,
    )
    rank_cause_hypotheses = PairStep(
        name="rank_cause_hypotheses",
        session=analysis_session,
        producer="prompts/analysis_producer.md",
        verifier="prompts/analysis_verifier.md",
        requires=[
            incident_scope_brief,
            response_objectives,
            incident_timeline,
            affected_surface,
            blast_radius,
            observability_gaps,
            evidence_gap_register,
        ],
        produces={
            "cause_hypothesis_ranking": cause_hypothesis_ranking,
            "immediate_mitigation_plan": immediate_mitigation_plan,
            "validation_plan": validation_plan,
            "incident_summary": incident_summary,
        },
        expected_output_schema=IncidentHypothesisPayload,
        route_contracts=RANK_CAUSE_HYPOTHESES_ROUTE_CONTRACTS,
    )
    prepare_hardening_program = PairStep(
        name="prepare_hardening_program",
        session=program_session,
        producer="prompts/program_producer.md",
        verifier="prompts/program_verifier.md",
        requires=[
            incident_package_checklist,
            incident_scope_brief,
            response_objectives,
            incident_timeline,
            affected_surface,
            blast_radius,
            observability_gaps,
            evidence_gap_register,
            cause_hypothesis_ranking,
            immediate_mitigation_plan,
            validation_plan,
            incident_summary,
        ],
        produces={
            "hardening_program": hardening_program,
            "hardening_backlog": hardening_backlog,
            "follow_up_owners": follow_up_owners,
            "stakeholder_communications_draft": stakeholder_communications_draft,
            "incident_resolution_package": incident_resolution_package,
        },
        expected_output_schema=IncidentHardeningProgramPayload,
        route_contracts=PREPARE_HARDENING_PROGRAM_ROUTE_CONTRACTS,
    )
    publish_incident_package = SystemStep(
        name="publish_incident_package",
        requires=[
            incident_summary,
            hardening_program,
            hardening_backlog,
            follow_up_owners,
            stakeholder_communications_draft,
            incident_resolution_package,
        ],
        produces={"incident_receipt": incident_receipt},
    )

    entry = bootstrap

    transitions = merge_transitions(
        global_routes(pause_on_outcome_tags("question", "blocked"), failed=FAIL),
        {
            bootstrap: {"inputs_prepared": frame_incident},
            frame_incident: {
                "incident_framed": assemble_evidence_pack,
                "needs_rework": frame_incident,
                "needs_replan": frame_incident,
            },
            assemble_evidence_pack: {
                "evidence_pack_ready": rank_cause_hypotheses,
                "needs_rework": assemble_evidence_pack,
                "needs_replan": frame_incident,
            },
            rank_cause_hypotheses: {
                "hypotheses_ranked": prepare_hardening_program,
                "needs_rework": rank_cause_hypotheses,
                "needs_replan": frame_incident,
            },
            prepare_hardening_program: {
                "hardening_program_ready": publish_incident_package,
                "needs_rework": prepare_hardening_program,
                "needs_replan": rank_cause_hypotheses,
            },
            publish_incident_package: {"incident_package_published": SUCCESS},
        },
    )

    @staticmethod
    def on_bootstrap(state: State, ctx) -> tuple[State, Event]:
        params = ctx.params
        next_state = state.model_copy(
            update={
                "incident_title": params.incident_title,
                "incident_window": params.incident_window,
                "affected_system": params.affected_system,
                "severity": params.severity,
                "incident_commander": params.incident_commander,
                "evidence_paths": list(params.evidence_paths),
                "framing_status": None,
                "evidence_status": None,
                "analysis_status": None,
                "program_status": None,
                "recommended_posture": None,
                "published": False,
            }
        )
        open_workflow_sessions(ctx, "frame_session", "evidence_session", "analysis_session", "program_session")
        write_invocation_contract(
            ctx,
            {
                "incident_title": next_state.incident_title,
                "incident_window": next_state.incident_window,
                "affected_system": next_state.affected_system,
                "severity": next_state.severity,
                "incident_commander": next_state.incident_commander,
                "evidence_paths": next_state.evidence_paths,
            },
        )
        return next_state, Event("inputs_prepared")

    @staticmethod
    def on_frame_incident(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"framing_status": outcome.tag})

    @staticmethod
    def on_assemble_evidence_pack(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"evidence_status": outcome.tag})

    @staticmethod
    def on_rank_cause_hypotheses(state: State, outcome: Outcome, artifacts):
        del artifacts
        recommended_posture = outcome.payload.get("recommended_posture")
        return state.model_copy(
            update={
                "analysis_status": outcome.tag,
                "recommended_posture": (
                    recommended_posture if isinstance(recommended_posture, str) else state.recommended_posture
                ),
            }
        )

    @staticmethod
    def on_prepare_hardening_program(state: State, outcome: Outcome, artifacts):
        del artifacts
        recommended_posture = outcome.payload.get("recommended_posture")
        return state.model_copy(
            update={
                "program_status": outcome.tag,
                "recommended_posture": (
                    recommended_posture if isinstance(recommended_posture, str) else state.recommended_posture
                ),
            }
        )

    @staticmethod
    def on_publish_incident_package(state: State, ctx) -> tuple[State, Event]:
        summary_path = ctx.workflow_folder / "incident_summary.json"
        hardening_program_path = ctx.workflow_folder / "hardening_program.md"
        hardening_backlog_path = ctx.workflow_folder / "hardening_backlog.md"
        owners_path = ctx.workflow_folder / "follow_up_owners.md"
        communications_path = ctx.workflow_folder / "stakeholder_communications_draft.md"
        package_path = ctx.workflow_folder / "incident_resolution_package.md"
        for artifact_path in (
            summary_path,
            hardening_program_path,
            hardening_backlog_path,
            owners_path,
            communications_path,
            package_path,
        ):
            if not artifact_path.exists():
                raise FileNotFoundError(f"missing required publication artifact at {artifact_path}")

        summary = read_json_object(summary_path)
        recommended_posture = require_non_empty_string(
            summary.get("recommended_posture"),
            error_message="incident_summary.json must define a non-empty recommended_posture",
            coerce=False,
        )
        primary_hypothesis = require_non_empty_string(
            summary.get("primary_hypothesis"),
            error_message="incident_summary.json must define a non-empty primary_hypothesis",
            coerce=False,
        )
        backlog_items = require_non_negative_int(
            summary.get("hardening_backlog_items"),
            "incident_summary.json must define a non-negative hardening_backlog_items",
        )

        write_publication_receipt(
            ctx,
            "incident_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "incident_title": state.incident_title,
                "incident_window": state.incident_window,
                "affected_system": state.affected_system,
                "severity": state.severity,
                "incident_commander": state.incident_commander,
                "recommended_posture": recommended_posture,
                "primary_hypothesis": primary_hypothesis,
                "hardening_backlog_items": backlog_items,
                "incident_summary": str(summary_path),
                "hardening_program": str(hardening_program_path),
                "hardening_backlog": str(hardening_backlog_path),
                "follow_up_owners": str(owners_path),
                "stakeholder_communications_draft": str(communications_path),
                "incident_resolution_package": str(package_path),
                "published": True,
            },
        )
        return state.model_copy(
            update={"published": True, "recommended_posture": recommended_posture}
        ), Event("incident_package_published")

    on_outcome = staticmethod(event_on_outcome_tags("question", "blocked", "failed"))
__all__ = ["IncidentToHardeningProgram"]
