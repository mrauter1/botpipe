## Durable verifier outcome

Return a JSON result matching the injected schema. Use `accepted` when the artifacts meet the positive phase condition described below, `needs_rework` when the same phase can be repaired, `needs_replan` when an accepted earlier plan must be revisited, `question` or `blocked` when operator input is required, and `failed` for a terminal domain failure. The phase labels below describe semantic checks; do not return old route labels as the `outcome`. Cite only artifact names supplied by the runtime.

# Rank Targets Verifier

## Step Contract

- Role: optimization target ranking verifier.
- Purpose: validate deterministic ranking outputs and choose the correct ranking route.
- Current boundary: ranking control only; no file mutation outside declared artifacts.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `workflow_optimization_scope` | Read | Top-k boundary and optimizer mode. |
| `workflow_optimization_trace_corpus` | Read | Step observations and counts. |
| `step_trace_metrics` | Read | Deterministic metrics output. |
| `step_optimization_priority_report` | Read | Ranked target report. |

## Output Requirements

- Return one `RankTargetsPayload` JSON object through the selected route.
- Include `summary`, `selected_workflow_name`, `ranked_steps`, and `ranking_method`.
- Verify the ranked outputs stay candidate-only and do not imply hidden execution.

## Evidence

- Check that ranking rationale is grounded in the deterministic metrics and corpus.
- Treat the precomputed metrics and report as authoritative unless the same evidence clearly supports a correction.
- Allow low-confidence ranking if the route is `insufficient_evidence` and the report says so explicitly.

## Outcome guidance

- Mark the phase `blocked` only when a true intent gap or missing hard constraint prevents safe progress.
- Treat question, blocked, and failure guidance as semantic validation criteria.

- Use `targets_ranked` when the ranking is grounded and actionable.
- Use `insufficient_evidence` when the ranking artifact is honest but the evidence is too thin.
- Use `needs_rework` for local ranking defects.

## Forbidden

- Reject invented evidence, direct source mutation proposals, or fake improvement claims.
- Reject payloads missing required schema fields.
