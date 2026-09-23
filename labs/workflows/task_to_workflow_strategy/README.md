# Task To Workflow Strategy

Turn an arbitrary software-work task into an explicit strategy package that chooses run-existing, compose, adapt, or create-new.

Canonical name: `task_to_workflow_strategy`
Aliases: `workflow-strategy`, `task-front-door`

## Durable function design

`workflow.py` exports one ordinary Python function decorated with `@workflow`. Python controls phase order, optional passes, loops, and nested workflows. Each phase runs a producer with `Provider.run` and a read-only verifier with typed `Provider.query`. Producers return `LabPhaseDraft`; each verifier returns a package-specific `LabPhaseOutcome` subclass from `contracts.py`, so domain evidence is typed before control flow consumes it.

Every declared output is a required `Artifact`. Botpipe snapshots the provider-written file before the operation completes, and later phases read those immutable handles. A verifier may cite only captured artifact names. The final typed `LabWorkflowResult` carries the accepted handles in `artifacts`, convenience snapshot paths in `artifact_paths`, and unique candidate identifiers. When phases reuse an artifact name, the later accepted handle wins.

The strategy workflow calls `task_to_candidate_workflow_set` directly. Botpipe records that call in an independent durable child scope before strategy selection, and the child's returned `artifacts` handles become immutable reads for the strategy phases.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.task_to_workflow_strategy import Params, workflow_callable

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable, Params(...), request="Describe the requested outcome"
)
```

Parameters are validated by the package-local Pydantic `Params` model before any operation starts. `request` contains the human-readable task or evidence request.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_task` | `task_strategy_brief.md`, `workflow_selection_criteria.md` |
| `select_strategy` | `strategy_decision.md` |
| `package_strategy` | `workflow_strategy_package.md`, `strategy_summary.json`, `strategy_next_action.md` |

Producer and verifier prompts remain phase-specific. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask_human()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
