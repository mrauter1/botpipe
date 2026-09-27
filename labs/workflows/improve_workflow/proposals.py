"""Bounded, evidence-backed recommendation for ``improve_workflow``."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from botpipe import OutputValidationError, Prompt, Provider, activity, current_run
from botpipe_optimizer.evidence import EvidenceSnapshot
from botpipe_optimizer.optimization import SourceManifest
from botpipe_optimizer.records import (
    CandidateReview,
    CandidateSet,
    ValidationPlan,
)

from .analysis_evidence import (
    AnalysisIntegrityError,
    FrozenAnalysisEvidence,
    GroundingError,
    freeze_analysis_evidence,
    validate_exact_quote,
    verify_analysis_evidence,
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
    if any(
        relative == ".analysis-evidence-bundle"
        or relative.startswith(".analysis-evidence-bundle/")
        for relative in relative_paths
    ):
        raise ValueError("captured workflow surface uses a reserved analysis path")
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
        and not path.relative_to(root).as_posix().startswith(
            ".analysis-evidence-bundle/"
        )
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
        objective=metric_view,
        top_k_steps=1,
        max_evidence_bytes=max_evidence_bytes,
        max_snapshot_bytes=max_snapshot_bytes,
        explicit_run_refs=explicit_run_refs,
        current_workflow_identity=provenance.get("workflow_identity"),
        current_surface_id=provenance.get("surface_id"),
        current_orchestration_id=provenance.get("orchestration_id"),
        baseline_surface_manifest_id=provenance.get("surface_id"),
    )


@activity(retry_safe=True, name="freeze improvement journal evidence")
def _freeze_journal_evidence(
    inspections: tuple[dict[str, Any], ...], destination: str, max_bytes: int
) -> FrozenAnalysisEvidence:
    return freeze_analysis_evidence(inspections, destination, max_bytes=max_bytes)


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
        if not idea.cited_observation_ids and not idea.source_evidence_paths:
            raise GroundingError("candidate must cite a trace or captured source file")
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


def _safe_model_path(value: str) -> bool:
    raw = Path(value)
    return bool(
        value
        and not raw.is_absolute()
        and ".." not in raw.parts
        and "\\" not in value
        and value == raw.as_posix()
    )


def _validate_proposal_grounding(
    proposal: Proposal,
    *,
    snapshot: EvidenceSnapshot,
    baseline_manifest: dict[str, Any],
) -> None:
    idea = proposal.candidate
    if idea is None:
        return
    paths = (*idea.targets, *idea.source_evidence_paths)
    unsafe = sorted({path for path in paths if not _safe_model_path(path)})
    if unsafe:
        raise AnalysisIntegrityError(
            "candidate path escapes the captured workflow boundary: "
            + ", ".join(unsafe)
        )
    allowed = {
        str(item["relative_path"])
        for item in baseline_manifest.get("files", ())
        if isinstance(item, dict) and item.get("relative_path")
    }
    unknown_paths = sorted(set(paths) - allowed)
    if unknown_paths:
        raise GroundingError(
            "candidate cites paths outside the captured baseline: "
            + ", ".join(unknown_paths)
        )
    unknown_observations = sorted(
        set(idea.cited_observation_ids) - snapshot.citable_observation_ids()
    )
    if unknown_observations:
        raise GroundingError(
            "candidate cites unavailable or unfocused observations: "
            + ", ".join(unknown_observations)
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
    frozen_source: _FrozenAnalysisSource,
    frozen_evidence: FrozenAnalysisEvidence,
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
        unsafe_sources = sorted(
            path for path in link.source_paths if not _safe_model_path(path)
        )
        if unsafe_sources:
            raise AnalysisIntegrityError(
                "assessment source path escapes the captured workflow boundary: "
                + ", ".join(unsafe_sources)
            )
        unknown_observations = sorted(set(link.observation_ids) - observations)
        if unknown_observations:
            raise GroundingError(
                "assessment cites unknown observations: "
                + ", ".join(unknown_observations)
            )
        unknown_paths = sorted(set(link.source_paths) - source_paths)
        if unknown_paths:
            raise GroundingError(
                "assessment cites source outside captured baseline: "
                + ", ".join(unknown_paths)
            )
        if link.basis == "trace":
            assert link.evidence_path is not None and link.quote is not None
            validate_exact_quote(Path(frozen_evidence.root), link.evidence_path, link.quote)
        elif link.basis == "observation" and link.evidence_path is not None:
            assert link.quote is not None
            validate_exact_quote(
                Path(frozen_evidence.root), link.evidence_path, link.quote
            )
            cited = [
                item for item in snapshot.observations
                if item.observation_id in link.observation_ids
            ]
            operation_path_identities = {
                identity
                for item in cited
                for identity in (
                    re.sub(r"[^A-Za-z0-9_.-]+", "-", item.operation_id)
                    .strip("-.")[:96],
                    sha256(item.operation_id.encode()).hexdigest(),
                )
            }
            if not any(
                identity and identity in link.evidence_path
                for identity in operation_path_identities
            ):
                raise GroundingError(
                    "observation citation path does not identify a cited operation record"
                )
        elif link.basis == "source" and link.evidence_path is not None:
            if link.evidence_path not in link.source_paths:
                raise GroundingError(
                    "source citation path must be one of the link's source_paths"
                )
            assert link.quote is not None
            validate_exact_quote(Path(frozen_source.root), link.evidence_path, link.quote)
        elif link.basis == "inference" and link.evidence_path is not None:
            raise GroundingError("inference must not carry a direct evidence citation")
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
    admitted_run_refs = {item.run_ref for item in snapshot.runs}
    admitted_inspections = tuple(
        inspection
        for inspection in inspections
        if (
            f"{inspection.get('run', {}).get('task_id')}/"
            f"{inspection.get('run', {}).get('run_id')}"
            if inspection.get("run", {}).get("task_id")
            else str(inspection.get("run", {}).get("run_id"))
        )
        in admitted_run_refs
    )
    frozen_evidence = _freeze_journal_evidence(
        admitted_inspections,
        str(Path(frozen_source.root) / ".analysis-evidence-bundle"),
        params.max_evidence_bytes,
    )
    model_manifest = _model_baseline_manifest(source.baseline_manifest)
    model_source_manifest = _model_source_manifest(
        source.manifest, source.baseline_manifest
    )
    def verify_frozen_analysis() -> None:
        _verify_analysis_source(frozen_source)
        verify_analysis_evidence(frozen_evidence)

    verify_frozen_analysis()
    investigator = Provider(workspace=frozen_source.root)
    assessment: DiagnosticAssessment | None = None
    frozen_trial_plan: dict[str, Any] | None = None
    grounding_feedback: str | None = None
    for grounding_attempt in range(params.max_grounding_repairs + 1):
        try:
            result = investigator.with_config(session=None).query(
                Prompt.file("prompts/assess.md"),
                input={
                    "request": request,
                    "selected_workflow_reference": source.manifest.workflow_name,
                    "analysis_source_root": frozen_source.root,
                    "analysis_evidence_root": frozen_evidence.root,
                    "analysis_evidence_index": "index.json",
                    "priority": params.objective,
                    "evidence": _neutral_evidence(snapshot),
                    "selected_workflow_source_manifest": model_source_manifest,
                    "baseline_surface_manifest": model_manifest,
                    "executable_contract": {
                        "function": source.manifest.qualname,
                        "signature": source.manifest.signature,
                        "input_schema": source.manifest.input_schema,
                        "return_annotation": source.manifest.return_annotation,
                    },
                    "caller_trial_inputs": {
                        "trial_cases": [
                            item.model_dump(mode="json")
                            for item in params.trial_cases
                        ],
                        "fixture_supplied": params.trial_fixture_path is not None,
                        "settings": params.trial_settings.model_dump(mode="json"),
                    },
                    "grounding_feedback": grounding_feedback,
                    "grounding_attempt": grounding_attempt,
                    "max_grounding_repairs": params.max_grounding_repairs,
                },
                returns=DiagnosticAssessment,
                output_retries=0,
            )
        except OutputValidationError as exc:
            verify_frozen_analysis()
            if grounding_attempt >= params.max_grounding_repairs:
                raise GroundingError(
                    "investigation output remained malformed after "
                    f"{params.max_grounding_repairs} repair(s): {exc}"
                ) from exc
            grounding_feedback = f"assessment schema error: {exc}"
            continue
        verify_frozen_analysis()
        try:
            candidate_assessment = _validate_assessment(
                result.value,
                snapshot=snapshot,
                baseline_manifest=source.baseline_manifest,
                frozen_source=frozen_source,
                frozen_evidence=frozen_evidence,
            )
            from .evaluation import (
                TrialIntegrityError,
                TrialPlanError,
                freeze_trial_plan,
            )

            try:
                candidate_plan = freeze_trial_plan(
                    params=params,
                    assessment=candidate_assessment,
                    analysis_root=Path(frozen_evidence.root),
                    analysis_hashes=frozen_evidence.hashes,
                    source_manifest=source.baseline_manifest,
                )
            except TrialIntegrityError:
                raise
            except TrialPlanError as exc:
                if params.trial_cases:
                    raise
                raise GroundingError(str(exc)) from exc
            assessment = candidate_assessment
            frozen_trial_plan = candidate_plan
            break
        except GroundingError as exc:
            if grounding_attempt >= params.max_grounding_repairs:
                raise GroundingError(
                    "investigation grounding remained invalid after "
                    f"{params.max_grounding_repairs} repair(s): {exc}"
                ) from exc
            grounding_feedback = str(exc)
    assert assessment is not None
    verify_frozen_analysis()

    producer = investigator.with_config(session=None)
    reviewer = producer.with_config(session=None)
    review: CandidateReview | None = None
    candidate_set: CandidateSet | None = None
    feedback: dict[str, Any] | None = None

    for revision in range(params.max_revisions + 1):
        proposal_feedback = feedback
        for grounding_attempt in range(params.max_grounding_repairs + 1):
            try:
                proposal = producer.query(
                    Prompt.file("prompts/propose.md"),
                    input={
                        "request": request,
                        "selected_workflow_reference": source.manifest.workflow_name,
                        "analysis_source_root": frozen_source.root,
                        "analysis_evidence_root": frozen_evidence.root,
                        "priority": params.objective,
                        "evidence": _neutral_evidence(snapshot),
                        "assessment": assessment.model_dump(mode="json"),
                        "frozen_trial_plan": frozen_trial_plan,
                        "selected_workflow_source_manifest": model_source_manifest,
                        "baseline_surface_manifest": model_manifest,
                        "max_candidates": 1,
                        "max_output_bytes": params.max_output_bytes,
                        "revision": revision,
                        "max_revisions": params.max_revisions,
                        "review_feedback": proposal_feedback,
                    },
                    returns=Proposal,
                    output_retries=0,
                )
            except OutputValidationError as exc:
                verify_frozen_analysis()
                if grounding_attempt >= params.max_grounding_repairs:
                    raise GroundingError(
                        "proposal output remained malformed after "
                        f"{params.max_grounding_repairs} repair(s): {exc}"
                    ) from exc
                proposal_feedback = {
                    "grounding_error": f"proposal schema error: {exc}",
                    "prior_feedback": feedback,
                }
                continue
            verify_frozen_analysis()
            try:
                _validate_proposal_grounding(
                    proposal.value,
                    snapshot=snapshot,
                    baseline_manifest=source.baseline_manifest,
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
                    baseline_manifest=source.baseline_manifest,
                )
                break
            except GroundingError as exc:
                if grounding_attempt >= params.max_grounding_repairs:
                    raise GroundingError(
                        "proposal grounding remained invalid after "
                        f"{params.max_grounding_repairs} repair(s): {exc}"
                    ) from exc
                proposal_feedback = {
                    "grounding_error": str(exc),
                    "prior_feedback": feedback,
                }
        assert candidate_set is not None
        review_grounding_feedback: str | None = None
        for grounding_attempt in range(params.max_grounding_repairs + 1):
            try:
                decision = reviewer.query(
                    Prompt.file("prompts/review_proposal.md"),
                    input={
                        "request": request,
                        "priority": params.objective,
                        "analysis_source_root": frozen_source.root,
                        "analysis_evidence_root": frozen_evidence.root,
                        "evidence": _neutral_evidence(snapshot),
                        "assessment": assessment.model_dump(mode="json"),
                        "frozen_trial_plan": frozen_trial_plan,
                        "candidate_set": candidate_set.model_dump(
                            mode="json", by_alias=True
                        ),
                        "selected_workflow_source_manifest": model_source_manifest,
                        "baseline_surface_manifest": model_manifest,
                        "max_candidates": 1,
                        "max_output_bytes": params.max_output_bytes,
                        "grounding_feedback": review_grounding_feedback,
                    },
                    returns=ChangeReview,
                    output_retries=0,
                )
                break
            except OutputValidationError as exc:
                verify_frozen_analysis()
                if grounding_attempt >= params.max_grounding_repairs:
                    raise GroundingError(
                        "proposal review output remained malformed after "
                        f"{params.max_grounding_repairs} repair(s): {exc}"
                    ) from exc
                review_grounding_feedback = f"review schema error: {exc}"
        review = _finalize_review(decision.value, candidate_set)
        review = validate_candidate_review(
            review,
            candidate_set=candidate_set,
            max_output_bytes=params.max_output_bytes,
        )
        verify_frozen_analysis()
        if review.accepted:
            return Recommendation(
                evidence_snapshot=snapshot,
                assessment=assessment,
                candidate_set=candidate_set,
                review=review,
                receipt=None,
                baseline_manifest=source.baseline_manifest,
                frozen_trial_plan=frozen_trial_plan,
                analysis_root=frozen_evidence.root,
                analysis_hashes=frozen_evidence.hashes,
            )
        feedback = decision.value.model_dump(mode="json")

    assert candidate_set is not None and review is not None
    return Recommendation(
        evidence_snapshot=snapshot,
        assessment=assessment,
        candidate_set=candidate_set,
        review=review,
        receipt=None,
        baseline_manifest=source.baseline_manifest,
        frozen_trial_plan=frozen_trial_plan,
        analysis_root=frozen_evidence.root,
        analysis_hashes=frozen_evidence.hashes,
    )


__all__ = ["propose_improvement"]
