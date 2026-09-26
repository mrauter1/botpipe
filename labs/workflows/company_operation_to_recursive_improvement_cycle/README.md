# Company Operation To Recursive Improvement Cycle

Turn company work history plus workflow telemetry into a bounded, evidence-backed improvement cycle with explicit stopping conditions.

Canonical name: `company_operation_to_recursive_improvement_cycle`
Aliases: `company-recursive-improvement`, `company-operation-cycle`

## Durable function design

`workflow.py` exports one ordinary Python workflow. Python observes catalog and run history, controls phases and replanning, and validates the published candidates and summary. The workflow recommends follow-through but never launches a universal recursive loop.

Every declared output is required when a phase returns `accepted`. Botpipe snapshots those files before completion, and later phases read immutable handles. A prerequisite-seeking `question` or `blocked` result may pause before files exist; it must not fabricate placeholder artifacts. The final typed `LabWorkflowResult` carries accepted handles in `artifacts` and convenience snapshot paths in `artifact_paths`.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.company_operation_to_recursive_improvement_cycle import (
    Params,
    workflow_callable,
)

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable,
    Params(task_title="Review workflow delivery and reliability"),
    request="Recommend the next bounded improvement cycle.",
)
```

Parameters are validated before work starts. `max_provider_turns` (default 32) caps all provider work and retries; human pauses have no wall-clock deadline. `request` can refine the operational review.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_company_operation` | `company_operation_brief.md`, `recursive_improvement_criteria.md` |
| `analyze_recursive_improvement_pressures` | `company_pressure_map.md`, `recursive_improvement_priority_matrix.md`, `recursive_improvement_candidates.json` |
| `package_recursive_improvement_cycle` | `recursive_improvement_cycle.md`, `recursive_improvement_summary.json`, `recursive_improvement_next_actions.md` |

Producer prompts remain phase-specific; independent reviewer prompts exist only for phases where a second judgment materially improves the outcome. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask_human()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
