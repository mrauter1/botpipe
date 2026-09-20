"""Optimizer v2: bounded evidence, one proposal/review pair, deterministic handoff."""

from __future__ import annotations

from dataclasses import asdict

from botpipe import (
    Artifact,
    Prompt,
    Session,
    activity,
    current_run,
    provider_budget,
    workflow,
)
from botpipe_optimizer.evidence import EvidenceSnapshot
from botpipe_optimizer.optimization import SourceManifest, SourceSite
from botpipe_optimizer.records import CandidateReview, CandidateSet, PublicationReceipt

from .contracts import OptimizationWorkflowResult
from .params import Params


@activity(retry_safe=True, name="publish optimizer recommendation")
def _publish_recommendation(
    output_dir: str,
    evidence_snapshot: EvidenceSnapshot,
    candidate_set: CandidateSet,
    review: CandidateReview | None,
    baseline_manifest: dict,
    max_output_bytes: int,
    supporting_content: bytes | None,
) -> PublicationReceipt:
    from botpipe_optimizer.recommendations import publish_recommendation

    return publish_recommendation(
        output_dir=output_dir,
        evidence_snapshot=evidence_snapshot,
        candidate_set=candidate_set,
        review=review,
        baseline_manifest=baseline_manifest,
        max_output_bytes=max_output_bytes,
        supporting_content=supporting_content,
    )


def _allowed_kinds(params: Params) -> set[str]:
    result = {"producer_prompt", "verifier_rubric"}
    if params.include_token_optimization:
        result.add("tokens")
    if params.include_workflow_level_candidates:
        result.add("workflow")
    if params.include_adversarial_generation:
        result.add("evaluation_case")
    return result


@workflow(name="workflow_run_traces_to_optimization_candidates", version="3")
def WorkflowRunTracesToOptimizationCandidates(
    params: Params, request: str = ""
) -> OptimizationWorkflowResult:
    """Recommend only from admitted, objective-eligible durable observations."""
    from botpipe.discovery import resolve_workflow
    from botpipe_optimizer import capture_source_manifest
    from botpipe_optimizer.evidence import capture_evidence_snapshot
    from botpipe_optimizer.recommendations import (
        build_empty_candidate_set,
        validate_candidate_review,
        validate_candidate_set,
    )

    context = current_run()

    def inspect_source():
        from botpipe.provenance import capture_workflow_provenance

        selected = resolve_workflow(params.selected_workflow, context.workspace)
        return {
            "manifest": asdict(capture_source_manifest(selected)),
            "provenance": capture_workflow_provenance(selected, context.workspace),
        }

    manifest_payload = context.operation(
        "optimizer.capture_source_manifest",
        {"workflow_name": params.selected_workflow},
        inspect_source,
        retry_safe=True,
        name="capture optimizer baseline source",
    )
    recorded_manifest = dict(manifest_payload["manifest"])
    recorded_manifest["sites"] = tuple(
        SourceSite(**site) for site in recorded_manifest.get("sites", ())
    )
    recorded_manifest["branch_lines"] = tuple(recorded_manifest.get("branch_lines", ()))
    manifest = SourceManifest(**recorded_manifest)
    provenance = manifest_payload["provenance"]
    baseline_manifest = (
        provenance.get("surface_manifest") or manifest_payload["manifest"]
    )
    baseline_surface_id = provenance.get("surface_id")

    def inspect_selected_runs():
        if params.run_refs:
            inspected = []
            for reference in params.run_refs:
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
            return inspected
        matching = []
        allowed = set(params.run_statuses)
        for summary in context.client.runs():
            record = summary if isinstance(summary, dict) else vars(summary)
            if (
                record.get("workflow_name") or record.get("workflow")
            ) != manifest.workflow_name:
                continue
            if allowed and record.get("status") not in allowed:
                continue
            matching.append(context.client.inspect(str(record["run_id"])))
            if len(matching) >= params.history_limit:
                break
        return matching

    inspections = context.operation(
        "optimizer.observe_runs",
        {
            "selection_reference": params.selected_workflow,
            "canonical_workflow_name": manifest.workflow_name,
            "run_refs": params.run_refs,
            "statuses": params.run_statuses,
            "history_limit": params.history_limit,
        },
        inspect_selected_runs,
        retry_safe=True,
        name="capture optimizer run evidence",
    )
    snapshot = context.operation(
        "optimizer.build_evidence_snapshot",
        {
            "workflow_name": params.selected_workflow,
            "objective": params.objective,
            "top_k_steps": params.top_k_steps,
            "route_tags": params.route_tags,
            "max_evidence_bytes": params.max_evidence_bytes,
        },
        lambda: capture_evidence_snapshot(
            manifest.workflow_name,
            inspections,
            source_manifest=manifest,
            objective=params.objective,
            top_k_steps=params.top_k_steps,
            max_evidence_bytes=params.max_evidence_bytes,
            explicit_run_refs=bool(params.run_refs),
            route_tags=tuple(params.route_tags),
            current_workflow_identity=provenance.get("workflow_identity"),
            current_surface_id=baseline_surface_id,
            current_orchestration_id=provenance.get("orchestration_id"),
            baseline_surface_manifest_id=baseline_surface_id,
        ),
        retry_safe=True,
        name="normalize bounded optimizer evidence",
    )

    review = None
    supporting_content = None
    with provider_budget(
        max_turns=params.max_provider_turns,
        max_seconds=params.max_analysis_seconds,
        turn_timeout_seconds=params.provider_turn_timeout_seconds,
    ) as budget:
        if snapshot.next_action == "propose_changes" and snapshot.shortlist:
            producer = Session(key="optimizer-producer")
            verifier = Session.fresh()
            feedback = None
            while True:
                proposal = producer.run(
                    Prompt.file("prompts/recommendation_producer.md"),
                    input={
                        "request": request,
                        "parameters": params.model_dump(mode="json"),
                        "evidence_snapshot": snapshot.model_dump(mode="json"),
                        "selected_workflow_source_manifest": manifest_payload[
                            "manifest"
                        ],
                        "baseline_surface_manifest": baseline_manifest,
                        "allowed_candidate_kinds": sorted(_allowed_kinds(params)),
                        "max_candidates": params.max_candidates,
                        "review_feedback": feedback,
                    },
                    writes=(
                        Artifact.md(
                            "workflow_optimization_supporting.md",
                            name="workflow_optimization_supporting",
                            required=False,
                        ),
                    ),
                    returns=CandidateSet,
                    name="propose evidence-bound candidates",
                    retries=2,
                )
                candidate_set = validate_candidate_set(
                    proposal.value,
                    evidence_snapshot=snapshot,
                    max_candidates=params.max_candidates,
                    allowed_kinds=_allowed_kinds(params),
                    expected_selected_workflow=manifest.workflow_name,
                    max_output_bytes=params.max_output_bytes,
                )
                if "workflow_optimization_supporting" in proposal.artifacts:
                    supporting_content = (
                        proposal.artifacts.workflow_optimization_supporting.read_bytes()
                    )
                decision = verifier.run(
                    Prompt.file("prompts/recommendation_verifier.md"),
                    input={
                        "request": request,
                        "evidence_snapshot": snapshot.model_dump(mode="json"),
                        "candidate_set": candidate_set.model_dump(
                            mode="json", by_alias=True
                        ),
                        "allowed_candidate_kinds": sorted(_allowed_kinds(params)),
                        "max_candidates": params.max_candidates,
                    },
                    returns=CandidateReview,
                    name="independently review candidate set",
                    retries=2,
                )
                review = validate_candidate_review(
                    decision.value,
                    candidate_set=candidate_set,
                    max_output_bytes=params.max_output_bytes,
                )
                if review.accepted:
                    break
                feedback = review.model_dump(mode="json", by_alias=True)
        else:
            candidate_set = build_empty_candidate_set(
                selected_workflow=manifest.workflow_name,
                evidence_snapshot_id=snapshot.snapshot_id,
                baseline_surface_manifest_id=snapshot.baseline_surface_manifest_id,
                next_action=(
                    "collect_evidence"
                    if snapshot.next_action == "collect_evidence"
                    else "no_change"
                ),
                reason="No objective-eligible evidence was available in the admitted sample.",
            )
        budget_record = budget.snapshot()

    receipt = _publish_recommendation(
        str(context.folder),
        snapshot,
        candidate_set,
        review,
        baseline_manifest,
        params.max_output_bytes,
        supporting_content,
    )
    return OptimizationWorkflowResult(
        summary=(
            f"Published {len(candidate_set.candidates)} evidence-bound candidate(s)."
            if candidate_set.candidates
            else f"Published {candidate_set.next_action}: {candidate_set.no_candidate_reason}"
        ),
        evidence_snapshot=snapshot,
        candidate_set=candidate_set,
        review=review,
        receipt=receipt,
        provider_budget=budget_record,
    )


workflow_callable = WorkflowRunTracesToOptimizationCandidates
__all__ = ["WorkflowRunTracesToOptimizationCandidates", "workflow_callable"]
