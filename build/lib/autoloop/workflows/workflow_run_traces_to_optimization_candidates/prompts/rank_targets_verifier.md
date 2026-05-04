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

## Route Guidance

- Treat `question` as the only default runtime control route; use it only when a true intent gap or missing hard constraint blocks safe progress.
- If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

- Use `targets_ranked` when the ranking is grounded and actionable.
- Use `insufficient_evidence` when the ranking artifact is honest but the evidence is too thin.
- Use `needs_rework` for local ranking defects.

## Forbidden

- Reject invented evidence, direct source mutation proposals, or fake improvement claims.
- Reject payloads missing required schema fields.
