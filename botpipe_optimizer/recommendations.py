"""Identity-bound optimizer recommendations, review, publication, and handoff."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from botpipe.storage import sync_directory
from botpipe.surface_identity import SURFACE_MANIFEST_SCHEMA, canonical_surface_id

from .evidence import EvidenceSnapshot, baseline_surface_id
from .records import (
    Candidate,
    CandidateKind,
    CandidateReview,
    CandidateSet,
    HandoffCandidate,
    PublicationReceipt,
    RefinementHandoff,
    SupportingArtifact,
)


@dataclass(frozen=True, slots=True)
class OptimizationCandidateSelection:
    """One independently reviewed candidate bound to its published evidence."""

    receipt: PublicationReceipt
    candidate_set: CandidateSet
    candidate: Candidate
    evidence_snapshot_path: Path
    baseline_surface_manifest_path: Path
    refinement_handoff_path: Path


def finalize_candidate_set_payload(payload: Mapping[str, Any]) -> CandidateSet:
    draft = json.loads(json.dumps(dict(payload)))
    draft["candidate_set_id"] = "candidate_set_" + "0" * 64
    if not isinstance(draft.get("candidates"), list):
        raise TypeError("candidates must be an array")
    for candidate in draft["candidates"]:
        if not isinstance(candidate, dict):
            raise TypeError("candidates must be objects")
        candidate["candidate_id"] = "candidate_" + "0" * 64
    provisional = CandidateSet.model_validate(draft)
    for raw, candidate in zip(draft["candidates"], provisional.candidates, strict=True):
        raw["candidate_id"] = candidate.expected_candidate_id()
    provisional = CandidateSet.model_validate(draft)
    draft["candidate_set_id"] = provisional.expected_candidate_set_id()
    result = CandidateSet.model_validate(draft)
    result.verify_identity()
    return result


def finalize_candidate_review_payload(payload: Mapping[str, Any]) -> CandidateReview:
    draft = json.loads(json.dumps(dict(payload)))
    draft["review_id"] = "candidate_review_" + "0" * 64
    provisional = CandidateReview.model_validate(draft)
    draft["review_id"] = provisional.expected_review_id()
    result = CandidateReview.model_validate(draft)
    result.verify_identity()
    return result


def build_empty_candidate_set(
    *,
    selected_workflow: str,
    evidence_snapshot_id: str,
    baseline_surface_manifest_id: str,
    next_action: str,
    reason: str,
) -> CandidateSet:
    return finalize_candidate_set_payload(
        {
            "schema": "botpipe.workflow_optimization.candidate_set/v2",
            "selected_workflow": selected_workflow,
            "evidence_snapshot_id": evidence_snapshot_id,
            "baseline_surface_manifest_id": baseline_surface_manifest_id,
            "candidates": [],
            "next_action": next_action,
            "no_candidate_reason": reason,
        }
    )


def validate_candidate_set(
    candidate_set: CandidateSet,
    *,
    evidence_snapshot: EvidenceSnapshot,
    max_candidates: int,
    allowed_kinds: Iterable[CandidateKind],
    expected_selected_workflow: str,
    max_output_bytes: int,
) -> CandidateSet:
    _validate_candidate_semantics(candidate_set, evidence_snapshot)
    if candidate_set.selected_workflow != expected_selected_workflow:
        raise ValueError("CandidateSet selected_workflow does not match invocation")
    if len(candidate_set.candidates) > max_candidates:
        raise ValueError("CandidateSet exceeds max_candidates")
    forbidden = sorted(
        {item.kind for item in candidate_set.candidates} - set(allowed_kinds)
    )
    if forbidden:
        raise ValueError(f"disabled candidate kinds: {', '.join(forbidden)}")
    _bounded_record(candidate_set, max_output_bytes, "CandidateSet")
    return candidate_set


def _validate_candidate_semantics(
    candidate_set: CandidateSet, evidence_snapshot: EvidenceSnapshot
) -> None:
    """Validate evidence-linked semantics independent of invocation policy."""
    candidate_set.verify_identity()
    if candidate_set.selected_workflow != evidence_snapshot.selected_workflow:
        raise ValueError("CandidateSet selected workflow does not match evidence")
    if candidate_set.evidence_snapshot_id != evidence_snapshot.snapshot_id:
        raise ValueError("CandidateSet evidence snapshot mismatch")
    if (
        candidate_set.baseline_surface_manifest_id
        != evidence_snapshot.baseline_surface_manifest_id
    ):
        raise ValueError("CandidateSet baseline mismatch")
    candidate_ids = [item.candidate_id for item in candidate_set.candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("candidate IDs must be unique across kinds")
    citable = evidence_snapshot.citable_observation_ids()
    for candidate in candidate_set.candidates:
        if not candidate.cited_observation_ids:
            raise ValueError("candidate must cite at least one observation")
        unknown = sorted(set(candidate.cited_observation_ids) - citable)
        if unknown:
            raise ValueError(
                f"candidate cites unknown observations: {', '.join(unknown)}"
            )
    if candidate_set.candidates and (
        candidate_set.next_action != "implement_candidate"
        or candidate_set.no_candidate_reason is not None
    ):
        raise ValueError(
            "non-empty CandidateSet must request implementation without a no-candidate reason"
        )
    if not candidate_set.candidates and (
        candidate_set.next_action == "implement_candidate"
        or not candidate_set.no_candidate_reason
    ):
        raise ValueError("empty CandidateSet needs an evidence/no-change reason")


def _baseline_manifest_identity(baseline_manifest: Mapping[str, Any]) -> str:
    """Derive the baseline identity instead of trusting an asserted surface ID."""
    recorded = baseline_manifest.get("surface_id")
    if recorded is None:
        return baseline_surface_id(baseline_manifest)
    if baseline_manifest.get("schema") != SURFACE_MANIFEST_SCHEMA:
        raise ValueError("asserted baseline surface_id requires a canonical manifest")
    try:
        derived = canonical_surface_id(
            boundary=baseline_manifest["boundary"],
            files=baseline_manifest["files"],
            mode_semantics=baseline_manifest["mode_semantics"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid canonical baseline surface manifest") from exc
    if recorded != derived:
        raise ValueError("baseline surface_id does not match manifest content")
    return derived


def validate_candidate_review(
    review: CandidateReview,
    *,
    candidate_set: CandidateSet,
    max_output_bytes: int,
) -> CandidateReview:
    review.verify_identity()
    if (
        review.candidate_set_id,
        review.evidence_snapshot_id,
        review.baseline_surface_manifest_id,
    ) != (
        candidate_set.candidate_set_id,
        candidate_set.evidence_snapshot_id,
        candidate_set.baseline_surface_manifest_id,
    ):
        raise ValueError("review anchors do not match CandidateSet")
    ids = [item.candidate_id for item in candidate_set.candidates]
    if review.reviewed_candidate_ids != ids:
        raise ValueError("reviewed IDs must exactly match CandidateSet order")
    if any(finding.candidate_id not in ids for finding in review.findings):
        raise ValueError("review finding cites unknown candidate")
    if review.accepted and any(
        finding.severity == "error" for finding in review.findings
    ):
        raise ValueError("accepted review contains error finding")
    _bounded_record(review, max_output_bytes, "candidate review")
    return review


def publish_recommendation(
    *,
    output_dir: str | Path,
    evidence_snapshot: EvidenceSnapshot,
    candidate_set: CandidateSet,
    review: CandidateReview | None,
    baseline_manifest: Mapping[str, Any],
    max_output_bytes: int,
    supporting_content: bytes | None = None,
) -> PublicationReceipt:
    """Publish one immutable generation, then atomically select its receipt.

    The root receipt is the sole mutable name.  Every path recorded in it points
    into a content-addressed generation directory, so a later publication cannot
    invalidate a receipt that a caller has already copied or journaled.
    """
    # Re-parse the snapshot to catch identity-breaking ``model_copy(update=...)``
    # values before touching the publication directory.
    evidence_snapshot = EvidenceSnapshot.model_validate(
        evidence_snapshot.model_dump(mode="python", by_alias=True), strict=True
    )
    candidate_set = CandidateSet.model_validate(
        candidate_set.model_dump(mode="python", by_alias=True), strict=True
    )
    if review is not None:
        review = CandidateReview.model_validate(
            review.model_dump(mode="python", by_alias=True), strict=True
        )
    _validate_candidate_semantics(candidate_set, evidence_snapshot)
    if candidate_set.candidates:
        if review is None or not review.accepted:
            raise ValueError(
                "non-empty CandidateSet requires accepted independent review"
            )
        validate_candidate_review(
            review, candidate_set=candidate_set, max_output_bytes=max_output_bytes
        )
    elif review is not None:
        validate_candidate_review(
            review, candidate_set=candidate_set, max_output_bytes=max_output_bytes
        )
    if (
        _baseline_manifest_identity(baseline_manifest)
        != candidate_set.baseline_surface_manifest_id
    ):
        raise ValueError("baseline manifest identity does not match CandidateSet")
    evidence_content = _json_bytes(
        evidence_snapshot.model_dump(mode="json", by_alias=True)
    )
    baseline_content = _json_bytes(dict(baseline_manifest))
    candidate_content = _json_bytes(
        candidate_set.model_dump(mode="json", by_alias=True)
    )
    review_content = (
        None
        if review is None
        else _json_bytes(review.model_dump(mode="json", by_alias=True))
    )
    report = render_recommendation_report(evidence_snapshot, candidate_set, review)
    report_content = report.encode()

    generation_id = _publication_generation_id(
        {
            "workflow_optimization_evidence.json": evidence_content,
            "baseline_surface_manifest.json": baseline_content,
            "workflow_optimization_candidates.json": candidate_content,
            "workflow_optimization_candidate_review.json": review_content,
            "workflow_optimization_report.md": report_content,
            "workflow_optimization_supporting.md": supporting_content,
        }
    )
    root = Path(output_dir).resolve()
    generation_path = root / "optimization_publications" / generation_id
    candidate_path = generation_path / "workflow_optimization_candidates.json"
    review_path = generation_path / "workflow_optimization_candidate_review.json"
    evidence_path = generation_path / "workflow_optimization_evidence.json"
    baseline_path = generation_path / "baseline_surface_manifest.json"
    report_path = generation_path / "workflow_optimization_report.md"
    handoff_path = generation_path / "workflow_refinement_evidence.json"
    supporting_path = generation_path / "workflow_optimization_supporting.md"
    handoff = RefinementHandoff(
        target_workflow_id=candidate_set.selected_workflow,
        evidence_snapshot_id=evidence_snapshot.snapshot_id,
        evidence_snapshot_path=str(evidence_path.resolve()),
        baseline_surface_manifest_id=candidate_set.baseline_surface_manifest_id,
        baseline_surface_manifest_path=str(baseline_path.resolve()),
        candidate_set_id=candidate_set.candidate_set_id,
        candidate_set_path=str(candidate_path.resolve()),
        candidates=[
            HandoffCandidate(
                candidate_id=item.candidate_id, kind=item.kind, title=item.title
            )
            for item in candidate_set.candidates
        ],
    )
    handoff_content = _json_bytes(handoff.model_dump(mode="json", by_alias=True))
    recommendation_output = [candidate_content, report_content, handoff_content]
    if review_content is not None:
        recommendation_output.append(review_content)
    if supporting_content is not None:
        recommendation_output.append(supporting_content)
    total = sum(len(content) for content in recommendation_output)
    if total > max_output_bytes:
        raise ValueError("published recommendation exceeds max_output_bytes")

    published = [
        (evidence_path, evidence_content),
        (baseline_path, baseline_content),
        (candidate_path, candidate_content),
        (report_path, report_content),
        (handoff_path, handoff_content),
    ]
    if review_content is not None:
        published.append((review_path, review_content))
    if supporting_content is not None:
        published.append((supporting_path, supporting_content))
    supporting = [
        SupportingArtifact(
            path=str(path.resolve()),
            sha256=hashlib.sha256(content).hexdigest(),
            bytes=len(content),
        )
        for path, content in published
    ]
    receipt = PublicationReceipt(
        status="accepted",
        selected_workflow=candidate_set.selected_workflow,
        evidence_snapshot_id=evidence_snapshot.snapshot_id,
        evidence_snapshot_path=str(evidence_path.resolve()),
        baseline_surface_manifest_id=candidate_set.baseline_surface_manifest_id,
        baseline_surface_manifest_path=str(baseline_path.resolve()),
        candidate_set_id=candidate_set.candidate_set_id,
        candidate_set_path=str(candidate_path.resolve()),
        review_id=None if review is None else review.review_id,
        review_path=None if review is None else str(review_path.resolve()),
        reviewed_candidate_ids=[] if review is None else review.reviewed_candidate_ids,
        next_action=candidate_set.next_action,
        refinement_handoff_path=str(handoff_path.resolve()),
        report_path=str(report_path.resolve()),
        supporting_artifacts=supporting,
        stop_reason=None,
    )
    receipt_content = _json_bytes(receipt.model_dump(mode="json", by_alias=True))
    if len(receipt_content) > max_output_bytes:
        raise ValueError("publication receipt exceeds max_output_bytes")
    generation_files = {path.name: content for path, content in published} | {
        "optimization_publication_receipt.json": receipt_content
    }
    _install_publication_generation(generation_path, generation_files)

    # This replace is the commit point.  Failures before it leave the previous
    # canonical receipt and all files it references byte-for-byte untouched.
    _atomic_bytes(root / "optimization_publication_receipt.json", receipt_content)
    return receipt


def render_recommendation_report(
    evidence_snapshot: EvidenceSnapshot,
    candidate_set: CandidateSet,
    review: CandidateReview | None,
) -> str:
    lines = [
        "# Workflow optimization recommendation",
        "",
        f"- Selected workflow: `{candidate_set.selected_workflow}`",
        f"- Evidence snapshot: `{candidate_set.evidence_snapshot_id}`",
        f"- Baseline surface: `{candidate_set.baseline_surface_manifest_id}`",
        f"- Recommendation basis: `{evidence_snapshot.recommendation_basis}`",
        "- Improvement: `not_evaluated`",
        f"- Next action: `{candidate_set.next_action}`",
        "",
        "## Candidates",
        "",
    ]
    lines.extend(
        [
            f"- `{item.candidate_id}` ({item.kind}): {item.title}; hypothesis: {item.expected_effect}"
            for item in candidate_set.candidates
        ]
        or [f"- No candidates. {candidate_set.no_candidate_reason}"]
    )
    if review is not None:
        lines.extend(["", f"Independent review accepted: `{review.accepted}`"])
    lines.extend(
        ["", "Candidate effects remain hypotheses until comparable evaluation."]
    )
    return "\n".join(lines) + "\n"


def read_publication_receipt(
    path: str | Path, *, max_output_bytes: int
) -> PublicationReceipt:
    return PublicationReceipt.model_validate_json(
        _read_bounded(Path(path), max_output_bytes, "receipt"), strict=True
    )


def read_candidate_set(path: str | Path, *, max_output_bytes: int) -> CandidateSet:
    return CandidateSet.model_validate_json(
        _read_bounded(Path(path), max_output_bytes, "CandidateSet"),
        strict=True,
    )


def read_candidate_review(
    path: str | Path, *, max_output_bytes: int
) -> CandidateReview:
    return CandidateReview.model_validate_json(
        _read_bounded(Path(path), max_output_bytes, "candidate review"),
        strict=True,
    )


def read_refinement_handoff(
    path: str | Path, *, max_output_bytes: int
) -> RefinementHandoff:
    return RefinementHandoff.model_validate_json(
        _read_bounded(Path(path), max_output_bytes, "handoff"), strict=True
    )


def load_optimization_candidate(
    *,
    optimization_receipt_path: str | Path,
    candidate_id: str,
    expected_selected_workflow: str,
    allowed_kinds: Iterable[CandidateKind],
    max_output_bytes: int = 10 * 1024 * 1024,
    max_evidence_bytes: int = 50 * 1024 * 1024,
) -> OptimizationCandidateSelection:
    """Load an accepted candidate only when every published identity still agrees."""
    receipt_path = Path(optimization_receipt_path).resolve(strict=True)
    receipt = read_publication_receipt(receipt_path, max_output_bytes=max_output_bytes)
    if (
        receipt.status != "accepted"
        or receipt.selected_workflow != expected_selected_workflow
        or candidate_id not in receipt.reviewed_candidate_ids
    ):
        raise ValueError(
            "optimization receipt/candidate is not accepted for selected workflow"
        )
    required = (
        receipt.candidate_set_path,
        receipt.evidence_snapshot_path,
        receipt.baseline_surface_manifest_path,
        receipt.refinement_handoff_path,
        receipt.review_path,
    )
    if not all(required):
        raise ValueError("accepted reviewed receipt is missing required paths")

    receipt_dir = receipt_path.parent
    artifacts = _verified_receipt_artifacts(
        receipt,
        receipt_dir,
        max_output_bytes + max_evidence_bytes,
    )
    candidate_set_path = _receipt_artifact_path(
        receipt_dir, receipt.candidate_set_path, "CandidateSet"
    )
    evidence_path = _receipt_artifact_path(
        receipt_dir, receipt.evidence_snapshot_path, "evidence snapshot"
    )
    baseline_path = _receipt_artifact_path(
        receipt_dir,
        receipt.baseline_surface_manifest_path,
        "baseline surface manifest",
    )
    handoff_path = _receipt_artifact_path(
        receipt_dir, receipt.refinement_handoff_path, "refinement handoff"
    )
    review_path = _receipt_artifact_path(
        receipt_dir, receipt.review_path, "candidate review"
    )
    for path in (
        candidate_set_path,
        evidence_path,
        baseline_path,
        handoff_path,
        review_path,
    ):
        if path not in artifacts:
            raise ValueError(f"receipt does not hash published artifact: {path.name}")

    candidate_set = read_candidate_set(
        candidate_set_path, max_output_bytes=max_output_bytes
    )
    candidate_set.verify_identity()
    if (
        candidate_set.candidate_set_id,
        candidate_set.evidence_snapshot_id,
        candidate_set.baseline_surface_manifest_id,
        candidate_set.selected_workflow,
    ) != (
        receipt.candidate_set_id,
        receipt.evidence_snapshot_id,
        receipt.baseline_surface_manifest_id,
        receipt.selected_workflow,
    ):
        raise ValueError("receipt and CandidateSet anchors do not match")
    evidence = EvidenceSnapshot.model_validate_json(
        _read_bounded(evidence_path, max_evidence_bytes, "evidence snapshot"),
        strict=True,
    )
    if (
        evidence.snapshot_id != receipt.evidence_snapshot_id
        or evidence.selected_workflow != receipt.selected_workflow
        or evidence.baseline_surface_manifest_id != receipt.baseline_surface_manifest_id
    ):
        raise ValueError("evidence anchors do not match receipt")
    _validate_candidate_semantics(candidate_set, evidence)

    matches = [
        item for item in candidate_set.candidates if item.candidate_id == candidate_id
    ]
    if len(matches) != 1 or matches[0].kind not in set(allowed_kinds):
        raise ValueError("candidate is absent, duplicated, or has a disallowed kind")
    baseline = json.loads(
        _read_bounded(baseline_path, max_evidence_bytes, "baseline surface manifest")
    )
    if not isinstance(baseline, dict) or (
        _baseline_manifest_identity(baseline) != receipt.baseline_surface_manifest_id
    ):
        raise ValueError("baseline surface identity does not match receipt")

    handoff = read_refinement_handoff(handoff_path, max_output_bytes=max_output_bytes)
    expected_handoff = (
        receipt.selected_workflow,
        receipt.evidence_snapshot_id,
        str(evidence_path),
        receipt.baseline_surface_manifest_id,
        str(baseline_path),
        receipt.candidate_set_id,
        str(candidate_set_path),
    )
    actual_handoff = (
        handoff.target_workflow_id,
        handoff.evidence_snapshot_id,
        handoff.evidence_snapshot_path,
        handoff.baseline_surface_manifest_id,
        handoff.baseline_surface_manifest_path,
        handoff.candidate_set_id,
        handoff.candidate_set_path,
    )
    selected_handoff = select_handoff_candidate(
        handoff,
        candidate_id,
        expected_workflow=receipt.selected_workflow,
        allowed_kinds=allowed_kinds,
    )
    if actual_handoff != expected_handoff or selected_handoff.title != matches[0].title:
        raise ValueError("refinement handoff does not match published candidate")

    review = read_candidate_review(review_path, max_output_bytes=max_output_bytes)
    validate_candidate_review(
        review, candidate_set=candidate_set, max_output_bytes=max_output_bytes
    )
    if (
        not review.accepted
        or review.review_id != receipt.review_id
        or review.reviewed_candidate_ids != receipt.reviewed_candidate_ids
    ):
        raise ValueError("candidate is not covered by the accepted independent review")
    return OptimizationCandidateSelection(
        receipt=receipt,
        candidate_set=candidate_set,
        candidate=matches[0],
        evidence_snapshot_path=evidence_path,
        baseline_surface_manifest_path=baseline_path,
        refinement_handoff_path=handoff_path,
    )


def select_handoff_candidate(
    handoff: RefinementHandoff,
    candidate_id: str,
    *,
    expected_workflow: str,
    allowed_kinds: Iterable[CandidateKind],
) -> HandoffCandidate:
    if handoff.target_workflow_id != expected_workflow:
        raise ValueError("optimizer handoff targets another workflow")
    matches = [item for item in handoff.candidates if item.candidate_id == candidate_id]
    if len(matches) != 1:
        raise ValueError("candidate_id is absent or duplicated in optimizer handoff")
    if matches[0].kind not in set(allowed_kinds):
        raise ValueError(
            f"candidate kind {matches[0].kind!r} is not accepted by this workflow"
        )
    return matches[0]


def _bounded_record(value: Any, limit: int, label: str) -> bytes:
    if limit <= 0:
        raise ValueError("max_output_bytes must be positive")
    payload = (
        value.model_dump(mode="json", by_alias=True)
        if hasattr(value, "model_dump")
        else value
    )
    content = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    if len(content) > limit:
        raise ValueError(f"{label} exceeds max_output_bytes")
    return content


def _read_bounded(path: Path, limit: int, label: str) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError(f"{label} must be a bounded regular file")
    content = path.read_bytes()
    if len(content) > limit:
        raise ValueError(f"{label} exceeds byte limit")
    return content


def _receipt_artifact_path(receipt_dir: Path, raw_path: str | None, label: str) -> Path:
    if not raw_path:
        raise ValueError(f"{label} path is missing")
    unresolved = Path(raw_path)
    resolved = unresolved.resolve(strict=True)
    try:
        resolved.relative_to(receipt_dir)
    except ValueError as exc:
        raise ValueError(
            f"{label} is outside the optimization receipt directory"
        ) from exc
    if unresolved.is_symlink() or not resolved.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    return resolved


def _verified_receipt_artifacts(
    receipt: PublicationReceipt,
    receipt_dir: Path,
    byte_limit: int,
) -> set[Path]:
    paths: set[Path] = set()
    total = 0
    for artifact in receipt.supporting_artifacts:
        path = _receipt_artifact_path(receipt_dir, artifact.path, "supporting artifact")
        if path in paths:
            raise ValueError("receipt contains duplicate supporting artifact paths")
        content = _read_bounded(path, byte_limit, "supporting artifact")
        total += len(content)
        if total > byte_limit:
            raise ValueError("receipt supporting artifacts exceed byte limit")
        if (
            len(content) != artifact.bytes
            or hashlib.sha256(content).hexdigest() != artifact.sha256
        ):
            raise ValueError(
                f"supporting artifact changed after publication: {path.name}"
            )
        paths.add(path)
    return paths


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _publication_generation_id(contents: Mapping[str, bytes | None]) -> str:
    """Return a stable ID for the complete caller-supplied publication input."""
    manifest = [
        {
            "name": name,
            "sha256": None if content is None else hashlib.sha256(content).hexdigest(),
            "bytes": None if content is None else len(content),
        }
        for name, content in sorted(contents.items())
    ]
    digest = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"publication_{digest}"


def _install_publication_generation(
    generation_path: Path, contents: Mapping[str, bytes]
) -> None:
    """Durably install a new directory, or verify an identical prior install."""
    parent = generation_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir() or parent.resolve() != parent:
        raise ValueError("publication directory must be a real in-root directory")
    temporary = Path(tempfile.mkdtemp(prefix=".publication-", dir=parent))
    try:
        for name, content in contents.items():
            _write_new_file(temporary / name, content)
        sync_directory(temporary)
        try:
            os.rename(temporary, generation_path)
        except OSError:
            if generation_path.is_symlink() or not generation_path.is_dir():
                raise
            _verify_generation(generation_path, contents)
        else:
            sync_directory(parent)
            return
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _verify_generation(path: Path, contents: Mapping[str, bytes]) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ValueError("publication generation must be a real directory")
    expected = set(contents)
    entries = list(path.iterdir())
    actual = {item.name for item in entries}
    if actual != expected or any(
        item.is_symlink() or not item.is_file() for item in entries
    ):
        raise ValueError("publication generation conflicts with existing contents")
    for name, content in contents.items():
        candidate = path / name
        if not candidate.is_file() or candidate.read_bytes() != content:
            raise ValueError("publication generation conflicts with existing contents")


def _write_new_file(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_json(path: Path, value: Any) -> None:
    _atomic_bytes(path, _json_bytes(value))


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                break
            except PermissionError as exc:
                # Windows may briefly deny replacement while another atomic
                # writer or reader closes its handle. Retry only that bounded
                # contention window; keep the previous receipt and staged file.
                if getattr(exc, "winerror", None) not in (5, 32, 33) or attempt == 7:
                    raise
                time.sleep(0.01 * 2**attempt)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


__all__ = [
    "OptimizationCandidateSelection",
    "build_empty_candidate_set",
    "finalize_candidate_review_payload",
    "finalize_candidate_set_payload",
    "load_optimization_candidate",
    "publish_recommendation",
    "read_candidate_review",
    "read_candidate_set",
    "read_publication_receipt",
    "read_refinement_handoff",
    "render_recommendation_report",
    "select_handoff_candidate",
    "validate_candidate_review",
    "validate_candidate_set",
]
