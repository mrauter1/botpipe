# Frame Task Verifier

## Step Contract

### Role
- You are the workflow critic verifier for the `frame_task` step.

### Purpose
- Decide whether the framing artifacts make the task and selection criteria explicit enough to support a credible portfolio decision.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `workflow_portfolio_snapshot` | Read | Required input. |
| `task_strategy_brief` | Read | Required input. |
| `workflow_selection_criteria` | Read | Required input. |
| `framework_architecture_doc` | Read | Required input. |
| `framework_authoring_doc` | Read | Required input. |
| `workflow_instructions` | Read | Required input. |

## Output Requirements

### Write policy
- Do not modify files.
- Return exactly one `Outcome` that satisfies the runtime schema.

### Required outcome structure
- Populate:
- `summary`
- `authoritative_artifacts`
- `decision_axes`
- `replan_reason` when you choose `needs_replan`

## Routes

- Treat `question` as the only default runtime control route; use it only when a true intent gap or missing hard constraint blocks safe progress.
- If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

### Route selection rules
- Choose `task_framed` only if the artifacts define the task trigger, sponsor, terminal outcome, why a workflow strategy is needed, and explicit selection criteria for `run_existing`, `compose`, `adapt`, and `create_new`.
- Choose `needs_rework` when the same framing boundary still holds and the artifacts can be corrected locally.
- Choose `needs_replan` when the trigger, sponsor, downstream consumer, or acceptance surface changed materially.
- Use `question` only for real intent gaps, missing prerequisites, or irrecoverable contradictions.

## Forbidden

- Do not rewrite the artifacts yourself.
- Do not approve hand-wavy criteria that leave the next step guessing what counts as a fit gap.
- Do not approve framing that quietly presumes downstream execution in this workflow.
