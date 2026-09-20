# Workflow run traces to optimization candidates

This candidate-only workflow captures bounded run evidence and the selected workflow's exact baseline surface, runs one producer turn plus one independent verifier turn, and deterministically publishes recommendations. It never executes, refines, evaluates, or promotes the selected workflow. If no objective-eligible evidence exists it makes zero provider calls and publishes a `collect_evidence` or `no_change` result.

```bash
botpipe run labs/workflows/workflow_run_traces_to_optimization_candidates "Diagnose devloop" --task review-1 \
  -wf selected_workflow devloop -wf task_title "Diagnose devloop" \
  -wf objective reliability
```

The default limits are 25 runs, one shortlisted step, three total candidates, six provider dispatches, 600 seconds per provider turn, 1800 seconds overall, 50 MiB of evidence, and 10 MiB of recommendation output. `objective` is `reliability`, `token_usage`, or `latency`. Empty `route_tags` means no route filter. Kind flags restrict the single CandidateSet; they do not add passes.

`max_candidates_per_pass` maps to the total `max_candidates` cap with a warning; conflicting values fail. Deprecated `optimization_depth=cheap|standard` maps only to dispatch/deadline limits (6/1800 or 12/3600). `ablation` remains planning-only.

Canonical outputs are:

- `workflow_optimization_evidence.json`
- `baseline_surface_manifest.json`
- `workflow_optimization_candidates.json`
- `workflow_optimization_candidate_review.json` when model review ran
- `workflow_optimization_report.md`
- `workflow_refinement_evidence.json`
- `optimization_publication_receipt.json`, written last as the commit marker

To implement one reviewed workflow/prompt/token/rubric proposal, pass `optimization_receipt_path` and its exact `candidate_id` to `workflow_and_eval_to_refined_workflow_package`. Evaluation-case candidates go to `workflow_to_eval_suite`. Recommendation receipts always say `improvement = not_evaluated`.

Resume rehashes the frozen evidence and baseline and preserves the runtime provider budget. Baseline/evidence drift or an incompatible old checkpoint requires a new analysis. Historical v1 receipts remain historical evidence and are not upgraded.
