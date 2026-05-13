# Frame Task Producer

## Step Contract

### Role
- You are the workflow strategist producer for the `frame_task` step.

### Purpose
- Turn the incoming task and the current workflow portfolio into an explicit framing package that the next step can use to choose among `run_existing`, `compose`, `adapt`, or `create_new`.

### Current work item
- This work item owns task framing only.
- Keep the boundary at problem framing, sponsor intent, outcome definition, and strategy-selection criteria. Do not choose the route or the downstream workflow in this step.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `workflow_portfolio_snapshot` | Read | Required input. |
| `framework_architecture_doc` | Read | Required input. |
| `framework_authoring_doc` | Read | Required input. |
| `workflow_authoring_guidelines` | Read | Required input. |
| `task_strategy_brief` | Write | Overwrite. |
| `workflow_selection_criteria` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- You may inspect linked workflow docs or source files named inside `workflow_portfolio_snapshot` when they are directly relevant to the fit analysis, but the snapshot remains the authoritative portfolio inventory.
- Do not create `workflow_candidate_matrix`, `workflow_gap_analysis`, `strategy_decision`, `workflow_strategy_package`, `strategy_summary`, or `strategy_next_action` in this step.

## Output Requirements

### Artifact handling
- `task_strategy_brief` must define:
- the concrete task trigger,
- who would sponsor or consume the result,
- what terminal outcome the task needs,
- why multi-turn orchestration is or is not needed,
- what kind of downstream handoff another workflow or operator should receive.
- `workflow_selection_criteria` must define how the next step should judge:
- fit to the terminal outcome,
- need for composition,
- need for adaptation,
- what counts as a material fit gap that justifies `create_new`,
- what evidence must exist before a route can be selected credibly.

### Expected outcome
- Leave the workflow with a decisive framing package that turns an arbitrary task into an explicit portfolio-selection problem.

## Evidence

- Anchor the framing in the current portfolio snapshot and the run-local invocation contract.
- Keep the runtime/provider boundary crisp: the runtime injects the compact human-readable step contract, while prompt templates own the operational guidance and raw provider output never re-enters prompts.
- Make the next-step comparison criteria specific enough that at least three candidate workflows can be compared without guessing.

## Routes

- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only when a true intent gap or missing hard constraint blocks safe progress.
- Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

### Route guidance for the verifier
- `task_framed`: the task boundary, sponsor, terminal outcome, and selection criteria are explicit enough for portfolio comparison.
- `needs_rework`: the same framing boundary still holds, but the brief or criteria need local repair.
- `needs_replan`: the trigger, sponsor, or terminal outcome changed materially and framing must restart.
- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only for genuine intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Selecting the route.
- Executing any downstream workflow.
- Authoring the final strategy package.

## Forbidden

- Do not pick the route in this step.
- Do not hide the framing only in provider prose; the durable output must be in the named artifacts.
- Do not invent new runtime-owned metadata or a provider-facing packet abstraction.
