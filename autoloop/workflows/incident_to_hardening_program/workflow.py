"""Incident hardening workflow package."""

from __future__ import annotations

from pydantic import BaseModel, Field

from autoloop.stdlib import (
    read_json_object,
    require_non_empty_string,
    require_non_negative_int,
)
from autoloop.stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from autoloop import Event, FAIL, FINISH, Outcome, Prompt, Session, Workflow, produce_verify_step, python_step
from autoloop.core import Artifact

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


def _after_frame_incident(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    ctx.state.framing_status = outcome.tag
    return None


def _after_assemble_evidence_pack(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    ctx.state.evidence_status = outcome.tag
    return None


def _after_rank_cause_hypotheses(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    recommended_posture = outcome.payload.get("recommended_posture")
    ctx.state.analysis_status = outcome.tag
    if isinstance(recommended_posture, str):
        ctx.state.recommended_posture = recommended_posture
    return None


def _after_prepare_hardening_program(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    recommended_posture = outcome.payload.get("recommended_posture")
    ctx.state.program_status = outcome.tag
    if isinstance(recommended_posture, str):
        ctx.state.recommended_posture = recommended_posture
    return None


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
    framework_architecture_doc = Artifact("{package_folder}/../../../docs/architecture.md")
    framework_authoring_doc = Artifact("{package_folder}/../../../docs/authoring.md")
    workflow_instructions = Artifact("{package_folder}/../../../Workflow_Instructions.md")
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

    @python_step(
        name="bootstrap",
        requires=[request],
        writes=[invocation_contract],
        routes={"inputs_prepared": "frame_incident"},
    )
    def bootstrap(ctx):
        params = ctx.params
        next_state = ctx.state.model_copy(
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
        ctx.state = next_state
        return "inputs_prepared"

    frame_incident = produce_verify_step(
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
        producer_writes=[
            incident_scope_brief,
            response_objectives,
            evidence_intake_register,
        ],
        control_schema=IncidentFramingPayload,
        routes=FRAME_INCIDENT_ROUTE_CONTRACTS,
        after_verifier=_after_frame_incident,
    )

    assemble_evidence_pack = produce_verify_step(
        producer_prompt=Prompt.file("prompts/evidence_producer.md"),
        verifier_prompt=Prompt.file("prompts/evidence_verifier.md"),
        session=evidence_session,
        requires=[
            incident_scope_brief,
            response_objectives,
            evidence_intake_register,
        ],
        producer_writes=[
            incident_timeline,
            affected_surface,
            blast_radius,
            observability_gaps,
            evidence_gap_register,
        ],
        control_schema=IncidentEvidencePayload,
        routes=ASSEMBLE_EVIDENCE_ROUTE_CONTRACTS,
        after_verifier=_after_assemble_evidence_pack,
    )

    rank_cause_hypotheses = produce_verify_step(
        producer_prompt=Prompt.file("prompts/analysis_producer.md"),
        verifier_prompt=Prompt.file("prompts/analysis_verifier.md"),
        session=analysis_session,
        requires=[
            incident_scope_brief,
            response_objectives,
            incident_timeline,
            affected_surface,
            blast_radius,
            observability_gaps,
            evidence_gap_register,
        ],
        producer_writes=[
            cause_hypothesis_ranking,
            immediate_mitigation_plan,
            validation_plan,
            incident_summary,
        ],
        control_schema=IncidentHypothesisPayload,
        routes=RANK_CAUSE_HYPOTHESES_ROUTE_CONTRACTS,
        after_verifier=_after_rank_cause_hypotheses,
    )

    prepare_hardening_program = produce_verify_step(
        producer_prompt=Prompt.file("prompts/program_producer.md"),
        verifier_prompt=Prompt.file("prompts/program_verifier.md"),
        session=program_session,
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
        producer_writes=[
            hardening_program,
            hardening_backlog,
            follow_up_owners,
            stakeholder_communications_draft,
            incident_resolution_package,
        ],
        control_schema=IncidentHardeningProgramPayload,
        routes=PREPARE_HARDENING_PROGRAM_ROUTE_CONTRACTS,
        after_verifier=_after_prepare_hardening_program,
    )

    @python_step(
        name="publish_incident_package",
        requires=[
            incident_summary,
            hardening_program,
            hardening_backlog,
            follow_up_owners,
            stakeholder_communications_draft,
            incident_resolution_package,
        ],
        writes=[incident_receipt],
        routes={"incident_package_published": FINISH},
    )
    def publish_incident_package(ctx):
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
                "incident_title": ctx.state.incident_title,
                "incident_window": ctx.state.incident_window,
                "affected_system": ctx.state.affected_system,
                "severity": ctx.state.severity,
                "incident_commander": ctx.state.incident_commander,
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
        ctx.state.published = True
        ctx.state.recommended_posture = recommended_posture
        return Event("incident_package_published")

__all__ = ["IncidentToHardeningProgram"]
