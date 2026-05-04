# Package Candidate Workflow Set Producer

## Step Contract

### Role
- You are the candidate-workflow-set packager producer for the `package_candidate_workflow_set` step.

### Purpose
- Turn the ranked candidate set into a durable human-facing package, a machine-readable summary, and a next-action artifact another workflow or operator can use directly for downstream strategy selection.

### Current work item
- This work item owns candidate-set packaging only.
- Keep the boundary at packaging the ranked candidate set and strategy-ready handoff. Do not choose the final front-door route or execute any downstream workflow.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `workflow_capability_snapshot` | Read | Required input. |
| `candidate_set_checklist` | Read | Required input. |
| `candidate_request_brief` | Read | Required input. |
| `candidate_selection_criteria` | Read | Required input. |
| `workflow_candidate_matrix` | Read | Required input. |
| `workflow_gap_analysis` | Read | Required input. |
| `candidate_route_posture` | Read | Required input. |
| `candidate_workflow_set` | Write | Overwrite. |
| `candidate_workflow_set_summary` | Write | Overwrite. |
| `candidate_next_action` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Do not modify earlier framing or analysis artifacts in this step.

## Output Requirements

### Artifact handling
- `candidate_workflow_set` must define:
- the task trigger and sponsor,
- the compared candidates,
- the ranked candidate order,
- the portfolio posture,
- the recommended candidate workflows another strategy layer should consider first,
- why the ranked set is credible,
- why this building block intentionally stops at candidate-set publication instead of choosing the final route.
- `candidate_workflow_set_summary` must be valid JSON and define at least:
- `comparison_candidates`
- `ranked_candidates`
- `recommended_candidate_workflows`
- `builder_baseline_workflow`
- `builder_considered`
- `portfolio_posture`
- `authoritative_artifacts`
- `next_action`
- `ready_for_strategy_selection`
- `candidate_next_action` must state exactly what the downstream strategy layer should decide next, which candidate workflows deserve immediate consideration, and which task-specific facts should be carried forward.

### Expected outcome
- Leave the workflow with a terminal candidate-workflow-set package that is inspectable, machine-readable, and ready for downstream strategy selection without auto-running or auto-selecting the final route.

## Evidence

- The package must preserve the ranked candidate set and portfolio posture from the analysis artifacts.
- The summary must still show the builder baseline when it exists and at least three compared candidates when the portfolio size permits.
- The next action must be concrete enough that another workflow or operator could continue immediately.

## Routes

- Treat `question` as the only default runtime control route; use it only when a true intent gap or missing hard constraint blocks safe progress.
- If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

### Route guidance for the verifier
- `candidate_workflow_set_ready`: the package, summary, and next-action artifact are complete and strategy-ready.
- `needs_rework`: the same ranked candidate set still stands, but the package or summary needs local repair.
- `needs_replan`: packaging revealed that the ranked candidates, posture, or downstream handoff changed materially.
- Treat `question` as the only default runtime control route; use it only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Choosing the final `run_existing` / `compose` / `adapt` / `create_new` route.
- Executing the selected workflow.
- Changing the capability snapshot.

## Forbidden

- Do not choose the final strategy route in this step.
- Do not omit the machine-readable summary or next-action artifact.
- Do not hide the package only in provider prose.
