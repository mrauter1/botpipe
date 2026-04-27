# `workflow_run_traces_to_optimization_candidates`

`workflow_run_traces_to_optimization_candidates` is a bundled authoring-only workflow that consumes runtime-owned trace evidence from completed runs and publishes candidate-only optimization artifacts plus `workflow_refinement_evidence.json`. It does not mutate the selected workflow source, does not run the selected workflow by default, and does not execute ablations.

## Problem and value

- Problem solved: turn completed run evidence into explicit optimization candidates instead of scattered postmortem notes and ad hoc prompt tweaks.
- Why it matters: once runtime observability is durable, the next leverage point is ranking where a workflow is weak and packaging proposed improvements without silently applying them.
- Classification: reusable workflow building block.
- Why Autoloop fits: the work needs deterministic evidence ingestion, verifier-gated candidate passes, and a publication receipt that proves the optimizer stayed candidate-only and non-mutating.

## Invocation

- Package path: `workflows/workflow_run_traces_to_optimization_candidates/`
- Discovery: `autoloop workflows show workflow_run_traces_to_optimization_candidates`
- Direct run:

```bash
autoloop run workflow_run_traces_to_optimization_candidates <task-id> \
  --message "Rank the highest-leverage optimization targets for the release workflow." \
  -wf selected_workflow release_candidate_to_go_no_go \
  -wf task_title "Optimize release go/no-go workflow" \
  -wf run_refs release-audit-123/run-20260426T120000Z-abcd1234 \
  -wf run_statuses failed \
  -wf run_statuses paused \
  -wf route_tags needs_rework \
  -wf route_tags blocked \
  -wf history_limit 25 \
  -wf top_k_steps 1 \
  -wf optimization_depth cheap
```

## Parameters

- `selected_workflow` required.
- `task_title` required.
- `run_refs` optional and repeatable. `run_refs` uses `<task_id>/<run_id>`.
- `run_statuses` optional and repeatable. `run_statuses` filter run-level terminal state.
- `route_tags` optional and repeatable. `route_tags` filter step-level evidence inside otherwise eligible runs.
- `history_limit` optional, default `25`.
- `top_k_steps` optional, default `1`.
- `optimization_depth` optional, one of `cheap`, `standard`, or `ablation`. Even `ablation` mode does not execute ablations here.
- `include_adversarial_generation`, `include_token_optimization`, and `include_workflow_level_candidates` are optional booleans that short-circuit their passes explicitly when disabled.
- `max_failure_scenarios`, `max_candidates_per_pass`, `focus`, `sponsor_role`, `desired_outcome`, and `constraints` are optional.
- The published `workflow_optimization_scope.json` records `optimization_depth` and `max_candidates_per_pass` for prompt and publication semantics only; it does not authorize reruns, ablations, refinement execution, or source mutation.

## Artifact Ownership

The optimizer uses deterministic helpers to prepare trace corpora, step metrics, source manifests, and failure-scenario seeds. LLM producers author failure and candidate artifacts. Workflow handlers validate accepted LLM-authored artifacts and leave them in place; they do not deterministically rewrite them.

## Artifacts

Frame artifacts:

- `selected_workflow_capability.json`
- `selected_workflow_authoring_surface.json`
- `selected_workflow_decomposition_surface.json`
- `selected_workflow_source_manifest.json`
- `workflow_optimization_scope.json`
- `workflow_optimization_trace_corpus.json`
- `excluded_run_report.json`

Analysis and candidate artifacts:

- `step_trace_metrics.json`
- `step_optimization_priority_report.json`
- `workflow_failure_scenario_seeds.json`
- `workflow_failure_scenarios.json`
- `producer_prompt_optimization_candidates.json`
- `verifier_rubric_optimization_candidates.json`
- `token_optimization_candidates.json`
- `adversarial_case_candidates.json`
- `workflow_level_optimization_candidates.json`

Publication artifacts:

- `workflow_optimization_scorecard.json`
- `workflow_refinement_evidence.json`
- `workflow_optimization_packet.md`
- `optimization_publication_receipt.json`

## Topology

Ordered step sequence:

1. `frame`
2. `rank_targets`
3. `mine_failures`
4. `optimize_producer`
5. `optimize_verifier_rubric`
6. `optimize_tokens`
7. `adversarial_cases`
8. `workflow_level`
9. `package`

Supported `pairs` subsets must be ordered prefixes only.

## Step-local optimization phase

- `frame` resolves the selected workflow, writes selected-workflow snapshots, captures `selected_workflow_source_manifest.json`, filters eligible runs, excludes historical runs missing Plan-1 observability, and writes the trace corpus.
- `rank_targets` combines deterministic metrics with LLM attribution to rank highest-leverage upstream steps rather than downstream symptoms.
- `mine_failures` consumes deterministic failure-scenario seeds and turns them into explicit producer-authored failure scenarios.
- `optimize_producer` proposes producer-side candidates only.
- `optimize_verifier_rubric` is one merged acceptance-function pass covering verifier prompt, rubric, and route-contract pressure.
- `optimize_tokens` proposes token reductions and classifies them by risk instead of treating compression as automatically safe.
- `adversarial_cases` proposes eval-case candidates only; it does not publish or run an eval suite.

## Workflow-level optimization phase

- `workflow_level` runs after local passes and proposes cross-step candidates such as artifact handoff changes, route-contract updates, context rendering changes, or workflow-parameter adjustments.
- `package` validates candidate artifacts, verifies the selected workflow source manifest is unchanged, writes the scorecard and packet, and publishes `workflow_refinement_evidence.json`.

## Failure Scenario Seeds

`workflow_failure_scenario_seeds.json` is deterministic input. `workflow_failure_scenarios.json` is the final producer-authored failure-scenario artifact.

## Optimization Depth

- All depths use existing traces only. This workflow does not execute target-workflow reruns, ablations, or refinement runs.
- `cheap`: existing traces only; concise candidate generation.
- `standard`: existing traces only; deeper LLM cross-checking; no reruns.
- `ablation`: ablation planning mode only; no ablation execution.

## Candidate Budget

`max_candidates_per_pass` is a soft prompt budget. It is not a schema limit and is not deterministically enforced. Verifiers may treat over-budget output as a focus concern, but the workflow does not reject solely on candidate count.

## Refinement handoff

- `workflow_refinement_evidence.json` is the explicit handoff into `workflow_and_eval_to_refined_workflow_package`.
- Optimization artifacts are candidate-only. They are prioritization and diagnosis input, not proof of improvement.
- `optimization_ablation_results`, when present from a later workflow, are stronger evidence than candidate estimates.
- `adversarial_case_candidates` should usually feed `workflow_to_eval_suite` before prompt or workflow promotion.

## Non-mutation guarantee

- The optimizer writes all outputs under its own workflow folder.
- It does not edit the selected workflow package.
- It captures `selected_workflow_source_manifest.json` during `frame` and revalidates that manifest during `package`.
- If the manifest changes, publication fails instead of silently proceeding.

## Validation commands

```bash
pytest -q tests/unit/test_optimization_helpers.py
pytest -q tests/runtime/test_workflow_run_traces_to_optimization_candidates.py
pytest -q tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py
pytest -q tests/test_architecture_baseline_docs.py
```
