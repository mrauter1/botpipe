"""Deterministic validation, publication, and consumer loading for optimizer v2."""

from __future__ import annotations
import hashlib, json, os, stat, tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
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


def atomic_write_bytes(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return path


def atomic_write_record(path, record):
    payload = (
        record.model_dump(mode="json", by_alias=True)
        if hasattr(record, "model_dump")
        else record
    )
    return atomic_write_bytes(
        path, (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    )


def _read_bounded(path: Path, limit: int, label: str) -> bytes:
    if limit <= 0:
        raise ValueError(f"{label} byte limit must be positive")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{label} must be a regular non-symlink file") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{label} must be a regular file")
        if metadata.st_size > limit:
            raise ValueError(f"{label} exceeds byte limit")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > limit:
            raise ValueError(f"{label} exceeds byte limit")
        return content
    finally:
        os.close(descriptor)


def read_candidate_set(path: Path, *, max_output_bytes: int) -> CandidateSet:
    return CandidateSet.model_validate_json(
        _read_bounded(path, max_output_bytes, "CandidateSet"), strict=True
    )


def read_candidate_review(path: Path, *, max_output_bytes: int) -> CandidateReview:
    return CandidateReview.model_validate_json(
        _read_bounded(path, max_output_bytes, "candidate review"), strict=True
    )


def _field(obj, name):
    return obj.get(name) if isinstance(obj, Mapping) else getattr(obj, name)


def _citable(snapshot):
    fn = getattr(snapshot, "citable_observation_ids", None)
    if callable(fn):
        return set(fn())
    return {
        (_field(o, "observation_id")) for o in (_field(snapshot, "observations") or [])
    }


def validate_candidate_set(
    candidate_set: CandidateSet,
    *,
    evidence_snapshot,
    max_candidates: int,
    allowed_kinds: Iterable[CandidateKind],
    expected_selected_workflow: str,
    allowed_target_paths: Iterable[str] | None = None,
    allowed_target_prefixes: Iterable[str] = (),
) -> CandidateSet:
    if max_candidates <= 0:
        raise ValueError("max_candidates must be positive")
    candidate_set.verify_identity()
    if candidate_set.selected_workflow != expected_selected_workflow:
        raise ValueError("CandidateSet selected_workflow does not match invocation")
    if candidate_set.evidence_snapshot_id != _field(evidence_snapshot, "snapshot_id"):
        raise ValueError("CandidateSet evidence snapshot mismatch")
    if candidate_set.baseline_surface_manifest_id != _field(
        evidence_snapshot, "baseline_surface_manifest_id"
    ):
        raise ValueError("CandidateSet baseline mismatch")
    if len(candidate_set.candidates) > max_candidates:
        raise ValueError("CandidateSet exceeds max_candidates")
    ids = [c.candidate_id for c in candidate_set.candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("candidate IDs must be unique across kinds")
    forbidden = sorted({c.kind for c in candidate_set.candidates} - set(allowed_kinds))
    if forbidden:
        raise ValueError(f"disabled candidate kinds: {', '.join(forbidden)}")
    exact = None if allowed_target_paths is None else set(allowed_target_paths)
    prefixes = tuple(x.rstrip("/") + "/" for x in allowed_target_prefixes)
    for c in candidate_set.candidates:
        unknown = sorted(set(c.cited_observation_ids) - _citable(evidence_snapshot))
        if unknown:
            raise ValueError(
                f"candidate cites unknown/unverified observations: {', '.join(unknown)}"
            )
        if exact is not None and any(
            t not in exact and not any(t.startswith(p) for p in prefixes)
            for t in c.targets
        ):
            raise ValueError("candidate target is outside editable boundary")
    if candidate_set.candidates and candidate_set.next_action != "implement_candidate":
        raise ValueError("non-empty CandidateSet must request implementation")
    if not candidate_set.candidates and (
        candidate_set.next_action == "implement_candidate"
        or not candidate_set.no_candidate_reason
    ):
        raise ValueError("empty CandidateSet needs an evidence/no-change reason")
    return candidate_set


def validate_candidate_review(
    review: CandidateReview, *, candidate_set: CandidateSet
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
    ids = [c.candidate_id for c in candidate_set.candidates]
    if review.reviewed_candidate_ids != ids:
        raise ValueError("reviewed IDs must exactly match CandidateSet order")
    if any(f.candidate_id not in ids for f in review.findings):
        raise ValueError("review finding cites unknown candidate")
    if review.accepted and any(f.severity == "error" for f in review.findings):
        raise ValueError("accepted review contains error finding")
    return review


def finalize_candidate_set_payload(payload: Mapping[str, Any]) -> CandidateSet:
    draft = json.loads(json.dumps(dict(payload)))
    draft["candidate_set_id"] = "candidate_set_" + "0" * 64
    if not isinstance(draft.get("candidates"), list):
        raise ValueError("candidates must be an array")
    for c in draft["candidates"]:
        if not isinstance(c, dict):
            raise ValueError("candidates must be objects")
        c["candidate_id"] = "candidate_" + "0" * 64
    provisional = CandidateSet.model_validate(draft)
    for raw, c in zip(draft["candidates"], provisional.candidates, strict=True):
        raw["candidate_id"] = c.expected_candidate_id()
    provisional = CandidateSet.model_validate(draft)
    draft["candidate_set_id"] = provisional.expected_candidate_set_id()
    result = CandidateSet.model_validate(draft)
    result.verify_identity()
    return result


def finalize_candidate_review_payload(payload: Mapping[str, Any]) -> CandidateReview:
    draft = dict(payload)
    draft["review_id"] = "candidate_review_" + "0" * 64
    provisional = CandidateReview.model_validate(draft)
    draft["review_id"] = provisional.expected_review_id()
    return CandidateReview.model_validate(draft)


def build_empty_candidate_set(
    *,
    selected_workflow,
    evidence_snapshot_id,
    baseline_surface_manifest_id,
    next_action,
    reason,
):
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


def render_recommendation_report(*, evidence_snapshot, candidate_set, review):
    lines = [
        "# Workflow optimization recommendation",
        "",
        f"- Selected workflow: `{candidate_set.selected_workflow}`",
        f"- Evidence snapshot: `{candidate_set.evidence_snapshot_id}`",
        f"- Baseline surface: `{candidate_set.baseline_surface_manifest_id}`",
        f"- Recommendation basis: `{_field(evidence_snapshot,'recommendation_basis')}`",
        "- Improvement: `not_evaluated`",
        f"- Next action: `{candidate_set.next_action}`",
        "",
        "## Candidates",
        "",
    ]
    lines += [
        f"- `{c.candidate_id}` ({c.kind}): {c.title}; hypothesis: {c.expected_effect}"
        for c in candidate_set.candidates
    ] or [f"- No candidates. {candidate_set.no_candidate_reason}"]
    lines += ["", "Candidate effects remain hypotheses until comparable evaluation."]
    return "\n".join(lines) + "\n"


def publish_recommendation(
    *,
    output_dir: Path,
    evidence_snapshot_path: Path,
    baseline_surface_manifest_path: Path,
    evidence_snapshot,
    candidate_set: CandidateSet,
    review: CandidateReview | None,
    max_output_bytes: int,
    max_evidence_bytes: int = 50 * 1024 * 1024,
    candidate_set_source_path: Path | None = None,
    review_source_path: Path | None = None,
    supporting_artifact_paths: Iterable[Path] = (),
    expected_baseline_root: Path | None = None,
    expected_baseline_boundary: Mapping[str, Any] | None = None,
    expected_baseline_kind: str = "workflow",
    expected_authoritative_sources: Mapping[str, Mapping[str, Any]] | None = None,
    max_authoritative_source_bytes: int = 512 * 1024 * 1024,
    before_commit=None,
) -> PublicationReceipt:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_incomplete_receipt(
        output_dir=output_dir,
        selected_workflow=candidate_set.selected_workflow,
        evidence_snapshot_id=candidate_set.evidence_snapshot_id,
        stop_reason="publication_in_progress",
    )
    if review:
        validate_candidate_review(review, candidate_set=candidate_set)
    if candidate_set.candidates and (review is None or not review.accepted):
        raise ValueError("non-empty CandidateSet requires accepted independent review")
    from .evidence import read_evidence_snapshot

    _read_bounded(evidence_snapshot_path, max_evidence_bytes, "evidence snapshot")
    persisted_evidence = read_evidence_snapshot(
        evidence_snapshot_path, max_bytes=max_evidence_bytes
    )
    if (
        persisted_evidence != evidence_snapshot
        or persisted_evidence.snapshot_id != candidate_set.evidence_snapshot_id
    ):
        raise ValueError("persisted evidence changed after validation")
    baseline_payload = _json(
        baseline_surface_manifest_path, max_evidence_bytes, "baseline surface manifest"
    )
    if baseline_payload.get("surface_id") != candidate_set.baseline_surface_manifest_id:
        raise ValueError("persisted baseline identity mismatch")
    from .candidate_surfaces import verify_surface_anchor

    root = expected_baseline_root or Path(str(baseline_payload.get("root")))
    boundary = expected_baseline_boundary or baseline_payload.get("boundary")
    if not isinstance(boundary, Mapping):
        raise ValueError("baseline surface boundary missing")
    if (
        verify_surface_anchor(
            baseline_payload,
            expected_root=root,
            expected_boundary=boundary,
            expected_surface_kind=expected_baseline_kind,
        )
        != candidate_set.baseline_surface_manifest_id
    ):
        raise ValueError("persisted baseline changed after validation")
    if expected_authoritative_sources is not None:
        if set(expected_authoritative_sources) != set(
            baseline_payload["relative_paths"]
        ):
            raise ValueError("authoritative source paths do not match baseline surface")
        remaining_source_bytes = max_authoritative_source_bytes
        for relative_path, source_anchor in expected_authoritative_sources.items():
            source = Path(str(source_anchor.get("source_path", "")))
            content = _read_bounded(
                source,
                remaining_source_bytes,
                f"authoritative source {relative_path}",
            )
            remaining_source_bytes -= len(content)
            executable = (
                bool(source.stat().st_mode & 0o111) if os.name == "posix" else False
            )
            if hashlib.sha256(content).hexdigest() != source_anchor.get(
                "sha256"
            ) or executable != source_anchor.get("executable"):
                raise ValueError(f"authoritative source changed: {relative_path}")
    cp = output_dir / "workflow_optimization_candidates.json"
    rp = output_dir / "workflow_optimization_report.md"
    hp = output_dir / "workflow_refinement_evidence.json"
    cb = (
        (
            json.dumps(
                candidate_set.model_dump(mode="json", by_alias=True),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()
        if candidate_set_source_path is None
        else _read_bounded(
            candidate_set_source_path, max_output_bytes, "CandidateSet source"
        )
    )
    if CandidateSet.model_validate_json(cb, strict=True) != candidate_set:
        raise ValueError("CandidateSet changed after validation")
    rb = render_recommendation_report(
        evidence_snapshot=evidence_snapshot, candidate_set=candidate_set, review=review
    ).encode()
    handoff = RefinementHandoff(
        target_workflow_id=candidate_set.selected_workflow,
        evidence_snapshot_id=candidate_set.evidence_snapshot_id,
        evidence_snapshot_path=str(evidence_snapshot_path.resolve()),
        baseline_surface_manifest_id=candidate_set.baseline_surface_manifest_id,
        baseline_surface_manifest_path=str(baseline_surface_manifest_path.resolve()),
        candidate_set_id=candidate_set.candidate_set_id,
        candidate_set_path=str(cp.resolve()),
        candidates=[
            HandoffCandidate(candidate_id=c.candidate_id, kind=c.kind, title=c.title)
            for c in candidate_set.candidates
        ],
    )
    hb = (
        json.dumps(
            handoff.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True
        )
        + "\n"
    ).encode()
    supporting = []
    supporting_total = 0
    model_supporting_paths = []
    remaining_model_bytes = max_output_bytes - len(cb)
    seen_paths = set()
    if review_source_path is not None:
        if review is None:
            raise ValueError("candidate review path supplied without a review")
        review_bytes = _read_bounded(
            review_source_path,
            remaining_model_bytes,
            "candidate review under max_output_bytes",
        )
        if CandidateReview.model_validate_json(review_bytes, strict=True) != review:
            raise ValueError("candidate review changed after validation")
        resolved_review = Path(review_source_path).resolve()
        seen_paths.add(resolved_review)
        supporting_total += len(review_bytes)
        supporting.append(
            SupportingArtifact(
                path=str(resolved_review),
                sha256=hashlib.sha256(review_bytes).hexdigest(),
                bytes=len(review_bytes),
            )
        )
    model_supporting_paths.extend(Path(path) for path in supporting_artifact_paths)
    for path in model_supporting_paths:
        resolved = path.resolve()
        if resolved in seen_paths:
            raise ValueError("duplicate supporting artifact path")
        seen_paths.add(resolved)
        content = _read_bounded(
            Path(path),
            max_output_bytes - len(cb) - supporting_total,
            "supporting artifact",
        )
        supporting_total += len(content)
        supporting.append(
            SupportingArtifact(
                path=str(Path(path).resolve()),
                sha256=hashlib.sha256(content).hexdigest(),
                bytes=len(content),
            )
        )
    if len(cb) + len(rb) + len(hb) + supporting_total > max_output_bytes:
        raise ValueError("recommendation output exceeds max_output_bytes")
    if (
        candidate_set_source_path is None
        or candidate_set_source_path.resolve() != cp.resolve()
    ):
        atomic_write_bytes(cp, cb)
    atomic_write_bytes(rp, rb)
    atomic_write_bytes(hp, hb)
    receipt = PublicationReceipt(
        status="accepted",
        selected_workflow=candidate_set.selected_workflow,
        evidence_snapshot_id=candidate_set.evidence_snapshot_id,
        evidence_snapshot_path=str(evidence_snapshot_path.resolve()),
        baseline_surface_manifest_id=candidate_set.baseline_surface_manifest_id,
        baseline_surface_manifest_path=str(baseline_surface_manifest_path.resolve()),
        candidate_set_id=candidate_set.candidate_set_id,
        candidate_set_path=str(cp.resolve()),
        review_id=None if review is None else review.review_id,
        review_path=(
            None if review_source_path is None else str(review_source_path.resolve())
        ),
        reviewed_candidate_ids=[] if review is None else review.reviewed_candidate_ids,
        next_action=candidate_set.next_action,
        refinement_handoff_path=str(hp.resolve()),
        report_path=str(rp.resolve()),
        supporting_artifacts=supporting,
        stop_reason=None,
    )
    if before_commit is not None:
        before_commit()
    atomic_write_record(output_dir / "optimization_publication_receipt.json", receipt)
    return receipt


def write_incomplete_receipt(
    *,
    output_dir: Path,
    selected_workflow: str,
    stop_reason: str,
    evidence_snapshot_id: str | None = None,
):
    receipt = PublicationReceipt(
        status="incomplete",
        selected_workflow=selected_workflow,
        evidence_snapshot_id=evidence_snapshot_id,
        evidence_snapshot_path=None,
        baseline_surface_manifest_id=None,
        baseline_surface_manifest_path=None,
        candidate_set_id=None,
        candidate_set_path=None,
        review_id=None,
        review_path=None,
        reviewed_candidate_ids=[],
        next_action=None,
        refinement_handoff_path=None,
        report_path=None,
        supporting_artifacts=[],
        stop_reason=stop_reason,
    )
    atomic_write_record(output_dir / "optimization_publication_receipt.json", receipt)
    return receipt


@dataclass(frozen=True, slots=True)
class OptimizationCandidateSelection:
    receipt: PublicationReceipt
    candidate_set: CandidateSet
    candidate: Candidate
    evidence_snapshot_path: Path
    baseline_surface_manifest_path: Path
    refinement_handoff_path: Path


def _json(path, limit, label):
    value = json.loads(_read_bounded(path, limit, label))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be object")
    return value


def _receipt_artifact_path(receipt_dir: Path, raw_path: str, label: str) -> Path:
    path = Path(raw_path)
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(receipt_dir)
    except ValueError as exc:
        raise ValueError(
            f"{label} is outside the optimization receipt directory"
        ) from exc
    if path.is_symlink() or not resolved.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    return resolved


def load_optimization_candidate(
    *,
    optimization_receipt_path: Path,
    candidate_id: str,
    expected_selected_workflow: str,
    allowed_kinds: Iterable[CandidateKind],
    max_output_bytes: int = 10 * 1024 * 1024,
    max_evidence_bytes: int = 50 * 1024 * 1024,
) -> OptimizationCandidateSelection:
    receipt = PublicationReceipt.model_validate(
        _json(optimization_receipt_path, max_output_bytes, "receipt"), strict=True
    )
    if (
        receipt.status != "accepted"
        or receipt.selected_workflow != expected_selected_workflow
        or candidate_id not in receipt.reviewed_candidate_ids
    ):
        raise ValueError(
            "optimization receipt/candidate is not accepted for selected workflow"
        )
    if not all(
        (
            receipt.candidate_set_path,
            receipt.evidence_snapshot_path,
            receipt.baseline_surface_manifest_path,
            receipt.refinement_handoff_path,
        )
    ):
        raise ValueError("accepted receipt missing paths")
    receipt_dir = optimization_receipt_path.resolve().parent
    candidate_set_path = _receipt_artifact_path(
        receipt_dir, receipt.candidate_set_path, "CandidateSet"
    )
    evidence_path = _receipt_artifact_path(
        receipt_dir, receipt.evidence_snapshot_path, "evidence snapshot"
    )
    baseline_path = _receipt_artifact_path(
        receipt_dir, receipt.baseline_surface_manifest_path, "baseline surface manifest"
    )
    handoff_path = _receipt_artifact_path(
        receipt_dir, receipt.refinement_handoff_path, "refinement handoff"
    )
    cs = read_candidate_set(candidate_set_path, max_output_bytes=max_output_bytes)
    cs.verify_identity()
    if (
        cs.candidate_set_id,
        cs.evidence_snapshot_id,
        cs.baseline_surface_manifest_id,
    ) != (
        receipt.candidate_set_id,
        receipt.evidence_snapshot_id,
        receipt.baseline_surface_manifest_id,
    ):
        raise ValueError("receipt anchors mismatch")
    if cs.selected_workflow != receipt.selected_workflow:
        raise ValueError("CandidateSet selected workflow mismatch")
    matches = [c for c in cs.candidates if c.candidate_id == candidate_id]
    if len(matches) != 1 or matches[0].kind not in set(allowed_kinds):
        raise ValueError("candidate missing, duplicate, or wrong kind")
    from .evidence import read_evidence_snapshot

    _read_bounded(evidence_path, max_evidence_bytes, "evidence snapshot")
    ev = read_evidence_snapshot(evidence_path, max_bytes=max_evidence_bytes)
    if ev.snapshot_id != receipt.evidence_snapshot_id or not ev.verify_identity():
        raise ValueError("evidence anchor mismatch")
    baseline = _json(baseline_path, max_evidence_bytes, "baseline")
    if baseline.get("surface_id") != receipt.baseline_surface_manifest_id:
        raise ValueError("baseline anchor mismatch")
    from .candidate_surfaces import verify_surface_anchor

    baseline_root = Path(str(baseline.get("root", ""))).resolve(strict=True)
    try:
        baseline_root.relative_to(receipt_dir)
    except ValueError as exc:
        raise ValueError(
            "baseline root is outside the optimization receipt directory"
        ) from exc
    boundary = baseline.get("boundary")
    surface_kind = baseline.get("surface_kind")
    if not isinstance(boundary, Mapping) or not isinstance(surface_kind, str):
        raise ValueError("baseline manifest boundary is invalid")
    verify_surface_anchor(
        baseline,
        expected_root=baseline_root,
        expected_boundary=boundary,
        expected_surface_kind=surface_kind,
    )
    handoff = RefinementHandoff.model_validate(
        _json(handoff_path, max_output_bytes, "handoff"), strict=True
    )
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
    if actual_handoff != expected_handoff or not any(
        x.candidate_id == candidate_id and x.kind == matches[0].kind
        for x in handoff.candidates
    ):
        raise ValueError("handoff mismatch")
    if receipt.review_id:
        if not receipt.review_path:
            raise ValueError("accepted reviewed receipt is missing review path")
        review_path = _receipt_artifact_path(
            receipt_dir, receipt.review_path, "candidate review"
        )
        persisted_review = read_candidate_review(
            review_path, max_output_bytes=max_output_bytes
        )
        validate_candidate_review(persisted_review, candidate_set=cs)
        if (
            persisted_review.review_id != receipt.review_id
            or persisted_review.reviewed_candidate_ids != receipt.reviewed_candidate_ids
        ):
            raise ValueError("receipt review anchors mismatch")
    return OptimizationCandidateSelection(
        receipt, cs, matches[0], evidence_path, baseline_path, handoff_path
    )


__all__ = [
    "OptimizationCandidateSelection",
    "build_empty_candidate_set",
    "finalize_candidate_review_payload",
    "finalize_candidate_set_payload",
    "load_optimization_candidate",
    "publish_recommendation",
    "read_candidate_review",
    "read_candidate_set",
    "render_recommendation_report",
    "validate_candidate_review",
    "validate_candidate_set",
    "write_incomplete_receipt",
]
