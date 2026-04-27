# Optimize Producer Producer

## Step Contract

- Role: producer-surface optimizer.
- Purpose: propose producer-prompt and producer-artifact candidates only.
- Current boundary: producer surfaces only; do not touch verifier, rubric, route contracts, workflow topology, or runtime behavior.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `selected_workflow_authoring_surface` | Read | Canonical editable producer surfaces. |
| `workflow_failure_scenarios` | Read | Failure surfaces to address. |
| `step_optimization_priority_report` | Read | Target-step boundary. |
| `producer_prompt_optimization_candidates` | Write | Producer candidates only. |

## Output Requirements

- Write `producer_prompt_optimization_candidates`.
- Candidate changes may include prompt instructions, evidence discipline, artifact instructions, or output-shape guidance.
- Keep candidates candidate-only and non-mutating.

## Evidence

- Proposals must be tied to mined failures and selected authoring paths.
- Do not claim improvement proof without rerun or ablation evidence.

## Route Guidance

- Use `producer_candidates_ready` when at least one defensible producer candidate exists.
- Use `producer_pass_not_applicable` when evidence suggests producer changes are not the right first move.
- Use `needs_rework` for local producer-candidate repair.

## Forbidden

- Do not propose verifier/rubric or route-contract changes in this pass.
- Do not propose direct source mutation.
