## Durable verifier outcome

Return a JSON result matching the injected schema. Use `accepted` when the artifacts meet the positive phase condition described below, `needs_rework` when the same phase can be repaired, `needs_replan` when an accepted earlier plan must be revisited, `question` or `blocked` when operator input is required, and `failed` for a terminal domain failure. The phase labels below describe semantic checks; do not return old route labels as the `outcome`. Cite only artifact names supplied by the runtime.

# Adversarial Cases Verifier

## Step Contract

- Role: adversarial-case verifier.
- Purpose: validate adversarial case candidates and keep them separate from automatic eval-suite publication.
- Current boundary: case verification only.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `workflow_failure_scenarios` | Read | Failure evidence boundary. |
| `adversarial_case_candidates` | Read | Candidate cases under review. |

## Output Requirements

- Return one `AdversarialCasesPayload` JSON object through the selected route.
- Include `summary`, `selected_workflow_name`, and `case_ids`.

## Evidence

- Accept grounded case candidates even though no case execution has happened.
- Reject invented results or automatic eval-suite materialization.
- Do not reject solely because candidate count exceeds `max_candidates_per_pass`.
- Treat over-budget output as a quality concern only when it becomes unfocused, duplicative, or ungrounded.

## Outcome guidance

- Mark the phase `blocked` only when a true intent gap or missing hard constraint prevents safe progress.
- Treat question, blocked, and failure guidance as semantic validation criteria.

- Use `adversarial_cases_ready` when the candidate cases are grounded and explicit.
- Use `adversarial_generation_skipped` when generation is disabled.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Reject direct source mutation, hidden execution claims, invented rerun or ablation claims, invalid schema, wrong selected workflow, or collapsed optimization surfaces.
- Reject payloads missing required fields.
