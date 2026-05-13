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

## Route Guidance

- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only when a true intent gap or missing hard constraint blocks safe progress.
- Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

- Use `adversarial_cases_ready` when the candidate cases are grounded and explicit.
- Use `adversarial_generation_skipped` when generation is disabled.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Reject direct source mutation, hidden execution claims, invented rerun or ablation claims, invalid schema, wrong selected workflow, or collapsed optimization surfaces.
- Reject payloads missing required fields.
