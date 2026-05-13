"""Workflow-local output contracts for the investigation evidence-pack building block."""

from __future__ import annotations

from pydantic import BaseModel, Field

from botpipe import AWAIT_INPUT, FAIL, Route, SELF


class InvestigationFramingPayload(BaseModel):
    """Verifier payload for the framing step."""

    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    evidence_focus: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class InvestigationEvidencePackPayload(BaseModel):
    """Verifier payload for the evidence-pack assembly step."""

    summary: str = Field(min_length=1)
    evidence_artifacts: list[str] = Field(min_length=1)
    source_count: int = Field(default=0, ge=0)
    unresolved_gaps: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    ready_for_downstream_assessment: bool = False
    replan_reason: str | None = None


_QUESTION_ROUTE = Route.to(AWAIT_INPUT, summary="Execution is awaiting user input.")
_BLOCKED_ROUTE = Route.to(
    AWAIT_INPUT,
    summary="The current investigation work item is blocked pending missing context, evidence, or approval.",
)
_FAILED_ROUTE = Route.to(
    FAIL,
    summary="The current investigation work item cannot continue because a required assumption, artifact, or validation failed.",
)


FRAME_INVESTIGATION_ROUTE_CONTRACTS = {
    "investigation_framed": Route.to(
        "assemble_evidence_pack",
        summary="The investigation boundary, objectives, and evidence intake plan are explicit and authoritative.",
        required_writes=("investigation_scope_brief", "investigation_objectives", "evidence_intake_register"),
        handoff="Locks the investigation framing so evidence assembly can proceed against a fixed boundary.",
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same investigation framing boundary holds, but the scope brief or objectives need local repair.",
        required_writes=("investigation_scope_brief", "investigation_objectives", "evidence_intake_register"),
        handoff="Keeps the investigation framing boundary intact and reruns the same step for local correction.",
    ),
    "needs_replan": Route.to(
        "frame_investigation",
        summary="The investigation trigger, downstream consumer, or evidence surface changed materially and must be reframed.",
        handoff="Resets the investigation framing boundary before downstream evidence work continues.",
    ),
    "question": _QUESTION_ROUTE,
    "blocked": _BLOCKED_ROUTE,
    "failed": _FAILED_ROUTE,
}

ASSEMBLE_EVIDENCE_PACK_ROUTE_CONTRACTS = {
    "evidence_pack_ready": Route.to(
        "publish_evidence_pack",
        summary="The evidence pack captures inspected sources, coverage, findings, unresolved gaps, and a machine-readable summary.",
        required_writes=(
            "evidence_source_inventory",
            "evidence_coverage_matrix",
            "evidence_findings",
            "evidence_gap_register",
            "evidence_pack",
            "evidence_pack_summary",
        ),
    ),
    "needs_rework": Route.to(
        SELF,
        summary="The same evidence-pack boundary holds, but source tracing, coverage, or gap handling needs local repair.",
        required_writes=(
            "evidence_source_inventory",
            "evidence_findings",
            "evidence_gap_register",
            "evidence_pack_summary",
        ),
        handoff="Keeps evidence assembly local and reruns the same step for tighter source tracing and packaging.",
    ),
    "needs_replan": Route.to(
        "frame_investigation",
        summary="The investigation boundary or evidence plan changed materially enough that framing must be revisited.",
        handoff="Routes back to investigation framing because the evidence contract is no longer authoritative.",
    ),
    "question": _QUESTION_ROUTE,
    "blocked": _BLOCKED_ROUTE,
    "failed": _FAILED_ROUTE,
}


__all__ = [
    "ASSEMBLE_EVIDENCE_PACK_ROUTE_CONTRACTS",
    "FRAME_INVESTIGATION_ROUTE_CONTRACTS",
    "InvestigationEvidencePackPayload",
    "InvestigationFramingPayload",
]
