# Frame Adaptation Request Producer

## Step Contract

### Role
- You are the workflow adaptation-request framing producer for the `frame_adaptation_request` step.

### Purpose
- Turn the chosen workflow and the current task context into an explicit adaptation framing package that the next step can use to assess fit, parameterization, and execution handling without guesswork.

### Current work item
- This work item owns adaptation framing only.
- Keep the boundary at task framing, selected-workflow intent, terminal outcome, and adaptation success criteria. Do not analyze individual workflow steps or package the terminal execution plan in this step.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `selected_workflow_capability` | Read | Required input. |
| `framework_architecture_doc` | Read | Required input. |
| `framework_authoring_doc` | Read | Required input. |
| `workflow_instructions` | Read | Required input. |
| `adaptation_request_brief` | Write | Overwrite. |
| `adaptation_success_criteria` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- You may inspect the selected workflow's linked doc or source file when the capability snapshot says they exist, but `selected_workflow_capability` remains the authoritative selected-workflow contract.
- Do not create `workflow_fit_assessment`, `step_adaptation_matrix`, `adapted_execution_plan`, `proposed_workflow_parameters`, `adapted_execution_summary`, or `adapted_execution_next_action` in this step.

## Output Requirements

### Artifact handling
- `adaptation_request_brief` must define:
- the concrete task trigger,
- who would sponsor or consume the result,
- the canonical selected workflow name and why it was chosen upstream,
- what terminal outcome the downstream execution should produce,
- why this building block is needed instead of auto-running the selected workflow immediately,
- what task facts must be preserved into later execution.
- `adaptation_success_criteria` must define:
- what parts of the selected workflow must stay fixed,
- what may be parameterized or carried forward as operator notes,
- what execution-ready evidence must exist before publication,
- which expected downstream artifacts matter,
- what risks or boundary changes should force `needs_replan` instead of local repair.

### Expected outcome
- Leave the workflow with a decisive framing package that turns the chosen workflow plus task context into an explicit adaptation-analysis problem.

## Evidence

- Anchor the framing in the selected workflow capability snapshot and the run-local invocation contract.
- Keep the runtime/provider boundary crisp: the runtime injects the compact human-readable step contract, while prompt templates own the operational guidance and raw provider output never re-enters prompts.
- Make the acceptance surface specific enough that the next step can assess fit, parameterization, and execution notes without silently widening the selected workflow boundary.

## Routes

### Route guidance for the verifier
- `adaptation_request_framed`: the selected workflow, task boundary, and adaptation success criteria are explicit enough for fit analysis.
- `needs_rework`: the same framing boundary still holds, but the brief or criteria need local repair.
- `needs_replan`: the task trigger, selected workflow, or execution boundary changed materially and framing must restart.
- Reserved routes are only for genuine intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Ranking other workflows.
- Packaging the terminal adapted execution plan.
- Executing the selected workflow.

## Forbidden

- Do not choose a different workflow in this step.
- Do not hide the framing only in provider prose; the durable output must live in the named artifacts.
- Do not invent new runtime-owned metadata or a provider-facing packet abstraction.
