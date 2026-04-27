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

## Route Guidance

- Use `token_candidates_ready` when candidates and risk classes are grounded.
- Use `token_pass_not_applicable` when compression is not applicable.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Reject invented token savings, hidden execution, or source mutation.
- Reject payloads missing required schema fields.
