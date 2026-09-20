"""Turn durable journal observations into evidence-linked optimization candidates."""

from __future__ import annotations

from botpipe import Session, current_run, workflow
from labs.workflows._shared import LabWorkflowResult, artifact, finish, run_phase

from .contracts import (
    AdversarialCasesPayload,
    CandidatePassPayload,
    FailureScenarioPayload,
    FrameOptimizationPayload,
    OptimizationPackagePayload,
    RankTargetsPayload,
)
from .params import Params


@workflow(name="workflow_run_traces_to_optimization_candidates", version="2")
def WorkflowRunTracesToOptimizationCandidates(
    params: Params, request: str = ""
) -> LabWorkflowResult:
    """Analyze observed operations and explicitly mark declared but unseen paths."""
    from dataclasses import asdict

    from botpipe.discovery import resolve_workflow
    from botpipe_optimizer import capture_source_manifest, optimize_observations

    _producer = Session(key="producer")
    _verifier = Session(key="verifier")
    context = current_run()

    def inspect_selected_runs():
        explicit_ids = [reference.rsplit("/", 1)[-1] for reference in params.run_refs]
        if explicit_ids:
            return [context.client.inspect(run_id) for run_id in explicit_ids]
        matching = []
        allowed = set(params.run_statuses)
        for summary in context.client.runs():
            record = summary if isinstance(summary, dict) else vars(summary)
            if (
                record.get("workflow_name") or record.get("workflow")
            ) != params.selected_workflow:
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
            "workflow_name": params.selected_workflow,
            "run_refs": params.run_refs,
            "statuses": params.run_statuses,
            "history_limit": params.history_limit,
        },
        inspect_selected_runs,
        retry_safe=True,
    )

    def inspect_source():
        selected = resolve_workflow(params.selected_workflow, context.workspace)
        return asdict(capture_source_manifest(selected))

    manifest_payload = context.operation(
        "optimizer.capture_source_manifest",
        {"workflow_name": params.selected_workflow},
        inspect_source,
        retry_safe=True,
    )
    selected = resolve_workflow(params.selected_workflow, context.workspace)
    manifest = capture_source_manifest(selected)
    if asdict(manifest) != manifest_payload:
        raise RuntimeError(
            "selected workflow source changed while optimizer evidence was captured"
        )
    report = optimize_observations(
        manifest.workflow_name,
        inspections,
        source_manifest=manifest,
        limit=params.top_k_steps,
    )
    evidence_ids = {
        operation_id
        for metric in report.metrics
        for operation_id in metric.evidence_operation_ids
    }
    base = {
        "request": request,
        "parameters": params.model_dump(mode="json"),
        "observed_optimization_report": report.to_dict(),
        "candidate_evidence_rule": "Candidates may cite only these operation ids: "
        + ", ".join(sorted(evidence_ids)),
        "unseen_path_rule": "Unseen paths are evidence gaps; do not score them or claim they executed.",
    }
    completed = []
    prior = ()

    def phase(name, prompt, filenames, returns):
        nonlocal prior
        result = run_phase(
            phase=name,
            producer=_producer,
            verifier=_verifier,
            producer_prompt=f"prompts/{prompt}_producer.md",
            verifier_prompt=f"prompts/{prompt}_verifier.md",
            input={
                **base,
                "prior_phases": [
                    item.evidence.model_dump(mode="json") for item in completed
                ],
            },
            reads=prior,
            writes=tuple(artifact(filename) for filename in filenames),
            returns=returns,
        )
        unknown = sorted(
            set(result.evidence.candidate_ids)
            - {candidate.candidate_id for candidate in report.candidates}
        )
        if unknown:
            raise ValueError(
                "provider proposed candidate ids outside the validated ranking: "
                + ", ".join(unknown)
            )
        completed.append(result)
        prior += result.handles
        return result.evidence.details

    framing = phase(
        "frame_observed_optimization",
        "frame",
        [
            "workflow_optimization_scope.json",
            "observed_trace_corpus.json",
            "selected_workflow_source_manifest.json",
        ],
        FrameOptimizationPayload,
    )
    if evidence_ids and framing["next_action"] != "package_only":
        ranking = phase(
            "rank_observed_targets",
            "rank_targets",
            [
                "step_optimization_priority_report.json",
                "step_trace_metrics.json",
            ],
            RankTargetsPayload,
        )
        if ranking["next_action"] != "package_only":
            failures = phase(
                "mine_observed_failures",
                "mine_failures",
                [
                    "workflow_failure_scenarios.json",
                ],
                FailureScenarioPayload,
            )
            if failures["failure_ids"]:
                phase(
                    "optimize_producer_contracts",
                    "optimize_producer",
                    [
                        "producer_prompt_optimization_candidates.json",
                    ],
                    CandidatePassPayload,
                )
                phase(
                    "optimize_verifier_rubrics",
                    "optimize_verifier_rubric",
                    [
                        "verifier_rubric_optimization_candidates.json",
                    ],
                    CandidatePassPayload,
                )
            if params.include_token_optimization:
                phase(
                    "optimize_tokens",
                    "optimize_tokens",
                    [
                        "token_optimization_candidates.json",
                    ],
                    CandidatePassPayload,
                )
            if params.include_adversarial_generation:
                phase(
                    "generate_adversarial_cases",
                    "adversarial_cases",
                    [
                        "adversarial_case_candidates.json",
                    ],
                    AdversarialCasesPayload,
                )
            if params.include_workflow_level_candidates:
                phase(
                    "optimize_workflow_boundary",
                    "workflow_level",
                    [
                        "workflow_level_optimization_candidates.json",
                    ],
                    CandidatePassPayload,
                )
    phase(
        "package_validated_candidates",
        "package",
        [
            "workflow_optimization_scorecard.json",
            "optimization_next_actions.md",
        ],
        OptimizationPackagePayload,
    )
    return finish("workflow_run_traces_to_optimization_candidates", completed)


workflow_callable = WorkflowRunTracesToOptimizationCandidates
__all__ = ["WorkflowRunTracesToOptimizationCandidates", "workflow_callable"]
