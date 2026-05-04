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
- Do not reject solely because candidate count exceeds `max_candidates_per_pass`.
- Treat over-budget output as a quality concern only when it becomes unfocused, duplicative, or ungrounded.

## Route Guidance

- Treat `question` as the only default runtime control route; use it only when a true intent gap or missing hard constraint blocks safe progress.
- If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

- Use `producer_candidates_ready` when the producer candidates are grounded and scoped correctly.
- Use `producer_pass_not_applicable` when the evidence shows producer changes are not justified.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Reject verifier/rubric, route-metadata, workflow-topology, or hidden-execution changes in this pass.
- Reject direct source mutation, invented rerun or ablation claims, invalid schema, wrong selected workflow, or collapsed optimization surfaces.
- Reject payloads missing required schema fields.
