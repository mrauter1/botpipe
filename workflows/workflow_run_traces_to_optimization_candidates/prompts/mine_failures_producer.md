# Mine Failures Producer

## Step Contract

- Role: failure-scenario mining producer.
- Purpose: convert ranked targets and trace observations into failure scenarios that explain where optimization pressure comes from.
- Current boundary: candidate-only diagnosis; no source edits, no reruns.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `workflow_optimization_scope` | Read | Requested depth and soft candidate budget context. |
| `workflow_optimization_trace_corpus` | Read | Deterministic step observations and raw refs. |
| `step_optimization_priority_report` | Read | Ranked steps to focus on first. |
| `selected_workflow_authoring_surface` | Read | Helps identify editable local surfaces. |
| `workflow_failure_scenario_seeds` | Read | Deterministic seed input, not the final artifact. |
| `workflow_failure_scenarios` | Write | Failure scenarios only. |

## Output Requirements

- Write `workflow_failure_scenarios`.
- Read `workflow_optimization_scope.json` and apply `optimization_depth`.
- Read `workflow_failure_scenario_seeds.json` as deterministic input. You own the final `workflow_failure_scenarios.json` artifact.
- The workflow will validate your artifact but will not deterministically rewrite it.
- Use the seeds, trace corpus, raw-output references, priority report, and selected workflow surfaces to author the final failure scenarios.
- Do not simply copy seeds mechanically. Refine, merge, split, or discard seeds based on the evidence.
- Use allowed failure kinds only.
- Keep observed evidence separate from inferred likely fixes.

## Evidence

- Use deterministic trace evidence, raw output references when present, and static graph context already captured.
- Do not require evidence-reference arrays to exist in order to write a valid scenario.

## Route Guidance

- Use `failure_scenarios_mined` when at least one grounded failure scenario exists.
- Use `no_failure_scenarios` when ranked targets do not produce defensible scenarios.
- Use `needs_rework` for local scenario repair.

## Forbidden

- Do not propose source mutation or automatic promotion.
- Do not claim eval cases or reruns were executed.
