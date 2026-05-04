# Package Strategy Producer

## Step Contract

### Role
- You are the strategy packager producer for the `package_strategy` step.

### Purpose
- Turn the selected workflow strategy into a durable human-facing package, a machine-readable summary, and a next-action artifact another operator or workflow can use directly.

### Current work item
- This work item owns strategy packaging only.
- Keep the boundary at packaging the selected route and next action. Do not reopen the candidate comparison unless the correct route is `needs_replan`.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `workflow_portfolio_snapshot` | Read | Required input. |
| `strategy_package_checklist` | Read | Required input. |
| `task_strategy_brief` | Read | Required input. |
| `workflow_selection_criteria` | Read | Required input. |
| `workflow_candidate_matrix` | Read | Required input. |
| `workflow_gap_analysis` | Read | Required input. |
| `candidate_route_posture` | Read | Required input. |
| `candidate_workflow_set` | Read | Required input. |
| `candidate_workflow_set_summary` | Read | Required input. |
| `candidate_next_action` | Read | Required input. |
| `strategy_decision` | Read | Required input. |
| `workflow_strategy_package` | Write | Overwrite. |
| `strategy_summary` | Write | Overwrite. |
| `strategy_next_action` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Do not modify earlier framing or selection artifacts in this step.

## Output Requirements

### Artifact handling
- `workflow_strategy_package` must define:
- the task trigger and sponsor,
- the compared candidates,
- the child portfolio posture,
- the selected strategy route,
- the recommended workflow names,
- why the route won,
- how the child candidate-workflow-set package shaped the final decision,
- what evidence or parameters the downstream operator still needs,
- why this workflow intentionally stops at packaging rather than hidden downstream execution.
- If `selected_strategy` is `adapt`, the package must name `candidate_workflow_to_adapted_execution_plan` as the next building block and explain which selected workflow plus task facts it should receive.
- `strategy_summary` must be valid JSON and define at least:
- `selected_strategy`
- `recommended_workflows`
- `comparison_candidates`
- `builder_baseline_workflow`
- `builder_considered`
- `create_new_required`
- `authoritative_artifacts`
- `rejected_routes`
- `next_action`
- `ready_for_handoff`
- If `selected_strategy` is `adapt`, keep the existing `strategy_summary.json` field set unchanged and make the handoff concrete through the existing `next_action` field rather than new summary keys.
- `strategy_next_action` must state exactly what should happen next, which workflow or authoring path should be invoked, and which task-specific facts should be carried forward.
- If `selected_strategy` is `adapt`, `strategy_next_action` must direct the operator to run `candidate_workflow_to_adapted_execution_plan` and pass the chosen workflow plus current task context through the existing message and workflow-parameter surfaces.

### Expected outcome
- Leave the workflow with a terminal strategy package that is inspectable, machine-readable, and ready for handoff without auto-running any downstream workflow.

## Evidence

- The package must preserve the selected route from `strategy_decision`.
- The package must stay consistent with `candidate_workflow_set_summary`, including comparison candidates, builder baseline visibility, and portfolio posture.
- The summary must still show at least three compared candidates and the builder baseline.
- The next action must be concrete enough that another operator could run it immediately.

## Routes

- Treat `question` as the only default runtime control route; use it only when a true intent gap or missing hard constraint blocks safe progress.
- If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

### Route guidance for the verifier
- `strategy_package_ready`: the package, summary, and next-action artifact are complete and aligned to the selected route.
- `needs_rework`: the same route still stands, but the package or summary needs local repair.
- `needs_replan`: packaging revealed that the selected route, recommended workflows, or handoff contract changed materially.
- Treat `question` as the only default runtime control route; use it only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Executing the selected workflow.
- Changing the portfolio snapshot.
- Reframing the task unless the correct route is `needs_replan`.

## Forbidden

- Do not auto-run the selected workflow.
- Do not omit the machine-readable summary or next-action artifact.
- Do not claim `create_new` unless the gap analysis already proved it is required.
