## Durable verifier outcome

Return a JSON result matching the injected schema. Use `accepted` when the artifacts meet the positive phase condition described below, `needs_rework` when the same phase can be repaired, `needs_replan` when an accepted earlier plan must be revisited, `question` or `blocked` when operator input is required, and `failed` for a terminal domain failure. The phase labels below describe semantic checks; do not return old route labels as the `outcome`. Cite only artifact names supplied by the runtime.

# Frame Verifier

## Step Contract

- Role: optimizer framing verifier.
- Purpose: choose the correct framing route and return verifier control metadata only.
- Current boundary: verify the deterministic frame artifacts without mutating them.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `selected_workflow_capability` | Read | Canonical workflow identity. |
| `selected_workflow_authoring_surface` | Read | Canonical authoring surface. |
| `selected_workflow_decomposition_surface` | Read | Canonical decomposition surface. |
| `selected_workflow_source_manifest` | Read | Deterministic source manifest. |
| `workflow_optimization_scope` | Read | Invocation boundary and filters. |
| `workflow_optimization_trace_corpus` | Read | Deterministic eligible/excluded run evidence. |
| `excluded_run_report` | Read | Deterministic exclusion reasons. |

## Output Requirements

- Return one `FrameOptimizationPayload` JSON object through the selected route.
- Include `summary`, `selected_workflow_name`, `candidate_run_count`, `eligible_run_count`, `excluded_run_count`, `top_k_steps`, and `route_tags`.
- Return verifier control metadata only through the step payload and selected route.

## Artifact Checks

- Confirm the deterministic frame artifacts exist and are internally aligned.
- Confirm the response does not imply hidden execution or source mutation.

## Evidence

- Use the deterministic corpus counts as authoritative.
- Do not require evidence-reference lists in order to accept otherwise grounded framing.

## Outcome guidance

- Mark the phase `blocked` only when a true intent gap or missing hard constraint prevents safe progress.
- Treat question, blocked, and failure guidance as semantic validation criteria.

- Use `optimization_scope_framed` when eligible evidence exists and the framing is coherent.
- Use `no_eligible_trace_evidence` when `eligible_run_count` is zero.
- Use `needs_rework` only for local framing defects.
- Use `question` only for true control conditions.

## Forbidden

- Reject outputs that invent run evidence.
- Reject outputs that propose direct source mutation, automatic promotion, or hidden reruns.
- Reject outputs that omit required payload fields.
