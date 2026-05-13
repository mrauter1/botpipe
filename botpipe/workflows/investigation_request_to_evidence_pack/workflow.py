"""Investigation evidence-pack building-block workflow package."""

from __future__ import annotations

from pydantic import BaseModel, Field

from botpipe.stdlib import (
    read_json_object,
    require_non_empty_string,
    require_non_negative_int,
    require_string_list,
)
from botpipe.stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from botpipe import Event, FAIL, FINISH, Outcome, Prompt, Session, Workflow, produce_verify_step, python_step
from botpipe.core import Artifact

from .contracts import (
    ASSEMBLE_EVIDENCE_PACK_ROUTE_CONTRACTS,
    FRAME_INVESTIGATION_ROUTE_CONTRACTS,
    InvestigationEvidencePackPayload,
    InvestigationFramingPayload,
)


def _after_frame_investigation(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    ctx.state.framing_status = outcome.tag
    return None


def _after_assemble_evidence_pack(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    ready = outcome.payload.get("ready_for_downstream_assessment")
    ctx.state.evidence_status = outcome.tag
    if isinstance(ready, bool):
        ctx.state.ready_for_downstream_assessment = ready
    return None

class InvestigationRequestToEvidencePack(Workflow):
    """Turn an investigation request into a durable evidence pack."""

    name = "investigation_request_to_evidence_pack"

    class State(BaseModel):
        investigation_title: str = ""
        investigation_kind: str = "general"
        sponsor_role: str | None = None
        evidence_paths: list[str] = Field(default_factory=list)
        source_constraints: list[str] = Field(default_factory=list)
        framing_status: str | None = None
        evidence_status: str | None = None
        ready_for_downstream_assessment: bool = False
        published: bool = False

    frame_session = Session()
    evidence_session = Session()

    request = Artifact("{{ run.folder }}/request.md")
    framework_architecture_doc = Artifact("{{ root }}/docs/architecture.md")
    framework_authoring_doc = Artifact("{{ root }}/docs/authoring.md")
    workflow_instructions = Artifact("{{ root }}/Workflow_Instructions.md")
    evidence_pack_checklist = Artifact("{{ package.folder }}/assets/evidence_pack_checklist.md")

    invocation_contract = Artifact("{{ workflow.folder }}/invocation_contract.json")
    investigation_scope_brief = Artifact("{{ workflow.folder }}/investigation_scope_brief.md")
    investigation_objectives = Artifact("{{ workflow.folder }}/investigation_objectives.md")
    evidence_intake_register = Artifact("{{ workflow.folder }}/evidence_intake_register.md")
    evidence_source_inventory = Artifact("{{ workflow.folder }}/evidence_source_inventory.md")
    evidence_coverage_matrix = Artifact("{{ workflow.folder }}/evidence_coverage_matrix.md")
    evidence_findings = Artifact("{{ workflow.folder }}/evidence_findings.md")
    evidence_gap_register = Artifact("{{ workflow.folder }}/evidence_gap_register.md")
    evidence_pack = Artifact("{{ workflow.folder }}/evidence_pack.md")
    evidence_pack_summary = Artifact("{{ workflow.folder }}/evidence_pack_summary.json")
    evidence_pack_receipt = Artifact("{{ workflow.folder }}/evidence_pack_receipt.json")

    @python_step(
        name="bootstrap",
        requires=[request],
        writes=[invocation_contract],
        routes={"inputs_prepared": "frame_investigation"},
    )
    def bootstrap(ctx):
        params = ctx.params
        next_state = ctx.state.model_copy(
            update={
                "investigation_title": params.investigation_title,
                "investigation_kind": params.investigation_kind,
                "sponsor_role": params.sponsor_role,
                "evidence_paths": list(params.evidence_paths),
                "source_constraints": list(params.source_constraints),
                "framing_status": None,
                "evidence_status": None,
                "ready_for_downstream_assessment": False,
                "published": False,
            }
        )
        open_workflow_sessions(ctx, "frame_session", "evidence_session")
        write_invocation_contract(
            ctx,
            {
                "investigation_title": next_state.investigation_title,
                "investigation_kind": next_state.investigation_kind,
                "sponsor_role": next_state.sponsor_role,
                "evidence_paths": next_state.evidence_paths,
                "source_constraints": next_state.source_constraints,
            },
        )
        ctx.state = next_state
        return "inputs_prepared"

    frame_investigation = produce_verify_step(
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
            investigation_scope_brief,
            investigation_objectives,
            evidence_intake_register,
        ],
        control_schema=InvestigationFramingPayload,
        routes=FRAME_INVESTIGATION_ROUTE_CONTRACTS,
        after_verifier=_after_frame_investigation,
    )

    assemble_evidence_pack = produce_verify_step(
        producer_prompt=Prompt.file("prompts/evidence_producer.md"),
        verifier_prompt=Prompt.file("prompts/evidence_verifier.md"),
        session=evidence_session,
        requires=[
            request,
            invocation_contract,
            investigation_scope_brief,
            investigation_objectives,
            evidence_intake_register,
            evidence_pack_checklist,
        ],
        producer_writes=[
            evidence_source_inventory,
            evidence_coverage_matrix,
            evidence_findings,
            evidence_gap_register,
            evidence_pack,
            evidence_pack_summary,
        ],
        control_schema=InvestigationEvidencePackPayload,
        routes=ASSEMBLE_EVIDENCE_PACK_ROUTE_CONTRACTS,
        after_verifier=_after_assemble_evidence_pack,
    )

    @python_step(
        name="publish_evidence_pack",
        requires=[
            investigation_scope_brief,
            investigation_objectives,
            evidence_intake_register,
            evidence_source_inventory,
            evidence_coverage_matrix,
            evidence_findings,
            evidence_gap_register,
            evidence_pack,
            evidence_pack_summary,
        ],
        writes=[evidence_pack_receipt],
        routes={"evidence_pack_published": FINISH},
    )
    def publish_evidence_pack(ctx):
        workflow_folder = ctx.workflow_folder
        required_paths = {
            "investigation_scope_brief": workflow_folder / "investigation_scope_brief.md",
            "investigation_objectives": workflow_folder / "investigation_objectives.md",
            "evidence_intake_register": workflow_folder / "evidence_intake_register.md",
            "evidence_source_inventory": workflow_folder / "evidence_source_inventory.md",
            "evidence_coverage_matrix": workflow_folder / "evidence_coverage_matrix.md",
            "evidence_findings": workflow_folder / "evidence_findings.md",
            "evidence_gap_register": workflow_folder / "evidence_gap_register.md",
            "evidence_pack": workflow_folder / "evidence_pack.md",
            "evidence_pack_summary": workflow_folder / "evidence_pack_summary.json",
        }
        for artifact_path in required_paths.values():
            if not artifact_path.exists():
                raise FileNotFoundError(f"missing required publication artifact at {artifact_path}")

        summary = read_json_object(required_paths["evidence_pack_summary"])
        summary_kind = require_non_empty_string(
            summary.get("investigation_kind"),
            error_message="evidence_pack_summary.json must define a non-empty investigation_kind",
            coerce=True,
        )
        if summary_kind != ctx.state.investigation_kind:
            raise ValueError("evidence_pack_summary.json investigation_kind must match workflow state")

        authoritative_artifacts = require_string_list(
            summary.get("authoritative_artifacts"),
            "evidence_pack_summary.json must define non-empty authoritative_artifacts",
        )
        ready_for_downstream_assessment = summary.get("ready_for_downstream_assessment")
        if not isinstance(ready_for_downstream_assessment, bool):
            raise ValueError("evidence_pack_summary.json must define boolean ready_for_downstream_assessment")
        source_count = require_non_negative_int(
            summary.get("source_count"),
            "evidence_pack_summary.json must define non-negative source_count",
        )
        finding_count = require_non_negative_int(
            summary.get("finding_count"),
            "evidence_pack_summary.json must define non-negative finding_count",
        )
        unresolved_gap_count = require_non_negative_int(
            summary.get("unresolved_gap_count"),
            "evidence_pack_summary.json must define non-negative unresolved_gap_count",
        )
        key_findings = require_string_list(
            summary.get("key_findings"),
            "evidence_pack_summary.json must define non-empty key_findings",
        )

        write_publication_receipt(
            ctx,
            "evidence_pack_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "investigation_title": ctx.state.investigation_title,
                "investigation_kind": ctx.state.investigation_kind,
                "sponsor_role": ctx.state.sponsor_role,
                "evidence_paths": ctx.state.evidence_paths,
                "source_constraints": ctx.state.source_constraints,
                "ready_for_downstream_assessment": ready_for_downstream_assessment,
                "source_count": source_count,
                "finding_count": finding_count,
                "unresolved_gap_count": unresolved_gap_count,
                "key_findings": key_findings,
                "authoritative_artifacts": authoritative_artifacts,
                **{name: str(path) for name, path in required_paths.items()},
                "published": True,
            },
        )
        ctx.state.ready_for_downstream_assessment = ready_for_downstream_assessment
        ctx.state.published = True
        return Event("evidence_pack_published")



__all__ = ["InvestigationRequestToEvidencePack"]
