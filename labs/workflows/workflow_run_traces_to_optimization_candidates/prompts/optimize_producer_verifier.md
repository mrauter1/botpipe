## Durable verifier outcome

Return a JSON result matching the injected schema. Use `accepted` when the artifacts meet the positive phase condition described below, `needs_rework` when the same phase can be repaired, `needs_replan` when an accepted earlier plan must be revisited, `question` or `blocked` when operator input is required, and `failed` for a terminal domain failure. The phase labels below describe semantic checks; do not return old route labels as the `outcome`. Cite only artifact names supplied by the runtime.

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

## Outcome guidance

- Mark the phase `blocked` only when a true intent gap or missing hard constraint prevents safe progress.
- Treat question, blocked, and failure guidance as semantic validation criteria.

- Use `producer_candidates_ready` when the producer candidates are grounded and scoped correctly.
- Use `producer_pass_not_applicable` when the evidence shows producer changes are not justified.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Reject verifier/rubric, route-metadata, workflow-topology, or hidden-execution changes in this pass.
- Reject direct source mutation, invented rerun or ablation claims, invalid schema, wrong selected workflow, or collapsed optimization surfaces.
- Reject payloads missing required schema fields.
