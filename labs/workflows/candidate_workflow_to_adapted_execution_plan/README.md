# Candidate Workflow To Adapted Execution Plan

Turn a chosen workflow plus task context into an execution-ready adapted plan with validated workflow parameters.

Canonical name: `candidate_workflow_to_adapted_execution_plan`
Aliases: `adapted-execution-plan`, `workflow-adaptation-plan`

## Durable function design

`workflow.py` exports one ordinary Python workflow. Python observes the selected contract, controls phases and replanning, and validates proposed parameters against the selected callable. Producers cannot change the selected workflow or its analyzed artifact surface.

Every declared output is required when a phase returns `accepted`. Botpipe snapshots those files before completion, and later phases read immutable handles. A prerequisite-seeking `question` or `blocked` result may pause before files exist; it must not fabricate placeholder artifacts. The final typed `LabWorkflowResult` carries accepted handles in `artifacts` and convenience snapshot paths in `artifact_paths`.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.candidate_workflow_to_adapted_execution_plan import (
    Params,
    workflow_callable,
)

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable,
    Params(
        selected_workflow="devloop",
        task_title="Adapt devloop for an API migration",
    ),
    request="Produce an execution-ready plan for the migration.",
)
```

Parameters are validated before work starts. `max_provider_turns` (default 32) caps all provider work and retries; human pauses have no wall-clock deadline. `request` contains the human-readable task.

Before completion, the workflow reads the captured `proposed_workflow_parameters.json` artifact and validates it against the selected callable. A first Pydantic parameter accepts the ergonomic flat model mapping only when every remaining callable argument is optional. Other signatures require a complete keyword-argument mapping. The canonical validated mapping is retained as the typed activity result in the durable journal.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_adaptation_request` | `adaptation_request_brief.md`, `adaptation_success_criteria.md` |
| `analyze_adaptation_surface` | `workflow_fit_assessment.md`, `step_adaptation_matrix.md` |
| `package_adapted_execution_plan` | `adapted_execution_plan.md`, `proposed_workflow_parameters.json`, `adapted_execution_summary.json`, `adapted_execution_next_action.md` |

Producer prompts remain phase-specific; independent reviewer prompts exist only for phases where a second judgment materially improves the outcome. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask_human()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
