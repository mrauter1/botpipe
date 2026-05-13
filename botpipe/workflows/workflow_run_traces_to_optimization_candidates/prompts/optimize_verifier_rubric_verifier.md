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
- Do not reject solely because candidate count exceeds `max_candidates_per_pass`.
- Treat over-budget output as a quality concern only when it becomes unfocused, duplicative, or ungrounded.

## Route Guidance

- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only when a true intent gap or missing hard constraint blocks safe progress.
- Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

- Use `verifier_rubric_candidates_ready` when the candidate set is grounded and scoped correctly.
- Use `verifier_rubric_pass_not_applicable` when verifier/rubric changes are not justified.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Reject direct source mutation, hidden execution claims, invented rerun or ablation claims, invalid schema, wrong selected workflow, or collapsed optimization surfaces.
- Reject invented evidence, automatic promotion, or fake reruns.
- Reject payloads missing required schema fields.
