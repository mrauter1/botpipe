# Task To Workflow Strategy

Turn an arbitrary software-work task into an explicit strategy package that chooses run-existing, compose, adapt, or create-new.

Canonical name: `task_to_workflow_strategy`
Aliases: `workflow-strategy`, `task-front-door`

## Durable function design

`workflow.py` exports one ordinary Python workflow. Python controls the child candidate-set call, phase order, and replanning. These strategy phases use producers only because their outputs are constrained by the child result and explicit cross-phase checks.

Every declared output is required when a phase returns `accepted`. Botpipe snapshots those files before completion, and later phases read immutable handles. A prerequisite-seeking `question` or `blocked` result may pause before files exist; it must not fabricate placeholder artifacts. The final typed `LabWorkflowResult` carries accepted handles in `artifacts` and convenience snapshot paths in `artifact_paths`.

The strategy workflow calls `task_to_candidate_workflow_set` directly. Botpipe records that call in an independent durable child scope before strategy selection, and the child's returned `artifacts` handles become immutable reads for the strategy phases.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.task_to_workflow_strategy import Params, workflow_callable

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable,
    Params(task_title="Automate release-readiness review"),
    request="Choose whether to run, compose, adapt, or create a workflow.",
)
```

Parameters are validated before work starts. `max_provider_turns` (default 32) caps the whole workflow, including child calls and retries; human pauses have no wall-clock deadline. `request` contains the human-readable task.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_task` | `task_strategy_brief.md`, `workflow_selection_criteria.md` |
| `select_strategy` | `strategy_decision.md` |
| `package_strategy` | `workflow_strategy_package.md`, `strategy_summary.json`, `strategy_next_action.md` |

Producer prompts remain phase-specific; independent reviewer prompts exist only for phases where a second judgment materially improves the outcome. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask_human()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
