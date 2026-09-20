# Optimizer

Botpipe's optimizer turns recorded workflow runs into evidence-bound recommendations. It does not edit, execute, or promote the selected workflow. A separate refinement run materializes one selected candidate, validates its exact files, and can optionally compare it with the baseline by running a frozen evaluator once per arm.

## Diagnose a workflow

Run the bundled optimizer workflow with the workflow to inspect:

```bash
botpipe run labs/workflows/workflow_run_traces_to_optimization_candidates \
  "Diagnose recent runs and recommend the next useful action" \
  --task optimizer-review-1 \
  -wf selected_workflow release_review \
  -wf task_title "Diagnose release review" \
  -wf objective reliability
```

`selected_workflow` accepts the same named, file, module, and explicit-class references as `botpipe run`. By default the optimizer considers the latest 25 completed or paused runs for that workflow. Use `run_refs` for an explicit historical investigation, `run_statuses` to restrict run status, and `route_tags` to focus the observations while retaining necessary context.

The objectives rank observed burden:

| Objective | Eligible evidence | Ordering |
|---|---|---|
| `reliability` | Explicit runtime failure or rework | Distinct affected runs, then deterministic ties |
| `token_usage` | Complete, positive dispatch usage | Known reported token total |
| `latency` | Complete, positive recorded time | Recorded elapsed seconds |

These rankings do not estimate probability, monetary cost, reducibility, or future benefit. If no eligible evidence exists, the workflow makes no model call and publishes a `collect_evidence` or `no_change` action.

## Defaults and limits

| Parameter | Default | Meaning |
|---|---:|---|
| `history_limit` | 25 | Runs considered before evidence admission |
| `top_k_steps` | 1 | Total shortlisted steps in the selected group |
| `max_candidates` | 3 | Total accepted candidates |
| `max_provider_turns` | 6 | Shared transport-dispatch cap, including retries and repair |
| `provider_turn_timeout_seconds` | 600 | Maximum time for one provider dispatch |
| `max_analysis_seconds` | 1800 | Overall recommendation deadline |
| `max_evidence_bytes` | 50 MiB | Admitted metadata, trace, provenance, topology, and copied raw evidence |
| `max_output_bytes` | 10 MiB | Accepted candidate and supporting-artifact bytes |

`include_adversarial_generation`, `include_token_optimization`, and `include_workflow_level_candidates` restrict allowed candidate kinds. They do not add automatic model stages. The normal evidence-backed path uses one producer turn and one independent verifier turn, with bounded retry or repair only when needed.

Budget reservations are persisted before dispatch. Resume keeps consumed turns and the non-extending deadline. A stale evidence snapshot, changed baseline, changed invocation, clock rollback, or incompatible budget rejects resume and requires a new analysis.

## Outputs

The optimizer's canonical outputs live in its workflow folder:

- `workflow_optimization_evidence.json`: admitted runs, observations, coverage gaps, comparable groups, metrics, and shortlist
- `workflow_optimization_candidates.json`: typed candidate set or an explicit evidence/no-change action
- `workflow_optimization_candidate_review.json`: independent review when a proposal was made
- `workflow_optimization_report.md`: deterministic human-readable projection
- `workflow_refinement_evidence.json`: deterministic handoff for downstream work
- `optimization_publication_receipt.json`: final commit record for the accepted recommendation, or an incomplete status and stop reason

The recommendation receipt always reports `improvement = not_evaluated`. Expected effects and validation plans are hypotheses until a concrete candidate is validated and, when requested, compared against the baseline.

## Hand off one candidate

Choose exactly one `candidate_id` from an accepted receipt. Prompt, rubric, token, and workflow candidates enter the refinement workflow:

```bash
botpipe run labs/workflows/workflow_and_eval_to_refined_workflow_package \
  "Materialize and validate the selected optimizer candidate" \
  --task refinement-1 \
  -wf selected_workflow release_review \
  -wf task_title "Refine release review" \
  -wf optimization_receipt_path .botpipe/tasks/optimizer-review-1/.../optimization_publication_receipt.json \
  -wf candidate_id candidate-abc123
```

The refinement entry point also retains its legacy pair, `evaluation_summary_path` plus `evaluation_findings_path`. Supply one complete input form. Mixing the optimizer handoff with the legacy pair, omitting half of either pair, selecting an unknown candidate, or changing the selected workflow fails before refinement.

An `evaluation_case` candidate does not enter workflow refinement. Pass it to `workflow_to_eval_suite`, which validates workflow parameters, stable case IDs, and expected artifacts and publishes a new evaluation-suite identity. Cases created from diagnosed failures are development cases; they do not modify a frozen comparison suite.

Concrete validation captures the project and any selected installed package layer, builds private baseline and candidate execution trees, overlays only allowed candidate paths, and compiles/tests the staged candidate. The validation receipt derives changes and results from those trees. It does not trust model-authored file counts, hashes, or success claims.

## Optional paired evaluation

Set `evaluation_spec_path` on the refinement run to request measured comparison. Omit it to skip paired execution. The harness freezes the spec, evaluator, cases, ordered case IDs, repetitions, settings, metrics, thresholds, and limits before either arm starts. It launches exactly one evaluator subprocess for the baseline and one for the candidate in separate execution trees and never promotes a candidate automatically.

An evaluation spec uses this shape:

```json
{
  "schema": "botpipe.optimizer.evaluation_spec/v1",
  "evaluator_argv": ["python", "{evaluator_path}"],
  "evaluator_path": "evaluate.py",
  "evaluator_content_id": "sha256:...",
  "case_input_path": "cases.json",
  "case_input_content_id": "sha256:...",
  "case_ids": ["case-001", "case-002"],
  "repetitions": 1,
  "effective_settings": {},
  "metrics": [
    {
      "name": "quality",
      "unit": "score",
      "direction": "higher_is_better",
      "aggregation": "mean",
      "minimum_improvement": 0.1,
      "maximum_regression": 0.0
    }
  ],
  "primary_metric": "quality",
  "guardrail_metrics": [],
  "claim_scope": "development_cases",
  "evaluator_kind": "external",
  "max_elapsed_seconds": 1200,
  "per_arm_timeout_seconds": 600,
  "max_evaluation_output_bytes": 52428800,
  "max_evaluation_output_files": 10000
}
```

The evaluator receives absolute `BOTPIPE_EVAL_REQUEST` and `BOTPIPE_EVAL_RESULT` paths. The request identifies the opaque execution, surface, execution tree, frozen spec and case input, ordered case/repetition plan, effective settings, output directory, and remaining limits. The evaluator atomically writes one strict result:

```json
{
  "schema": "botpipe.optimizer.eval_result/v1",
  "execution_id": "...",
  "surface_id": "...",
  "spec_id": "...",
  "cases": [
    {
      "case_id": "case-001",
      "repetition": 1,
      "outcome": "scored",
      "metrics": {"quality": 0.85},
      "evidence_paths": [],
      "usage_availability": "not_attempted",
      "elapsed_seconds": 1.2
    }
  ]
}
```

There must be exactly one result for every planned `(case_id, repetition)` pair, in order. Required metrics must be finite numbers. Evidence must be regular, non-symlink files inside the allowed output directory. A crash, timeout, cancellation, exhausted budget, nonzero exit, stale or missing result, identity mismatch, duplicate or unknown case pair, NaN/infinity, missing metric, oversized output, or source mutation makes the comparison incomplete and cannot produce `improved`.

Metrics support `mean` and `sum`. Improvement is normalized so positive is better regardless of metric direction. Any primary or guardrail regression beyond its threshold yields `regressed`; otherwise meeting the primary minimum yields `improved`; otherwise the result is `no_material_change`. Incompatible settings or incomplete evidence yields `inconclusive`. Development cases remain labeled `development_cases`; a separate withheld suite may use `evaluation_cases`.

For `evaluator_kind = "botpipe"`, set `max_provider_turns_per_arm`. The evaluator must initialize and reuse the supplied budget across all cases, retries, and repair calls and report its budget record. External evaluators receive the process deadline and output limits but cannot claim an internal provider-turn cap.

## Migration

- `max_candidates_per_pass` is deprecated. Use `max_candidates`, which is one total cap. Conflicting values fail.
- `optimization_depth` is deprecated. `cheap` maps to 6 turns/1800 seconds and `standard` to 12/3600 while retaining the same single proposal/review topology. `ablation` is planning-only. Supply `evaluation_spec_path` for a measured comparison.
- v1 receipts and candidate artifacts remain historical evidence. They are not upgraded into v2 proof; validate the candidate again to produce current identities and results.
- Incompatible in-progress checkpoints fail with a restart instruction. The optimizer does not refresh a changed evidence or baseline anchor during resume.
- `workflow_refinement_evidence.json` remains the downstream handoff name, now as a deterministic v2 projection tied to the evidence, candidate set, and baseline IDs.

The complete normative requirements and acceptance cases are in [Optimizer v2 requirements](requirements/optimizer-v2.md).
