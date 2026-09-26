"""Bounded, evidence-backed recommendation for ``improve_workflow``."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
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

from .models import (
    ChangeReview,
    DiagnosticAssessment,
    ImproveWorkflowParams,
    Recommendation,
)


@dataclass(frozen=True, slots=True)
class _SourceCapture:
    """Typed source facts restored from the activity journal on replay."""

    manifest: SourceManifest
    provenance: dict[str, Any]
    baseline_manifest: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _FrozenAnalysisSource:
    root: str
    managed_root: str
    marker_sha256: str
    hashes: dict[str, str]


class ChangeIdea(BaseModel):
    """Provider-owned semantics for one change; runtime owns record identity."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    targets: list[str] = Field(min_length=1)
    cited_observation_ids: list[str] = Field(default_factory=list)
    source_evidence_paths: list[str] = Field(default_factory=list)
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
            "Cannot capture an attributable optimizer baseline: " + provenance["error"]
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


@activity(retry_safe=True, name="freeze improvement analysis source")
def _freeze_analysis_source(
    source: _SourceCapture, destination: str
) -> _FrozenAnalysisSource:
    """Copy the exact captured surface used by all model analysis turns."""

    from botpipe_optimizer import prepare_candidate_workspace

    manifest = source.baseline_manifest
    files = manifest.get("files", ())
    relative_paths = tuple(
        str(item["relative_path"])
        for item in files
        if isinstance(item, dict) and item.get("relative_path")
    )
    if not relative_paths:
        raise ValueError("captured workflow surface has no analysis source files")
    prepared = prepare_candidate_workspace(
        manifest["root"], relative_paths, destination
    )
    expected = {
        str(item["relative_path"]): str(item["surface_sha256"]) for item in files
    }
    actual = {
        relative: sha256((prepared.baseline_root / relative).read_bytes()).hexdigest()
        for relative in relative_paths
    }
    if actual != expected:
        raise ValueError("workflow source changed while freezing analysis baseline")
    for relative in relative_paths:
        os.chmod(prepared.baseline_root / relative, 0o444)
    return _FrozenAnalysisSource(
        root=str(prepared.baseline_root),
        managed_root=str(prepared.root),
        marker_sha256=sha256(
            (prepared.root / ".botpipe-candidate.json").read_bytes()
        ).hexdigest(),
        hashes=actual,
    )


def _verify_analysis_source(frozen: _FrozenAnalysisSource) -> None:
    raw_root = Path(frozen.root)
    raw_managed = Path(frozen.managed_root)
    if raw_managed.is_symlink() or raw_root.is_symlink():
        raise ValueError("frozen workflow analysis paths must not be symlinks")
    if raw_root.parent != raw_managed:
        raise ValueError("frozen workflow analysis root has an invalid owner")
    marker = raw_managed / ".botpipe-candidate.json"
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("frozen workflow analysis ownership marker is invalid")
    if sha256(marker.read_bytes()).hexdigest() != frozen.marker_sha256:
        raise ValueError("frozen workflow analysis ownership marker changed")
    managed = raw_managed.resolve(strict=True)
    root = raw_root.resolve(strict=True)
    if root != managed / "baseline":
        raise ValueError("frozen workflow analysis root escaped its managed directory")
    entries = tuple(root.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ValueError("frozen workflow analysis source contains a symlink")
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in entries
        if path.is_file() and not path.is_symlink()
    }
    if actual_paths != set(frozen.hashes):
        raise ValueError("frozen workflow analysis source file set changed")
    actual = {
        relative: sha256(_ordinary_frozen_file(root, relative).read_bytes()).hexdigest()
        for relative in frozen.hashes
    }
    if actual != frozen.hashes:
        raise ValueError("frozen workflow analysis source changed")


def _ordinary_frozen_file(root: Path, relative: str) -> Path:
    path = root / relative
    if path.is_symlink():
        raise ValueError("frozen workflow analysis source contains a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or not resolved.is_relative_to(root):
        raise ValueError("frozen workflow analysis source escaped its root")
    return resolved


def _model_baseline_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Expose exact relative identities without authoritative absolute paths."""

    value = json.loads(json.dumps(manifest))
    value["root"] = "."
    value["surface_root"] = "."
    for item in value.get("files", ()):
        if isinstance(item, dict):
            item.pop("surface_path", None)
    return value


def _model_source_manifest(
    manifest: SourceManifest, baseline_manifest: dict[str, Any]
) -> dict[str, Any]:
    value = asdict(manifest)
    original = manifest.source_path
    value["source_path"] = next(
        (
            str(item["relative_path"])
            for item in baseline_manifest.get("files", ())
            if isinstance(item, dict)
            and original
            and item.get("surface_path")
            and Path(str(item["surface_path"])).resolve() == Path(original).resolve()
        ),
        None,
    )
    return value


@activity(retry_safe=True, name="capture bounded improvement evidence")
def _capture_evidence(
    source: _SourceCapture,
    inspections: tuple[dict[str, Any], ...],
    metric_view: str | None,
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
        # Evidence v3 requires a concrete legacy view. It remains descriptive
        # and is removed from active model input when the user did not request it.
        objective=metric_view or "reliability",
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
    assessment: DiagnosticAssessment,
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
        supporting_content=(
            "# Diagnostic assessment\n\n```json\n"
            + json.dumps(assessment.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n```\n"
        ).encode(),
    )


def _finalize_candidate_set(
    proposal: Proposal,
    *,
    selected_workflow: str,
    snapshot: EvidenceSnapshot,
    assessment: DiagnosticAssessment,
) -> CandidateSet:
    from botpipe_optimizer.recommendations import finalize_candidate_set_payload

    candidates: list[dict[str, Any]] = []
    if proposal.candidate is not None:
        idea = proposal.candidate
        assessed_sources = {
            path for link in assessment.intent_evidence for path in link.source_paths
        }
        for scoped in assessment.scope_assessments:
            assessed_sources.update(
                path for link in scoped.evidence for path in link.source_paths
            )
        unknown_sources = sorted(set(idea.source_evidence_paths) - assessed_sources)
        if unknown_sources:
            raise ValueError(
                "candidate source evidence was not established by assessment: "
                + ", ".join(unknown_sources)
            )
        if not idea.cited_observation_ids and not idea.source_evidence_paths:
            raise ValueError("source-only candidate must name assessed source evidence")
        unsupported_targets = sorted(
            set(idea.targets) - set(idea.source_evidence_paths)
            if not idea.cited_observation_ids
            else ()
        )
        if unsupported_targets:
            raise ValueError(
                "source-only candidate targets lack assessed source evidence: "
                + ", ".join(unsupported_targets)
            )
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


def _neutral_evidence(snapshot: EvidenceSnapshot) -> dict[str, Any]:
    """Return model evidence without a preselected target or action."""

    return {
        "schema": snapshot.schema_version,
        "snapshot_id": snapshot.snapshot_id,
        "selected_workflow": snapshot.selected_workflow,
        "baseline_surface_manifest_id": snapshot.baseline_surface_manifest_id,
        "selection": snapshot.selection.model_dump(mode="json"),
        "runs": [item.model_dump(mode="json") for item in snapshot.runs],
        "excluded_runs": [
            item.model_dump(mode="json") for item in snapshot.excluded_runs
        ],
        "issues": [item.model_dump(mode="json") for item in snapshot.issues],
        "observations": [
            item.model_dump(mode="json") for item in snapshot.observations
        ],
        "groups": [item.model_dump(mode="json") for item in snapshot.groups],
        "selected_group_id": snapshot.selected_group_id,
        "recommendation_basis": snapshot.recommendation_basis,
        # These are neutral aggregates.  The deterministic objective shortlist,
        # ranking basis, and next action are intentionally not model inputs.
        "descriptive_step_metrics": [
            item.model_dump(mode="json") for item in snapshot.step_metrics
        ],
        "budget": snapshot.budget.model_dump(mode="json"),
    }


def _validate_assessment(
    assessment: DiagnosticAssessment,
    *,
    snapshot: EvidenceSnapshot,
    baseline_manifest: dict[str, Any],
) -> DiagnosticAssessment:
    observations = {item.observation_id for item in snapshot.observations}
    raw_files = baseline_manifest.get("files", ())
    source_paths = {
        str(item["relative_path"])
        for item in raw_files
        if isinstance(item, dict) and item.get("relative_path")
    }
    links = list(assessment.intent_evidence)
    for scoped in assessment.scope_assessments:
        links.extend(scoped.evidence)
    for link in links:
        unknown_observations = sorted(set(link.observation_ids) - observations)
        if unknown_observations:
            raise ValueError(
                "assessment cites unknown observations: "
                + ", ".join(unknown_observations)
            )
        unknown_paths = sorted(set(link.source_paths) - source_paths)
        if unknown_paths:
            raise ValueError(
                "assessment cites source outside captured baseline: "
                + ", ".join(unknown_paths)
            )
    return assessment


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
        params.metric_view,
        params.max_evidence_bytes,
        params.max_snapshot_bytes,
        bool(params.run_refs),
    )
    frozen_source = _freeze_analysis_source(
        source, str(context.folder / "analysis-source")
    )
    model_manifest = _model_baseline_manifest(source.baseline_manifest)
    model_source_manifest = _model_source_manifest(
        source.manifest, source.baseline_manifest
    )
    _verify_analysis_source(frozen_source)
    investigator = Provider(workspace=frozen_source.root)
    assessment = investigator.query(
        Prompt.file("prompts/investigate.md"),
        input={
            "request": request,
            "selected_workflow_reference": source.manifest.workflow_name,
            "analysis_source_root": frozen_source.root,
            "priority": params.objective,
            "evidence": _neutral_evidence(snapshot),
            "selected_workflow_source_manifest": model_source_manifest,
            "baseline_surface_manifest": model_manifest,
        },
        returns=DiagnosticAssessment,
    ).value
    assessment = _validate_assessment(
        assessment,
        snapshot=snapshot,
        baseline_manifest=source.baseline_manifest,
    )
    _verify_analysis_source(frozen_source)

    producer = investigator.with_config(session=None)
    reviewer = producer.with_config(session=None)
    review: CandidateReview | None = None
    candidate_set: CandidateSet | None = None
    feedback: dict[str, Any] | None = None

    for revision in range(params.max_revisions + 1):
        proposal = producer.query(
            Prompt.file("prompts/propose.md"),
            input={
                "request": request,
                "selected_workflow_reference": source.manifest.workflow_name,
                "analysis_source_root": frozen_source.root,
                "priority": params.objective,
                "evidence": _neutral_evidence(snapshot),
                "assessment": assessment.model_dump(mode="json"),
                "selected_workflow_source_manifest": model_source_manifest,
                "baseline_surface_manifest": model_manifest,
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
            assessment=assessment,
        )
        candidate_set = validate_candidate_set(
            candidate_set,
            evidence_snapshot=snapshot,
            max_candidates=1,
            allowed_kinds=("workflow",),
            expected_selected_workflow=source.manifest.workflow_name,
            max_output_bytes=params.max_output_bytes,
            baseline_manifest=source.baseline_manifest,
        )
        _verify_analysis_source(frozen_source)
        decision = reviewer.query(
            Prompt.file("prompts/review_proposal.md"),
            input={
                "request": request,
                "priority": params.objective,
                "analysis_source_root": frozen_source.root,
                "evidence": _neutral_evidence(snapshot),
                "assessment": assessment.model_dump(mode="json"),
                "candidate_set": candidate_set.model_dump(mode="json", by_alias=True),
                "selected_workflow_source_manifest": model_source_manifest,
                "baseline_surface_manifest": model_manifest,
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
        _verify_analysis_source(frozen_source)
        if review.accepted:
            receipt = _publish(
                str(context.folder),
                snapshot,
                assessment,
                candidate_set,
                review,
                source.baseline_manifest,
                params.max_output_bytes,
                params.max_evidence_bytes,
                params.max_snapshot_bytes,
            )
            return Recommendation(
                evidence_snapshot=snapshot,
                assessment=assessment,
                candidate_set=candidate_set,
                review=review,
                receipt=receipt,
            )
        feedback = decision.value.model_dump(mode="json")

    assert candidate_set is not None and review is not None
    return Recommendation(
        evidence_snapshot=snapshot,
        assessment=assessment,
        candidate_set=candidate_set,
        review=review,
        receipt=None,
    )


__all__ = ["propose_improvement"]
