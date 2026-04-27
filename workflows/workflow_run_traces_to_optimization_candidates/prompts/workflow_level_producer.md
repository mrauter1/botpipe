# Workflow Level Producer

## Step Contract

- Role: workflow-level optimizer.
- Purpose: propose cross-step, topology, handoff, or workflow-policy candidates only after local passes have been considered.
- Current boundary: prefer local changes unless evidence shows a cross-step or workflow-level cause.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `selected_workflow_capability` | Read | Canonical compiled workflow graph. |
| `selected_workflow_authoring_surface` | Read | Canonical editable surfaces. |
| `selected_workflow_decomposition_surface` | Read | Cross-step surface and docs/tests. |
| `workflow_optimization_scope` | Read | Requested depth and soft candidate budget. |
| `workflow_optimization_trace_corpus` | Read | Runtime evidence and handoff pressure. |
| `step_optimization_priority_report` | Read | Local-first ranking boundary. |
| `workflow_level_optimization_candidates` | Write | Workflow-level candidates only. |

## Output Requirements

- Write `workflow_level_optimization_candidates`.
- Read `workflow_optimization_scope.json`.
- Apply `optimization_depth`.
- Treat `max_candidates_per_pass` as a soft candidate budget.
- Allowed targets include artifact handoff, route metadata, split/merge, prompt README, context rendering, session policy, workflow parameter, workflow code, eval gap, input quality gap, and operator process gap.
- Prefer the highest-leverage candidates. Do not pad the list. If you exceed the budget, explain why in the candidate rationale or summary.
- Keep candidate-only language and note when refinement workflow or ablation would be required.

## Evidence

- Only propose workflow-level changes when local fixes are insufficient or clearly downstream symptoms.
- Do not claim workflow-level changes are proven improvements.

## Route Guidance

- Use `workflow_level_candidates_ready` when grounded workflow-level candidates exist.
- Use `workflow_level_pass_not_applicable` when local changes or no-op packaging remain the right boundary.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Do not invent source mutations, hidden reruns, or automatic promotion.
- Do not mutate source files. Write only the required candidate artifact.
