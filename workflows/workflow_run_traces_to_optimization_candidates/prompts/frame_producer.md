# Frame Producer

## Step Contract

- Role: optimizer framing producer.
- Purpose: review the deterministic frame artifacts and explain whether the scope is ready for ranking or must short-circuit to no-op packaging.
- Current boundary: candidate-only framing; no source mutation, no hidden execution, no reruns.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `selected_workflow_capability` | Read | Canonical compiled workflow identity. |
| `selected_workflow_authoring_surface` | Read | Canonical editable selected-workflow surface. |
| `selected_workflow_decomposition_surface` | Read | Canonical compiled/decomposition surface. |
| `selected_workflow_source_manifest` | Read | Deterministic pre-publication source manifest. |
| `workflow_optimization_scope` | Read | Invocation scope, filters, and boundaries. |
| `workflow_optimization_trace_corpus` | Read | Deterministic run evidence and step observations. |
| `excluded_run_report` | Read | Excluded historical runs and deterministic reason codes. |

## Output Requirements

- Do not rewrite the deterministic frame artifacts.
- Explain whether the evidence supports `optimization_scope_framed`, `no_eligible_trace_evidence`, or `needs_rework`.
- Keep observed evidence separate from inference.
- Do not claim ranking, reruns, ablations, or source changes happened here.

## Evidence

- Use only the deterministic frame artifacts plus the shared docs/instructions supplied by runtime.
- Treat `eligible_run_count == 0` as a no-op packaging condition, not a workflow failure.

## Route Guidance

- Prefer `optimization_scope_framed` when the selected workflow identity, frame artifacts, and eligible trace evidence are coherent.
- Prefer `no_eligible_trace_evidence` when the corpus shows zero eligible runs after deterministic filtering.
- Prefer `needs_rework` only for local framing or evidence-interpretation issues.
- Reserved routes are only `question`, `blocked`, and `failed`.

## Forbidden

- Do not mutate selected-workflow files or prompts.
- Do not invent missing observability.
- Do not run the selected workflow or any downstream refinement workflow.
