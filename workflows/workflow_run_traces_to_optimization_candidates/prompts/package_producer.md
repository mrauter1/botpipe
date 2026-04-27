# Package Producer

## Step Contract

- Role: optimization package producer.
- Purpose: publish the scorecard and human-readable packet that summarize candidate-only optimization evidence.
- Current boundary: candidate-only publication; no source mutation, no hidden execution, no automatic promotion.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `selected_workflow_capability` | Read | Canonical selected-workflow identity. |
| `selected_workflow_authoring_surface` | Read | Canonical authoring surface. |
| `selected_workflow_decomposition_surface` | Read | Canonical decomposition surface. |
| `selected_workflow_source_manifest` | Read | Pre-publication source manifest. |
| `workflow_optimization_scope` | Read | Invocation and boundary. |
| `workflow_optimization_trace_corpus` | Read | Deterministic corpus counts. |
| `excluded_run_report` | Read | Deterministic exclusion reasons. |
| `optimization_package_checklist` | Read | Publication guardrails. |
| `workflow_optimization_scorecard` | Write | Machine-readable publication scorecard. |
| `workflow_optimization_packet` | Write | Human-readable optimization packet. |

## Output Requirements

- Write `workflow_optimization_scorecard` and `workflow_optimization_packet`.
- Read `workflow_optimization_scope` and apply `optimization_depth`.
- If `eligible_run_count == 0`, publish a no-op scorecard and packet that explain why no optimization was performed.
- Say which candidates are ready for review, which require ablation, which are token-only, which are adversarial-case ideas, and which require workflow-level refinement when those artifacts exist.
- State that target workflow reruns, ablations, and refinement execution were not executed in this workflow.
- Keep candidate-only language and make the non-mutation boundary explicit.

## Evidence

- Use only the artifacts already captured in this workflow folder.
- Do not claim reruns, ablations, refinements, or source edits happened unless evidence exists in this workflow folder.

## Route Guidance

- Use `optimization_packet_ready` when the scorecard and packet are aligned and publication-safe.
- Use `needs_rework` only for local packaging defects.

## Forbidden

- Do not imply automatic promotion, automatic rollback, hidden target-workflow execution, or hidden refinement execution.
- Do not invent candidate artifacts that were never produced.
