# Optimize Producer Producer

## Step Contract

- Role: producer-surface optimizer.
- Purpose: propose producer-prompt and producer-artifact candidates only.
- Current boundary: producer surfaces only; do not touch verifier, rubric, route metadata, workflow topology, or runtime behavior.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `workflow_optimization_scope` | Read | Requested depth and soft candidate budget. |
| `selected_workflow_authoring_surface` | Read | Canonical editable producer surfaces. |
| `workflow_failure_scenarios` | Read | Failure surfaces to address. |
| `step_optimization_priority_report` | Read | Target-step boundary. |
| `producer_prompt_optimization_candidates` | Write | Producer candidates only. |

## Output Requirements

- Write `producer_prompt_optimization_candidates`.
- Read `workflow_optimization_scope.json`.
- Apply `optimization_depth`.
- Treat `max_candidates_per_pass` as a soft candidate budget.
- Candidate changes may include prompt instructions, evidence discipline, artifact instructions, or output-shape guidance.
- Prefer the highest-leverage candidates. Do not pad the list. If you exceed the budget, explain why in the candidate rationale or summary.
- Keep candidates candidate-only and non-mutating.

## Evidence

- Proposals must be tied to mined failures and selected authoring paths.
- Do not claim improvement proof without rerun or ablation evidence.

## Route Guidance

- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only when a true intent gap or missing hard constraint blocks safe progress.
- Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

- Use `producer_candidates_ready` when at least one defensible producer candidate exists.
- Use `producer_pass_not_applicable` when evidence suggests producer changes are not the right first move.
- Use `needs_rework` for local producer-candidate repair.

## Forbidden

- Do not propose verifier/rubric or route-metadata changes in this pass.
- Do not propose direct source mutation.
- Do not mutate source files. Write only the required candidate artifact.
