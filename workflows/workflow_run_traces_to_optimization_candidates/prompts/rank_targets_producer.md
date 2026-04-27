# Rank Targets Producer

## Step Contract

- Role: optimization target ranking producer.
- Purpose: turn deterministic step metrics and corpus evidence into a ranked local-first optimization narrative.
- Current boundary: candidate-only ranking; no source edits, no reruns, no ablations.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `workflow_optimization_scope` | Read | Ranking boundary and top-k request. |
| `workflow_optimization_trace_corpus` | Read | Step observations and run metadata. |
| `selected_workflow_capability` | Read | Canonical selected-workflow identity. |
| `selected_workflow_authoring_surface` | Read | Helps identify editable prompt surfaces. |
| `selected_workflow_decomposition_surface` | Read | Helps avoid blaming downstream symptoms incorrectly. |
| `step_trace_metrics` | Write | Deterministic per-step counts and token share. |
| `step_optimization_priority_report` | Write | Ranked target set and rationale. |

## Output Requirements

- Write `step_trace_metrics` and `step_optimization_priority_report`.
- Read `workflow_optimization_scope.json` and apply `optimization_depth`.
- Treat the precomputed deterministic metrics and draft ranking report as the authoritative starting point; revise only when the same evidence justifies it explicitly.
- Distinguish high failure count from highest leverage optimization target.
- Prefer upstream attribution when later failures are downstream symptoms of weaker earlier artifacts.

## Evidence

- Use only runtime-owned trace, git-tracking, and static-graph evidence already captured.
- Do not claim LLM review overrode deterministic evidence without saying why.

## Route Guidance

- Use `targets_ranked` when at least one defensible target is ranked.
- Use `insufficient_evidence` when the corpus is too thin for credible ranking.
- Use `needs_rework` only for local ranking repair.

## Forbidden

- Do not recommend source mutation or automatic promotion.
- Do not claim reruns or ablations happened.
