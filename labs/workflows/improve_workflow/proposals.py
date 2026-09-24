"""Bounded, evidence-backed recommendation for ``improve_workflow``."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from botpipe import Prompt, Provider, activity, current_run
from botpipe_optimizer.evidence import EvidenceSnapshot
from botpipe_optimizer.optimization import SourceManifest
from botpipe_optimizer.records import (
    CandidateReview,
    CandidateSet,
    PublicationReceipt,
    ValidationPlan,
)

from .models import ChangeReview, ImproveWorkflowParams, Recommendation


@dataclass(frozen=True, slots=True)
class _SourceCapture:
    """Typed source facts restored from the activity journal on replay."""

    manifest: SourceManifest
    provenance: dict[str, Any]
    baseline_manifest: dict[str, Any]


class ChangeIdea(BaseModel):
    """Provider-owned semantics for one change; runtime owns record identity."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    targets: list[str] = Field(min_length=1)
    cited_observation_ids: list[str] = Field(min_length=1)
    proposed_change: str = Field(min_length=1)
    expected_effect: str = Field(min_length=1)
    risks: list[str] = Field(min_length=1)
    validation_plan: ValidationPlan


class Proposal(BaseModel):
    """Small provider result converted deterministically into a CandidateSet."""

    model_config = ConfigDict(extra="forbid")

    candidate: ChangeIdea | None
    next_action: Literal["implement_candidate", "collect_evidence", "no_change"]
    reason: str | None = None

    @model_validator(mode="after")
    def coherent_action(self):
        if self.candidate is not None:
            if self.next_action != "implement_candidate" or self.reason is not None:
                raise ValueError(
                    "a change idea requires implement_candidate and no reason"
                )
        elif self.next_action == "implement_candidate" or not (
            self.reason and self.reason.strip()
        ):
            raise ValueError(
                "an empty proposal requires collect_evidence/no_change and a reason"
            )
        return self


@activity(retry_safe=True, name="capture improvement source")
def _capture_source(selected_workflow: str) -> _SourceCapture:
    from botpipe.discovery import resolve_workflow
    from botpipe.provenance import (
        capture_workflow_provenance,
        capture_workflow_surface_manifest,
    )
    from botpipe_optimizer import capture_source_manifest

    context = current_run()
    selected = resolve_workflow(selected_workflow, context.workspace)
    manifest = capture_source_manifest(selected)
    provenance = capture_workflow_provenance(selected, context.workspace)
    if not provenance["verified"]:
        raise ValueError(
            "Cannot capture an attributable optimizer baseline: "
            + provenance["error"]
        )
    baseline_manifest = capture_workflow_surface_manifest(selected, context.workspace)
    if baseline_manifest["surface_id"] != provenance["surface_id"]:
        raise ValueError("workflow surface changed during optimizer baseline capture")
    return _SourceCapture(
        manifest=manifest,
        provenance=provenance,
        baseline_manifest=baseline_manifest,
    )


@activity(retry_safe=True, name="capture improvement history")
def _capture_history(
    canonical_workflow_name: str,
    run_refs: tuple[str, ...],
    history_limit: int,
) -> tuple[dict[str, Any], ...]:
    """Read exact requested runs or bounded recent runs that are not executing."""

    context = current_run()
    if run_refs:
        inspected = []
        for reference in run_refs:
            task_id, separator, run_id = reference.rpartition("/")
            if not separator:
                run_id = reference
            details = context.client.inspect(run_id)
            recorded_task = details.get("run", {}).get("task_id")
            if separator and str(recorded_task) != task_id:
                raise ValueError(
                    f"run reference task does not match journal: {reference}"
                )
            inspected.append(details)
        return tuple(inspected)

    matching = []
    for summary in context.client.runs():
        record = summary if isinstance(summary, dict) else vars(summary)
        if (
            record.get("workflow_name") or record.get("workflow")
        ) != canonical_workflow_name:
            continue
        details = context.client.inspect(str(record["run_id"]))
        # Use the snapshot: a listed historical run may have since resumed.
        if details["run"].get("status") in {"created", "running"}:
            continue
        matching.append(details)
        if len(matching) >= history_limit:
            break
    return tuple(matching)


@activity(retry_safe=True, name="capture bounded improvement evidence")
def _capture_evidence(
    source: _SourceCapture,
    inspections: tuple[dict[str, Any], ...],
    objective: str,
    max_evidence_bytes: int,
    max_snapshot_bytes: int,
    explicit_run_refs: bool,
) -> EvidenceSnapshot:
    from botpipe_optimizer.evidence import capture_evidence_snapshot

    provenance = source.provenance
    return capture_evidence_snapshot(
        source.manifest.workflow_name,
        inspections,
        source_manifest=source.manifest,
        objective=objective,
        top_k_steps=1,
        max_evidence_bytes=max_evidence_bytes,
        max_snapshot_bytes=max_snapshot_bytes,
        explicit_run_refs=explicit_run_refs,
        current_workflow_identity=provenance.get("workflow_identity"),
        current_surface_id=provenance.get("surface_id"),
        current_orchestration_id=provenance.get("orchestration_id"),
        baseline_surface_manifest_id=provenance.get("surface_id"),
    )


@activity(retry_safe=True, name="publish improvement recommendation")
def _publish(
    output_dir: str,
    evidence_snapshot: EvidenceSnapshot,
    candidate_set: CandidateSet,
    review: CandidateReview | None,
    baseline_manifest: dict[str, Any],
    max_output_bytes: int,
    max_evidence_bytes: int,
    max_snapshot_bytes: int,
) -> PublicationReceipt:
    from botpipe_optimizer.recommendations import publish_recommendation

    return publish_recommendation(
        output_dir=output_dir,
        evidence_snapshot=evidence_snapshot,
        candidate_set=candidate_set,
        review=review,
        baseline_manifest=baseline_manifest,
        max_output_bytes=max_output_bytes,
        max_evidence_bytes=max_evidence_bytes,
        max_snapshot_bytes=max_snapshot_bytes,
    )


def _empty_candidate_set(
    source: _SourceCapture, snapshot: EvidenceSnapshot
) -> CandidateSet:
    from botpipe_optimizer.recommendations import build_empty_candidate_set

    if snapshot.next_action == "no_change":
        reason = "The admitted evidence contains no objective-eligible change signal."
    else:
        reason = "No objective-eligible evidence was available in the admitted sample."
    return build_empty_candidate_set(
        selected_workflow=source.manifest.workflow_name,
        evidence_snapshot_id=snapshot.snapshot_id,
        baseline_surface_manifest_id=snapshot.baseline_surface_manifest_id,
        next_action=(
            "no_change" if snapshot.next_action == "no_change" else "collect_evidence"
        ),
        reason=reason,
    )


def _finalize_candidate_set(
    proposal: Proposal,
    *,
    selected_workflow: str,
    snapshot: EvidenceSnapshot,
) -> CandidateSet:
    from botpipe_optimizer.recommendations import finalize_candidate_set_payload

    candidates: list[dict[str, Any]] = []
    if proposal.candidate is not None:
        idea = proposal.candidate
        candidates.append(
            {
                "kind": "workflow",
                "title": idea.title,
                "targets": idea.targets,
                "cited_observation_ids": idea.cited_observation_ids,
                "proposed_change": idea.proposed_change,
                "expected_effect": idea.expected_effect,
                "risks": idea.risks,
                "validation_plan": idea.validation_plan.model_dump(mode="json"),
                "payload": {
                    "target_paths": idea.targets,
                    "workflow_change": idea.proposed_change,
                },
            }
        )
    return finalize_candidate_set_payload(
        {
            "schema": "botpipe.workflow_optimization.candidate_set/v2",
            "selected_workflow": selected_workflow,
            "evidence_snapshot_id": snapshot.snapshot_id,
            "baseline_surface_manifest_id": snapshot.baseline_surface_manifest_id,
            "candidates": candidates,
            "next_action": proposal.next_action,
            "no_candidate_reason": proposal.reason,
        }
    )


def _finalize_review(
    change_review: ChangeReview, candidate_set: CandidateSet
) -> CandidateReview:
    from botpipe_optimizer.recommendations import finalize_candidate_review_payload

    required_changes = change_review.required_changes
    if any(not item.strip() for item in required_changes) or len(
        required_changes
    ) != len(set(required_changes)):
        raise ValueError("review required_changes must be non-empty and unique")
    candidate_ids = [item.candidate_id for item in candidate_set.candidates]
    accepted = change_review.accepted and not required_changes
    findings = []
    if candidate_ids and not accepted:
        messages = required_changes or [change_review.summary]
        findings = [
            {
                "candidate_id": candidate_ids[0],
                "severity": "error",
                "message": message,
            }
            for message in messages
        ]
    return finalize_candidate_review_payload(
        {
            "schema": "botpipe.workflow_optimization.candidate_review/v2",
            "candidate_set_id": candidate_set.candidate_set_id,
            "evidence_snapshot_id": candidate_set.evidence_snapshot_id,
            "baseline_surface_manifest_id": (
                candidate_set.baseline_surface_manifest_id
            ),
            "accepted": accepted,
            "reviewed_candidate_ids": candidate_ids,
            "findings": findings,
        }
    )


def propose_improvement(params: ImproveWorkflowParams, request: str) -> Recommendation:
    """Return one reviewed proposal, or a bounded evidence/no-change result.

    The caller owns the enclosing workflow and provider budget. A rejected final
    proposal remains inspectable but is deliberately not published as accepted.
    """

    from botpipe_optimizer.recommendations import (
        validate_candidate_review,
        validate_candidate_set,
    )

    context = current_run()
    source = _capture_source(params.selected_workflow)
    inspections = _capture_history(
        source.manifest.workflow_name,
        tuple(params.run_refs),
        params.history_limit,
    )
    snapshot = _capture_evidence(
        source,
        inspections,
        params.objective,
        params.max_evidence_bytes,
        params.max_snapshot_bytes,
        bool(params.run_refs),
    )

    if snapshot.next_action != "propose_changes" or not snapshot.shortlist:
        candidate_set = _empty_candidate_set(source, snapshot)
        receipt = _publish(
            str(context.folder),
            snapshot,
            candidate_set,
            None,
            source.baseline_manifest,
            params.max_output_bytes,
            params.max_evidence_bytes,
            params.max_snapshot_bytes,
        )
        return Recommendation(
            evidence_snapshot=snapshot,
            candidate_set=candidate_set,
            review=None,
            receipt=receipt,
        )

    producer = Provider()
    reviewer = producer.with_config(session=None)
    review: CandidateReview | None = None
    candidate_set: CandidateSet | None = None
    feedback: dict[str, Any] | None = None

    for revision in range(params.max_revisions + 1):
        proposal = producer.query(
            Prompt.file("prompts/propose.md"),
            input={
                "request": request,
                "selected_workflow_reference": params.selected_workflow,
                "objective": params.objective,
                "evidence_snapshot": snapshot.model_dump(mode="json"),
                "selected_workflow_source_manifest": asdict(source.manifest),
                "baseline_surface_manifest": source.baseline_manifest,
                "max_candidates": 1,
                "max_output_bytes": params.max_output_bytes,
                "revision": revision,
                "max_revisions": params.max_revisions,
                "review_feedback": feedback,
            },
            returns=Proposal,
        )
        candidate_set = _finalize_candidate_set(
            proposal.value,
            selected_workflow=source.manifest.workflow_name,
            snapshot=snapshot,
        )
        candidate_set = validate_candidate_set(
            candidate_set,
            evidence_snapshot=snapshot,
            max_candidates=1,
            allowed_kinds=("workflow",),
            expected_selected_workflow=source.manifest.workflow_name,
            max_output_bytes=params.max_output_bytes,
        )
        decision = reviewer.query(
            Prompt.file("prompts/review_proposal.md"),
            input={
                "request": request,
                "objective": params.objective,
                "evidence_snapshot": snapshot.model_dump(mode="json"),
                "candidate_set": candidate_set.model_dump(mode="json", by_alias=True),
                "selected_workflow_source_manifest": asdict(source.manifest),
                "baseline_surface_manifest": source.baseline_manifest,
                "max_candidates": 1,
                "max_output_bytes": params.max_output_bytes,
            },
            returns=ChangeReview,
        )
        review = _finalize_review(decision.value, candidate_set)
        review = validate_candidate_review(
            review,
            candidate_set=candidate_set,
            max_output_bytes=params.max_output_bytes,
        )
        if review.accepted:
            receipt = _publish(
                str(context.folder),
                snapshot,
                candidate_set,
                review,
                source.baseline_manifest,
                params.max_output_bytes,
                params.max_evidence_bytes,
                params.max_snapshot_bytes,
            )
            return Recommendation(
                evidence_snapshot=snapshot,
                candidate_set=candidate_set,
                review=review,
                receipt=receipt,
            )
        feedback = decision.value.model_dump(mode="json")

    assert candidate_set is not None and review is not None
    return Recommendation(
        evidence_snapshot=snapshot,
        candidate_set=candidate_set,
        review=review,
        receipt=None,
    )


__all__ = ["propose_improvement"]
