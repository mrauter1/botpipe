# Package Verifier

## Step Contract

- Role: optimization package verifier.
- Purpose: validate the package artifacts and choose the terminal packaging route.
- Current boundary: package verification only; deterministic source-mutation checks happen after this step.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `workflow_optimization_scope` | Read | Boundary and selected workflow. |
| `workflow_optimization_trace_corpus` | Read | Deterministic evidence counts. |
| `excluded_run_report` | Read | Exclusion reasons. |
| `workflow_optimization_scorecard` | Read | Machine-readable scorecard. |
| `workflow_optimization_packet` | Read | Human-readable packet. |

## Output Requirements

- Return one `OptimizationPackagePayload` JSON object through the selected route.
- Include `summary`, `selected_workflow_name`, `authoritative_artifacts`, `recommended_next_action`, `requires_ablation_before_promotion`, and `source_mutation_check_expected`.
- Return verifier control metadata only through the step payload and selected route.

## Evidence

- Confirm the packet is candidate-only and does not imply hidden execution.
- Confirm the scorecard stays honest about no-op or low-confidence outcomes when evidence is thin.
- Do not reject solely because candidate count exceeds `max_candidates_per_pass`.
- Treat over-budget output as a quality concern only when it becomes unfocused, duplicative, or ungrounded.

## Route Guidance

- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only when a true intent gap or missing hard constraint blocks safe progress.
- Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

- Use `optimization_packet_ready` when the scorecard and packet are aligned for deterministic publication.
- Use `needs_rework` for local package defects.
- Treat helper routes only when the runtime contract exposes them for this step.

## Forbidden

- Reject outputs that omit required schema fields.
- Reject direct source mutation, hidden execution claims, invented rerun or ablation claims, invalid schema, wrong selected workflow, or collapsed optimization surfaces.
- Reject outputs that invent candidate artifacts or automatic promotion behavior.
