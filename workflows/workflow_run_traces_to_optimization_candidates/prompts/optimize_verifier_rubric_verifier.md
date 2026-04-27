# Optimize Verifier Rubric Verifier

## Step Contract

- Role: acceptance-function verifier.
- Purpose: validate merged verifier/rubric candidates and keep false-accept and false-reject reasoning evidence-backed.
- Current boundary: acceptance-function verification only.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `workflow_failure_scenarios` | Read | Failure evidence boundary. |
| `selected_workflow_authoring_surface` | Read | Canonical editable acceptance surfaces. |
| `verifier_rubric_optimization_candidates` | Read | Candidate artifact under review. |

## Output Requirements

- Return one `CandidatePassPayload` JSON object through the selected route.
- Include `summary`, `selected_workflow_name`, `target_steps`, and `candidate_ids`.

## Evidence

- Reject acceptance-function changes that simply soften correct verifier behavior.
- Accept candidate-only acceptance changes when they remain grounded and explicit about risks.

## Route Guidance

- Use `verifier_rubric_candidates_ready` when the candidate set is grounded and scoped correctly.
- Use `verifier_rubric_pass_not_applicable` when verifier/rubric changes are not justified.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Reject invented evidence, source mutation, automatic promotion, or fake reruns.
- Reject payloads missing required schema fields.
