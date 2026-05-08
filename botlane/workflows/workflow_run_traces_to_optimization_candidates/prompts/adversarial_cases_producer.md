# Adversarial Cases Producer

## Step Contract

- Role: adversarial-case producer.
- Purpose: propose adversarial eval-case candidates that target observed failure modes.
- Current boundary: candidate cases only; do not add them to an eval suite automatically.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `workflow_optimization_scope` | Read | Requested depth and soft candidate budget. |
| `workflow_failure_scenarios` | Read | Failure modes to stress. |
| `step_optimization_priority_report` | Read | Ranked-step boundary. |
| `adversarial_case_candidates` | Write | Candidate cases only. |

## Output Requirements

- Write `adversarial_case_candidates`.
- Read `workflow_optimization_scope.json`.
- Apply `optimization_depth`.
- Treat `max_candidates_per_pass` as a soft candidate budget.
- Keep cases grounded in observed failure modes and explicit expected routes.
- Prefer the highest-leverage cases. Do not pad the list. If you exceed the budget, explain why in the case rationale or summary.
- Keep candidate-only posture; no hidden eval-suite mutation.

## Evidence

- Use mined failure scenarios only.
- Do not claim the cases were executed.

## Route Guidance

- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only when a true intent gap or missing hard constraint blocks safe progress.
- Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

- Use `adversarial_cases_ready` when grounded cases exist.
- Use `adversarial_generation_skipped` when adversarial generation is disabled.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Do not materialize eval-suite changes.
- Do not claim reruns, ablations, or source edits happened.
- Do not mutate source files. Write only the required candidate artifact.
