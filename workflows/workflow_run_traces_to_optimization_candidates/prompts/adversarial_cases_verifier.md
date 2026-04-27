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

## Route Guidance

- Use `adversarial_cases_ready` when the candidate cases are grounded and explicit.
- Use `adversarial_generation_skipped` when generation is disabled.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Reject hidden execution, direct source mutation, or payloads missing required fields.
