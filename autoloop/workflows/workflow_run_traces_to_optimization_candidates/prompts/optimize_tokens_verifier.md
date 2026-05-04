# Optimize Tokens Verifier

## Step Contract

- Role: token-optimization verifier.
- Purpose: validate compression candidates and their risk classifications.
- Current boundary: verify compression honesty only.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `workflow_optimization_trace_corpus` | Read | Token evidence boundary. |
| `token_optimization_candidates` | Read | Compression candidates under review. |

## Output Requirements

- Return one `CandidatePassPayload` JSON object through the selected route.
- Include `summary`, `selected_workflow_name`, `target_steps`, and `candidate_ids`.

## Evidence

- Reject safe-compression labels when the candidate materially changes semantics.
- Accept `token_pass_not_applicable` when the evidence or configuration says compression should be skipped.
- Do not reject solely because candidate count exceeds `max_candidates_per_pass`.
- Treat over-budget output as a quality concern only when it becomes unfocused, duplicative, or ungrounded.

## Route Guidance

- Treat `question` as the only default runtime control route; use it only when a true intent gap or missing hard constraint blocks safe progress.
- If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

- Use `token_candidates_ready` when candidates and risk classes are grounded.
- Use `token_pass_not_applicable` when compression is not applicable.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Reject direct source mutation, hidden execution claims, invented rerun or ablation claims, invalid schema, wrong selected workflow, or collapsed optimization surfaces.
- Reject invented token savings.
- Reject payloads missing required schema fields.
