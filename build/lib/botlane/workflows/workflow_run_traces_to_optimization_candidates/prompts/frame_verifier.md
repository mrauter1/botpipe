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

## Route Guidance

- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only when a true intent gap or missing hard constraint blocks safe progress.
- Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

- Use `optimization_scope_framed` when eligible evidence exists and the framing is coherent.
- Use `no_eligible_trace_evidence` when `eligible_run_count` is zero.
- Use `needs_rework` only for local framing defects.
- Use `question` only for true control conditions.

## Forbidden

- Reject outputs that invent run evidence.
- Reject outputs that propose direct source mutation, automatic promotion, or hidden reruns.
- Reject outputs that omit required payload fields.
