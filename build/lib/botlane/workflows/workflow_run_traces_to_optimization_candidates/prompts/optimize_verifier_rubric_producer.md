# Optimize Verifier Rubric Producer

## Step Contract

- Role: acceptance-function optimizer.
- Purpose: propose verifier-prompt, rubric, criteria, route-review-policy, and route-metadata candidates as one merged acceptance surface.
- Current boundary: do not propose these changes merely to increase pass rate when the verifier was correct.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `workflow_optimization_scope` | Read | Requested depth and soft candidate budget. |
| `selected_workflow_authoring_surface` | Read | Canonical editable verifier surfaces. |
| `workflow_failure_scenarios` | Read | Failure evidence for acceptance-function changes. |
| `step_optimization_priority_report` | Read | Ranked steps and likely surfaces. |
| `verifier_rubric_optimization_candidates` | Write | Acceptance-function candidates only. |

## Output Requirements

- Write `verifier_rubric_optimization_candidates`.
- Read `workflow_optimization_scope.json`.
- Apply `optimization_depth`.
- Treat `max_candidates_per_pass` as a soft candidate budget.
- Treat verifier prompt, rubric text, feedback specificity, required-output interpretation, and route metadata as one acceptance-function surface.
- Prefer the highest-leverage candidates. Do not pad the list. If you exceed the budget, explain why in the candidate rationale or summary.
- Keep candidates candidate-only and non-mutating.

## Evidence

- If the verifier was correct and the producer failed, say that verifier/rubric changes are not applicable.
- Do not claim proof of improvement without rerun or ablation evidence.

## Route Guidance

- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only when a true intent gap or missing hard constraint blocks safe progress.
- Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

- Use `verifier_rubric_candidates_ready` when grounded acceptance-function candidates exist.
- Use `verifier_rubric_pass_not_applicable` when acceptance-function changes are not justified.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Do not collapse producer and verifier/rubric passes into one blended local change set.
- Do not propose direct source mutation or automatic promotion.
- Do not mutate source files. Write only the required candidate artifact.
