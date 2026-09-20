"""Optimizer v2: deterministic capture, one producer/verifier pair, deterministic publication."""

from __future__ import annotations
import hashlib, json, os, shutil, stat, tempfile
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from botpipe import (
    FINISH,
    Prompt,
    Route,
    Session,
    Workflow,
    produce_verify_step,
    python_step,
)
from botpipe.core import Artifact
from botpipe.core.compiler import compile_workflow
from botpipe.core.providers import current_provider_dispatch_budget
from botpipe.core.surface_identity import (
    canonical_workflow_identity,
    derive_workflow_surface_manifest,
)
from botpipe.runtime.inspection import (
    inspect_resolved_workflow,
    resolve_workflow_reference,
    selected_workflow_authoring_surface_payload,
)
from botpipe.stdlib import (
    open_workflow_sessions,
    write_invocation_contract,
    write_workflow_json,
)
from botpipe_optimizer.candidate_surfaces import (
    derive_surface_manifest,
    verify_surface_anchor,
)
from botpipe_optimizer.evidence import (
    EvidenceSnapshot,
    capture_evidence_snapshot,
    read_evidence_snapshot,
    write_evidence_snapshot,
)
from botpipe_optimizer.optimization import list_selected_workflow_runs
from botpipe_optimizer.recommendations import (
    build_empty_candidate_set,
    publish_recommendation,
    read_candidate_review,
    read_candidate_set,
    validate_candidate_review,
    validate_candidate_set,
    write_incomplete_receipt,
)
from botpipe_optimizer.records import CandidateReview, CandidateSet
from .contracts import RECOMMENDATION_ROUTES, RecommendationControl

KIND = "workflow"
MAX_FILES = 100000
MAX_BYTES = 512 * 1024 * 1024


def _read_bounded(path, limit, label):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{label} must be a regular non-symlink file") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise ValueError(f"{label} exceeds its regular-file byte limit")
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
            raise ValueError(f"{label} exceeds its byte limit")
        return content
    finally:
        os.close(descriptor)


def _json(path, limit=MAX_BYTES):
    v = json.loads(_read_bounded(path, limit, path.name))
    if not isinstance(v, dict):
        raise ValueError(f"{path.name} must contain an object")
    return v


def _runtime_surface(capability, root):
    manifest = derive_workflow_surface_manifest(root, capability)
    sources = [
        {"relative_path": e["relative_path"], "source_path": e["surface_path"]}
        for e in manifest["files"]
    ]
    return dict(manifest["boundary"]), sources, manifest


def _copy_baseline(folder, boundary, sources):
    parent = folder / "baseline_snapshots"
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="surface-", dir=parent))
    if len(sources) > MAX_FILES:
        raise ValueError("baseline exceeds file limit")
    total = 0
    source_map = {}
    for e in sources:
        rel = e["relative_path"]
        src = Path(e["source_path"]).resolve(strict=True)
        if src.is_symlink() or not src.is_file():
            raise ValueError(f"baseline source is not a regular file: {rel}")
        total += src.stat().st_size
        if total > MAX_BYTES:
            raise ValueError("baseline exceeds byte limit before copy")
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst, follow_symlinks=False)
        source_map[rel] = src
    return derive_surface_manifest(
        root,
        expected_root=root,
        boundary=boundary,
        surface_kind=KIND,
        authoritative_sources=source_map,
    )


def _source_anchor(sources):
    out = {}
    remaining = MAX_BYTES
    for e in sources:
        p = Path(e["source_path"]).resolve(strict=True)
        content = _read_bounded(
            p, remaining, f"authoritative source {e['relative_path']}"
        )
        remaining -= len(content)
        out[e["relative_path"]] = {
            "source_path": str(p),
            "sha256": hashlib.sha256(content).hexdigest(),
            "executable": (
                bool(p.stat().st_mode & 0o111) if os.name == "posix" else False
            ),
        }
    return out


def _checkpoint(inv, evidence, surface, sources):
    stable = {
        relative: {"sha256": entry["sha256"], "executable": entry["executable"]}
        for relative, entry in sources.items()
    }
    return hashlib.sha256(
        json.dumps(
            {
                "invocation": inv,
                "evidence": evidence,
                "surface": surface,
                "sources": stable,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _invocation_id(params, request_path, selected_workflow):
    request_sha = hashlib.sha256(
        _read_bounded(Path(request_path), MAX_BYTES, "optimizer request")
    ).hexdigest()
    payload = {
        "selected_workflow": selected_workflow,
        "params": params.model_dump(
            mode="json", exclude={"optimization_depth", "max_candidates_per_pass"}
        ),
        "request_sha256": request_sha,
    }
    return (
        "invocation-"
        + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def _allowed(params):
    kinds = {"producer_prompt", "verifier_rubric"}
    if params.include_token_optimization:
        kinds.add("tokens")
    if params.include_workflow_level_candidates:
        kinds.add("workflow")
    if params.include_adversarial_generation:
        kinds.add("evaluation_case")
    return kinds


def _admit_model_outputs(ctx, *, include_review: bool) -> None:
    paths = [ctx.artifacts.workflow_optimization_candidates.path]
    supporting = ctx.artifacts.workflow_optimization_supporting.path
    review = ctx.artifacts.workflow_optimization_candidate_review.path
    if supporting.exists():
        paths.append(supporting)
    if include_review and review.exists():
        paths.append(review)
    total = 0
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"model output must be a regular file: {path.name}")
        total += path.stat().st_size
        if total > ctx.params.max_output_bytes:
            raise ValueError("model outputs exceed max_output_bytes")


def _verify(ctx):
    evidence = read_evidence_snapshot(ctx.artifacts.workflow_optimization_evidence.path)
    manifest = _json(ctx.artifacts.baseline_surface_manifest.path)
    current_invocation = _invocation_id(
        ctx.params, ctx.artifacts.request.path, ctx.state.selected_workflow_name
    )
    invocation_contract = _json(ctx.artifacts.invocation_contract.path)
    if (
        current_invocation != ctx.state.invocation_identity
        or invocation_contract.get("invocation_identity") != current_invocation
    ):
        raise ValueError("incompatible optimizer invocation; start a new analysis")
    if evidence.snapshot_id != ctx.state.evidence_snapshot_id:
        raise ValueError("baseline/evidence changed; start a new analysis")
    sid = verify_surface_anchor(
        manifest,
        expected_root=Path(ctx.state.baseline_root),
        expected_boundary=ctx.state.baseline_boundary,
        expected_surface_kind=KIND,
    )
    if (
        sid != ctx.state.baseline_surface_manifest_id
        or evidence.baseline_surface_manifest_id != sid
    ):
        raise ValueError("baseline/evidence changed; start a new analysis")
    resolved = resolve_workflow_reference(ctx.root, ctx.params.selected_workflow)
    capability = inspect_resolved_workflow(ctx.root, resolved)
    boundary, sources, current = _runtime_surface(capability, ctx.root.resolve())
    current_paths = {
        e["relative_path"]: str(Path(e["source_path"]).resolve()) for e in sources
    }
    if (
        boundary != ctx.state.baseline_boundary
        or current["surface_id"] != sid
        or current_paths
        != {k: v["source_path"] for k, v in ctx.state.authoritative_sources.items()}
    ):
        raise ValueError("baseline/evidence changed; start a new analysis")
    remaining_source_bytes = MAX_BYTES
    for relative_path, e in ctx.state.authoritative_sources.items():
        p = Path(e["source_path"])
        content = _read_bounded(
            p, remaining_source_bytes, f"authoritative source {relative_path}"
        )
        remaining_source_bytes -= len(content)
        if hashlib.sha256(content).hexdigest() != e["sha256"] or (
            (bool(p.stat().st_mode & 0o111) if os.name == "posix" else False)
            != e["executable"]
        ):
            raise ValueError("baseline/evidence changed; start a new analysis")
    cp = _json(ctx.artifacts.optimizer_checkpoint.path)
    expected = _checkpoint(
        ctx.state.invocation_identity,
        evidence.snapshot_id,
        sid,
        ctx.state.authoritative_sources,
    )
    if (
        cp.get("checkpoint_id") != expected
        or cp.get("invocation_identity") != current_invocation
        or cp.get("baseline_root") != ctx.state.baseline_root
        or cp.get("authoritative_sources") != ctx.state.authoritative_sources
    ):
        raise ValueError("incompatible checkpoint; start a new analysis")
    return evidence, manifest


def _validate(ctx, candidate_set, evidence, manifest, cap):
    return validate_candidate_set(
        candidate_set,
        evidence_snapshot=evidence,
        max_candidates=cap,
        allowed_kinds=_allowed(ctx.params),
        expected_selected_workflow=ctx.state.selected_workflow_name,
        allowed_target_paths=manifest["relative_paths"],
        allowed_target_prefixes=(
            ctx.state.baseline_boundary["package_root_relative_path"],
        ),
    )


def _after_review(ctx):
    try:
        evidence, manifest = _verify(ctx)
        _admit_model_outputs(ctx, include_review=True)
        cs = read_candidate_set(
            ctx.artifacts.workflow_optimization_candidates.path,
            max_output_bytes=ctx.params.max_output_bytes,
        )
        review = read_candidate_review(
            ctx.artifacts.workflow_optimization_candidate_review.path,
            max_output_bytes=ctx.params.max_output_bytes,
        )
        cap = (
            ctx.params.max_candidates
            if ctx.outcome.tag == "recommendations_reviewed"
            else max(ctx.params.max_candidates, len(cs.candidates))
        )
        _validate(ctx, cs, evidence, manifest, cap)
        validate_candidate_review(review, candidate_set=cs)
        if (ctx.outcome.tag == "recommendations_reviewed") != review.accepted:
            raise ValueError("review decision and route disagree")
        if review.accepted:
            ctx.state.review_id = review.review_id
            ctx.state.reviewed_candidate_ids = review.reviewed_candidate_ids
    except Exception as exc:
        write_incomplete_receipt(
            output_dir=ctx.workflow_folder,
            selected_workflow=ctx.state.selected_workflow_name or "unknown",
            evidence_snapshot_id=ctx.state.evidence_snapshot_id,
            stop_reason=str(exc),
        )
        raise


class _FailureReceiptExtension:
    def bind(self, binding):
        class Bound:
            def before_step(self, event):
                return None

            def after_step(self, event):
                return None

            def on_terminal(self, event):
                return None

            def on_fatal(self, event, error):
                state = event.state
                selected = getattr(state, "selected_workflow_name", None) or "unknown"
                evidence = getattr(state, "evidence_snapshot_id", None)
                kind = (
                    getattr(getattr(error, "failure_context", None), "kind", None)
                    or type(error).__name__
                )
                write_incomplete_receipt(
                    output_dir=binding.workflow_folder,
                    selected_workflow=selected,
                    evidence_snapshot_id=evidence,
                    stop_reason=f"{kind}: {error}",
                )

        return Bound()


class WorkflowRunTracesToOptimizationCandidates(Workflow):
    name = "workflow_run_traces_to_optimization_candidates"

    class State(BaseModel):
        selected_workflow_name: str | None = None
        invocation_identity: str | None = None
        evidence_snapshot_id: str | None = None
        baseline_surface_manifest_id: str | None = None
        baseline_root: str = ""
        baseline_boundary: dict[str, Any] = Field(default_factory=dict)
        authoritative_sources: dict[str, dict[str, Any]] = Field(default_factory=dict)
        review_id: str | None = None
        reviewed_candidate_ids: list[str] = Field(default_factory=list)
        published: bool = False

    recommendation_session = Session()
    verifier_session = Session.fresh()
    extensions = (_FailureReceiptExtension(),)
    request = Artifact("{{ run.folder }}/request.md")
    invocation_contract = Artifact.json(
        "{{ workflow.folder }}/invocation_contract.json"
    )
    selected_workflow_authoring_surface = Artifact.json(
        "{{ workflow.folder }}/selected_workflow_authoring_surface.json"
    )
    baseline_surface_manifest = Artifact.json(
        "{{ workflow.folder }}/baseline_surface_manifest.json"
    )
    workflow_optimization_evidence = Artifact.json(
        "{{ workflow.folder }}/workflow_optimization_evidence.json"
    )
    optimizer_checkpoint = Artifact.json(
        "{{ workflow.folder }}/optimizer_checkpoint.json"
    )
    workflow_optimization_candidates = Artifact.json(
        "{{ workflow.folder }}/workflow_optimization_candidates.json",
        schema=CandidateSet,
    )
    workflow_optimization_supporting = Artifact.md(
        "{{ workflow.folder }}/workflow_optimization_supporting.md"
    )
    workflow_optimization_candidate_review = Artifact.json(
        "{{ workflow.folder }}/workflow_optimization_candidate_review.json",
        schema=CandidateReview,
    )
    workflow_optimization_report = Artifact.md(
        "{{ workflow.folder }}/workflow_optimization_report.md"
    )
    workflow_refinement_evidence = Artifact.json(
        "{{ workflow.folder }}/workflow_refinement_evidence.json"
    )
    optimization_publication_receipt = Artifact.json(
        "{{ workflow.folder }}/optimization_publication_receipt.json"
    )
    recommend = produce_verify_step(
        producer_prompt=Prompt.file("prompts/recommendation_producer.md"),
        verifier_prompt=Prompt.file("prompts/recommendation_verifier.md"),
        session=recommendation_session,
        verifier_session=verifier_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_authoring_surface,
            baseline_surface_manifest,
            workflow_optimization_evidence,
        ],
        producer_writes=[
            workflow_optimization_candidates,
            workflow_optimization_supporting,
        ],
        verifier_writes=[workflow_optimization_candidate_review],
        control_schema=RecommendationControl,
        routes=RECOMMENDATION_ROUTES,
        after_verifier=_after_review,
    )

    @python_step(
        name="capture",
        requires=[request],
        writes=[
            invocation_contract,
            selected_workflow_authoring_surface,
            baseline_surface_manifest,
            workflow_optimization_evidence,
            optimizer_checkpoint,
            workflow_optimization_candidates,
            optimization_publication_receipt,
        ],
        routes={
            "evidence_ready": Route.to(
                "recommend",
                summary="Frozen eligible evidence is ready.",
                required_writes=(
                    "invocation_contract",
                    "selected_workflow_authoring_surface",
                    "baseline_surface_manifest",
                    "workflow_optimization_evidence",
                    "optimizer_checkpoint",
                    "optimization_publication_receipt",
                ),
            ),
            "no_actionable_evidence": Route.to(
                "publish_recommendation",
                summary="Publish an evidence action with zero model calls.",
                required_writes=(
                    "invocation_contract",
                    "selected_workflow_authoring_surface",
                    "baseline_surface_manifest",
                    "workflow_optimization_evidence",
                    "optimizer_checkpoint",
                    "workflow_optimization_candidates",
                    "optimization_publication_receipt",
                ),
            ),
        },
    )
    def capture(ctx):
        p = ctx.params
        resolved = resolve_workflow_reference(ctx.root, p.selected_workflow)
        capability = inspect_resolved_workflow(ctx.root, resolved)
        name = resolved.reference.workflow_name
        # Replace any stale success marker before validation so a failed new
        # invocation can never leave an older accepted receipt consumable.
        write_incomplete_receipt(
            output_dir=ctx.workflow_folder,
            selected_workflow=name,
            stop_reason="validating_inputs",
        )
        try:
            runs = list_selected_workflow_runs(
                ctx.root,
                name,
                run_refs=p.run_refs,
                run_statuses=p.run_statuses,
                history_limit=p.history_limit,
            )
        except Exception as exc:
            write_incomplete_receipt(
                output_dir=ctx.workflow_folder,
                selected_workflow=name,
                stop_reason=f"invalid_input: {exc}",
            )
            raise
        for stale in (
            ctx.artifacts.workflow_optimization_candidates.path,
            ctx.artifacts.workflow_optimization_supporting.path,
            ctx.artifacts.workflow_optimization_candidate_review.path,
            ctx.artifacts.workflow_optimization_report.path,
            ctx.artifacts.workflow_refinement_evidence.path,
        ):
            stale.unlink(missing_ok=True)
        write_incomplete_receipt(
            output_dir=ctx.workflow_folder,
            selected_workflow=name,
            stop_reason="analysis_in_progress",
        )
        authoring = selected_workflow_authoring_surface_payload(capability)
        boundary, sources, authoritative = _runtime_surface(
            capability, ctx.root.resolve()
        )
        manifest = _copy_baseline(ctx.workflow_folder, boundary, sources)
        if manifest["surface_id"] != authoritative["surface_id"]:
            raise ValueError("captured baseline does not match runtime surface")
        write_workflow_json(
            ctx,
            "selected_workflow_authoring_surface.json",
            {
                "schema": "botpipe.workflow_authoring_surface/v2",
                "selected_workflow": name,
                "surface": authoring,
            },
        )
        write_workflow_json(ctx, "baseline_surface_manifest.json", manifest)
        compiled = compile_workflow(resolved.workflow_cls)
        workflow_identity = canonical_workflow_identity(
            resolved.reference, workflow_name=compiled.workflow_name
        )
        snapshot = capture_evidence_snapshot(
            ctx.root,
            name,
            runs,
            ctx.workflow_folder / "evidence_snapshot",
            route_tags=p.route_tags,
            objective=p.objective,
            top_k_steps=p.top_k_steps,
            max_evidence_bytes=p.max_evidence_bytes,
            explicit_run_refs=bool(p.run_refs),
            current_workflow_identity=workflow_identity,
            current_surface_manifest_id=manifest["surface_id"],
            current_topology_id=compiled.topology_hash,
        )
        write_evidence_snapshot(
            snapshot, ctx.artifacts.workflow_optimization_evidence.path
        )
        invocation = _invocation_id(p, ctx.artifacts.request.path, name)
        anchor = _source_anchor(sources)
        cid = _checkpoint(
            invocation, snapshot.snapshot_id, manifest["surface_id"], anchor
        )
        write_invocation_contract(
            ctx,
            {
                "schema": "botpipe.workflow_optimization.invocation/v2",
                "invocation_identity": invocation,
                "selected_workflow": name,
                **p.model_dump(
                    mode="json",
                    exclude={"optimization_depth", "max_candidates_per_pass"},
                ),
            },
        )
        budget = current_provider_dispatch_budget()
        write_workflow_json(
            ctx,
            "optimizer_checkpoint.json",
            {
                "schema": "botpipe.workflow_optimization.checkpoint/v2",
                "checkpoint_id": cid,
                "invocation_identity": invocation,
                "baseline_root": manifest["root"],
                "authoritative_sources": anchor,
                "provider_budget": None if budget is None else budget.snapshot(),
            },
        )
        ctx.state.selected_workflow_name = name
        ctx.state.invocation_identity = invocation
        ctx.state.evidence_snapshot_id = snapshot.snapshot_id
        ctx.state.baseline_surface_manifest_id = manifest["surface_id"]
        ctx.state.baseline_root = manifest["root"]
        ctx.state.baseline_boundary = boundary
        ctx.state.authoritative_sources = anchor
        open_workflow_sessions(ctx, "recommendation_session", "verifier_session")
        if snapshot.next_action == "propose_changes" and snapshot.shortlist:
            return "evidence_ready"
        empty = build_empty_candidate_set(
            selected_workflow=name,
            evidence_snapshot_id=snapshot.snapshot_id,
            baseline_surface_manifest_id=manifest["surface_id"],
            next_action=(
                "collect_evidence"
                if snapshot.next_action == "collect_evidence"
                else "no_change"
            ),
            reason="No objective-eligible evidence was available in the admitted sample.",
        )
        write_workflow_json(
            ctx,
            "workflow_optimization_candidates.json",
            empty.model_dump(mode="json", by_alias=True),
        )
        return "no_actionable_evidence"

    @python_step(
        name="publish_recommendation",
        requires=[
            invocation_contract,
            baseline_surface_manifest,
            workflow_optimization_evidence,
            optimizer_checkpoint,
            workflow_optimization_candidates,
        ],
        reads=[
            workflow_optimization_candidate_review,
            workflow_optimization_supporting,
        ],
        writes=[
            workflow_optimization_report,
            workflow_refinement_evidence,
            optimization_publication_receipt,
        ],
        routes={
            "published": Route.to(
                FINISH,
                summary="Recommendation and handoff committed.",
                required_writes=(
                    "workflow_optimization_report",
                    "workflow_refinement_evidence",
                    "optimization_publication_receipt",
                ),
            )
        },
    )
    def publish_recommendation(ctx):
        try:
            budget = current_provider_dispatch_budget()
            remaining = None if budget is None else budget.remaining_seconds()
            if remaining is not None and remaining <= 0:
                raise ValueError("optimizer deadline exhausted before publication")
            evidence, manifest = _verify(ctx)
            _admit_model_outputs(ctx, include_review=True)
            cs = read_candidate_set(
                ctx.artifacts.workflow_optimization_candidates.path,
                max_output_bytes=ctx.params.max_output_bytes,
            )
            _validate(ctx, cs, evidence, manifest, ctx.params.max_candidates)
            review = None
            rpath = ctx.artifacts.workflow_optimization_candidate_review.path
            if rpath.is_file():
                review = read_candidate_review(
                    rpath, max_output_bytes=ctx.params.max_output_bytes
                )
                validate_candidate_review(review, candidate_set=cs)
            supporting = ctx.artifacts.workflow_optimization_supporting.path
            supporting_paths = [supporting] if supporting.is_file() else []

            def before_commit():
                active = current_provider_dispatch_budget()
                left = None if active is None else active.remaining_seconds()
                if left is not None and left <= 0:
                    raise ValueError(
                        "optimizer deadline exhausted before receipt commit"
                    )

            receipt = publish_recommendation(
                output_dir=ctx.workflow_folder,
                evidence_snapshot_path=ctx.artifacts.workflow_optimization_evidence.path,
                baseline_surface_manifest_path=ctx.artifacts.baseline_surface_manifest.path,
                evidence_snapshot=evidence,
                candidate_set=cs,
                review=review,
                max_output_bytes=ctx.params.max_output_bytes,
                max_evidence_bytes=ctx.params.max_evidence_bytes,
                candidate_set_source_path=ctx.artifacts.workflow_optimization_candidates.path,
                review_source_path=rpath if review is not None else None,
                supporting_artifact_paths=supporting_paths,
                expected_baseline_root=Path(ctx.state.baseline_root),
                expected_baseline_boundary=ctx.state.baseline_boundary,
                expected_baseline_kind=KIND,
                expected_authoritative_sources=ctx.state.authoritative_sources,
                before_commit=before_commit,
            )
            ctx.state.published = receipt.status == "accepted"
            return "published"
        except Exception as exc:
            write_incomplete_receipt(
                output_dir=ctx.workflow_folder,
                selected_workflow=ctx.state.selected_workflow_name or "unknown",
                evidence_snapshot_id=ctx.state.evidence_snapshot_id,
                stop_reason=str(exc),
            )
            raise

    entry = capture


__all__ = ["WorkflowRunTracesToOptimizationCandidates"]
