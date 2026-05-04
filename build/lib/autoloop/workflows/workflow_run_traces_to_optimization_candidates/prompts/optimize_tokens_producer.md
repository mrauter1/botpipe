# Optimize Tokens Producer

## Step Contract

- Role: token-optimization producer.
- Purpose: propose token-reduction candidates without silently changing semantics.
- Current boundary: compression only; classify risk explicitly.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `workflow_optimization_scope` | Read | Requested depth and soft candidate budget. |
| `selected_workflow_authoring_surface` | Read | Canonical editable prompt surfaces. |
| `workflow_optimization_trace_corpus` | Read | Token usage evidence. |
| `step_optimization_priority_report` | Read | Ranked target boundary. |
| `token_optimization_candidates` | Write | Compression candidates with risk classification. |

## Output Requirements

- Write `token_optimization_candidates`.
- Read `workflow_optimization_scope.json`.
- Apply `optimization_depth`.
- Treat `max_candidates_per_pass` as a soft candidate budget.
- Classify every candidate as `safe_compression`, `risky_compression`, or `semantic_behavior_change_disguised_as_compression`.
- Prefer the highest-leverage candidates. Do not pad the list. If you exceed the budget, explain why in the candidate rationale or summary.
- Keep candidate-only language and avoid hidden semantic changes.

## Evidence

- Use trace-corpus token evidence only.
- Do not claim preserved semantics unless the rationale is explicit.

## Route Guidance

- Treat `question` as the only default runtime control route; use it only when a true intent gap or missing hard constraint blocks safe progress.
- If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

- Use `token_candidates_ready` when grounded compression candidates exist.
- Use `token_pass_not_applicable` when token optimization is disabled or not justified.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Do not present risky semantic changes as safe compression.
- Do not claim reruns, tests, or ablations happened.
- Do not mutate source files. Write only the required candidate artifact.
