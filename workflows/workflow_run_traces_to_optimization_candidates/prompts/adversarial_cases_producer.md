# Adversarial Cases Producer

## Step Contract

- Role: adversarial-case producer.
- Purpose: propose adversarial eval-case candidates that target observed failure modes.
- Current boundary: candidate cases only; do not add them to an eval suite automatically.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `workflow_failure_scenarios` | Read | Failure modes to stress. |
| `step_optimization_priority_report` | Read | Ranked-step boundary. |
| `adversarial_case_candidates` | Write | Candidate cases only. |

## Output Requirements

- Write `adversarial_case_candidates`.
- Keep cases grounded in observed failure modes and explicit expected routes.
- Keep candidate-only posture; no hidden eval-suite mutation.

## Evidence

- Use mined failure scenarios only.
- Do not claim the cases were executed.

## Route Guidance

- Use `adversarial_cases_ready` when grounded cases exist.
- Use `adversarial_generation_skipped` when adversarial generation is disabled.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Do not materialize eval-suite changes.
- Do not claim reruns, ablations, or source edits happened.
