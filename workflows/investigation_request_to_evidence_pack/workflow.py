"""Investigation evidence-pack building-block workflow package."""

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
    ASSEMBLE_EVIDENCE_PACK_ROUTE_CONTRACTS,
    FRAME_INVESTIGATION_ROUTE_CONTRACTS,
    InvestigationEvidencePackPayload,
    InvestigationFramingPayload,
)


_INVESTIGATION_KINDS = frozenset(
    {
        "release_readiness",
        "incident_response",
        "security_remediation",
        "delivery_recovery",
        "customer_escalation",
        "general",
    }
)


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

    request = Artifact("{run_folder}/request.md")
    framework_architecture_doc = Artifact("{package_folder}/../../docs/architecture.md")
    framework_authoring_doc = Artifact("{package_folder}/../../docs/authoring.md")
    workflow_instructions = Artifact("{package_folder}/../../Workflow_Instructions.md")
    evidence_pack_checklist = Artifact("{package_folder}/assets/evidence_pack_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json")
    investigation_scope_brief = Artifact("{workflow_folder}/investigation_scope_brief.md")
    investigation_objectives = Artifact("{workflow_folder}/investigation_objectives.md")
    evidence_intake_register = Artifact("{workflow_folder}/evidence_intake_register.md")
    evidence_source_inventory = Artifact("{workflow_folder}/evidence_source_inventory.md")
    evidence_coverage_matrix = Artifact("{workflow_folder}/evidence_coverage_matrix.md")
    evidence_findings = Artifact("{workflow_folder}/evidence_findings.md")
    evidence_gap_register = Artifact("{workflow_folder}/evidence_gap_register.md")
    evidence_pack = Artifact("{workflow_folder}/evidence_pack.md")
    evidence_pack_summary = Artifact("{workflow_folder}/evidence_pack_summary.json")
    evidence_pack_receipt = Artifact("{workflow_folder}/evidence_pack_receipt.json")

    bootstrap = SystemStep(
        name="bootstrap",
        requires=[request],
        produces={"invocation_contract": invocation_contract},
    )
    frame_investigation = PairStep(
        name="frame_investigation",
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
            "investigation_scope_brief": investigation_scope_brief,
            "investigation_objectives": investigation_objectives,
            "evidence_intake_register": evidence_intake_register,
        },
        expected_output_schema=InvestigationFramingPayload,
        route_contracts=FRAME_INVESTIGATION_ROUTE_CONTRACTS,
    )
    assemble_evidence_pack = PairStep(
        name="assemble_evidence_pack",
        session=evidence_session,
        producer="prompts/evidence_producer.md",
        verifier="prompts/evidence_verifier.md",
        requires=[
            request,
            invocation_contract,
            investigation_scope_brief,
            investigation_objectives,
            evidence_intake_register,
            evidence_pack_checklist,
        ],
        produces={
            "evidence_source_inventory": evidence_source_inventory,
            "evidence_coverage_matrix": evidence_coverage_matrix,
            "evidence_findings": evidence_findings,
            "evidence_gap_register": evidence_gap_register,
            "evidence_pack": evidence_pack,
            "evidence_pack_summary": evidence_pack_summary,
        },
        expected_output_schema=InvestigationEvidencePackPayload,
        route_contracts=ASSEMBLE_EVIDENCE_PACK_ROUTE_CONTRACTS,
    )
    publish_evidence_pack = SystemStep(
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
        produces={"evidence_pack_receipt": evidence_pack_receipt},
    )

    entry = bootstrap

    transitions = merge_transitions(
        global_routes(pause_on_outcome_tags("question", "blocked"), failed=FAIL),
        {
            bootstrap: {"inputs_prepared": frame_investigation},
            frame_investigation: {
                "investigation_framed": assemble_evidence_pack,
                "needs_rework": frame_investigation,
                "needs_replan": frame_investigation,
            },
            assemble_evidence_pack: {
                "evidence_pack_ready": publish_evidence_pack,
                "needs_rework": assemble_evidence_pack,
                "needs_replan": frame_investigation,
            },
            publish_evidence_pack: {"evidence_pack_published": SUCCESS},
        },
    )

    @staticmethod
    def on_bootstrap(state: State, ctx) -> tuple[State, Event]:
        payload = dict(ctx.workflow_params)
        investigation_title = _require_text(
            payload.get("investigation_title"),
            "investigation_request_to_evidence_pack requires workflow parameter 'investigation_title'",
        )
        investigation_kind = _normalize_investigation_kind(payload.get("investigation_kind"))
        sponsor_role = _normalize_optional_text(payload.get("sponsor_role"))
        evidence_paths = _normalize_unique_strings(payload.get("evidence_paths"))
        source_constraints = _normalize_unique_strings(payload.get("source_constraints"))

        next_state = state.model_copy(
            update={
                "investigation_title": investigation_title,
                "investigation_kind": investigation_kind,
                "sponsor_role": sponsor_role,
                "evidence_paths": evidence_paths,
                "source_constraints": source_constraints,
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
        return next_state, Event("inputs_prepared")

    @staticmethod
    def on_frame_investigation(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"framing_status": outcome.tag})

    @staticmethod
    def on_assemble_evidence_pack(state: State, outcome: Outcome, artifacts):
        del artifacts
        ready = outcome.payload.get("ready_for_downstream_assessment")
        return state.model_copy(
            update={
                "evidence_status": outcome.tag,
                "ready_for_downstream_assessment": (
                    ready if isinstance(ready, bool) else state.ready_for_downstream_assessment
                ),
            }
        )

    @staticmethod
    def on_publish_evidence_pack(state: State, ctx) -> tuple[State, Event]:
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

        summary = _read_json(required_paths["evidence_pack_summary"])
        summary_kind = _require_text(
            summary.get("investigation_kind"),
            "evidence_pack_summary.json must define a non-empty investigation_kind",
        )
        if summary_kind != state.investigation_kind:
            raise ValueError("evidence_pack_summary.json investigation_kind must match workflow state")

        authoritative_artifacts = _require_string_list(
            summary.get("authoritative_artifacts"),
            "evidence_pack_summary.json must define non-empty authoritative_artifacts",
        )
        ready_for_downstream_assessment = summary.get("ready_for_downstream_assessment")
        if not isinstance(ready_for_downstream_assessment, bool):
            raise ValueError("evidence_pack_summary.json must define boolean ready_for_downstream_assessment")
        source_count = _require_non_negative_int(summary, "source_count")
        finding_count = _require_non_negative_int(summary, "finding_count")
        unresolved_gap_count = _require_non_negative_int(summary, "unresolved_gap_count")
        key_findings = _normalize_string_list(summary.get("key_findings"))

        write_publication_receipt(
            ctx,
            "evidence_pack_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "investigation_title": state.investigation_title,
                "investigation_kind": state.investigation_kind,
                "sponsor_role": state.sponsor_role,
                "evidence_paths": state.evidence_paths,
                "source_constraints": state.source_constraints,
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
        return state.model_copy(
            update={
                "ready_for_downstream_assessment": ready_for_downstream_assessment,
                "published": True,
            }
        ), Event("evidence_pack_published")

    on_outcome = staticmethod(event_on_outcome_tags("question", "blocked", "failed"))


def _require_text(value, error_message: str) -> str:
    if value is None:
        raise ValueError(error_message)
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(error_message)
    return normalized


def _normalize_optional_text(value) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_unique_strings(raw_value) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        candidates = raw_value
    else:
        candidates = [raw_value]
    normalized: list[str] = []
    for value in candidates:
        candidate = str(value).strip()
        if candidate and candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _normalize_investigation_kind(value) -> str:
    normalized = _require_text(
        value,
        "investigation_request_to_evidence_pack requires workflow parameter 'investigation_kind'",
    )
    if normalized not in _INVESTIGATION_KINDS:
        supported = ", ".join(sorted(_INVESTIGATION_KINDS))
        raise ValueError(f"investigation_kind must be one of: {supported}")
    return normalized


def _read_json(path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return raw


def _require_non_negative_int(payload: dict[str, object], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"evidence_pack_summary.json must define non-negative {field_name}")
    return value


def _require_string_list(value, error_message: str) -> list[str]:
    normalized = _normalize_string_list(value)
    if not normalized:
        raise ValueError(error_message)
    return normalized


def _normalize_string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return []
        candidate = item.strip()
        if candidate:
            normalized.append(candidate)
    return normalized


__all__ = ["InvestigationRequestToEvidencePack"]
