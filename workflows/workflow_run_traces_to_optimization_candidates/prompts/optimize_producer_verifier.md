# Optimize Producer Verifier

## Step Contract

- Role: producer-surface verifier.
- Purpose: validate producer-only candidates and keep producer and acceptance surfaces separate.
- Current boundary: producer-candidate verification only.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `selected_workflow_authoring_surface` | Read | Canonical editable producer surfaces. |
| `workflow_failure_scenarios` | Read | Failure boundary. |
| `producer_prompt_optimization_candidates` | Read | Candidate artifact under review. |

## Output Requirements

- Return one `CandidatePassPayload` JSON object through the selected route.
- Include `summary`, `selected_workflow_name`, `target_steps`, and `candidate_ids`.

## Evidence

- Confirm every candidate stays on producer-facing surfaces only.
- Reject pass-rate chasing that merely weakens the verifier indirectly.

## Route Guidance

- Use `producer_candidates_ready` when the producer candidates are grounded and scoped correctly.
- Use `producer_pass_not_applicable` when the evidence shows producer changes are not justified.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Reject verifier/rubric, route-contract, workflow-topology, or hidden-execution changes in this pass.
- Reject payloads missing required schema fields.
