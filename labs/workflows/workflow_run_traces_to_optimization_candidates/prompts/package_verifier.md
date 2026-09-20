## Durable verifier outcome

Return a JSON result matching the injected schema. Use `accepted` when the artifacts meet the positive phase condition described below, `needs_rework` when the same phase can be repaired, `needs_replan` when an accepted earlier plan must be revisited, `question` or `blocked` when operator input is required, and `failed` for a terminal domain failure. The phase labels below describe semantic checks; do not return old route labels as the `outcome`. Cite only artifact names supplied by the runtime.

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

## Outcome guidance

- Mark the phase `blocked` only when a true intent gap or missing hard constraint prevents safe progress.
- Treat question, blocked, and failure guidance as semantic validation criteria.

- Use `optimization_packet_ready` when the scorecard and packet are aligned for deterministic publication.
- Use `needs_rework` for local package defects.
- Use `blocked` only when a missing prerequisite or irreconcilable contradiction prevents safe progress.

## Forbidden

- Reject outputs that omit required schema fields.
- Reject direct source mutation, hidden execution claims, invented rerun or ablation claims, invalid schema, wrong selected workflow, or collapsed optimization surfaces.
- Reject outputs that invent candidate artifacts or automatic promotion behavior.
