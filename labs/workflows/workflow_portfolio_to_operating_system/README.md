# Workflow Portfolio To Operating System

Turn workflow capability and portfolio health evidence into explicit lifecycle recommendations, change candidates, and an operating-system governance package.

Canonical name: `workflow_portfolio_to_operating_system`
Aliases: `portfolio-operating-system`, `workflow-portfolio-governance`

## Durable function design

`workflow.py` exports one ordinary Python workflow. Python observes the catalog and run history, controls phases and replanning, and validates complete lifecycle coverage and published change candidates. Sparse history remains evidence uncertainty rather than an automatic change signal.

Every declared output is required when a phase returns `accepted`. Botpipe snapshots those files before completion, and later phases read immutable handles. A prerequisite-seeking `question` or `blocked` result may pause before files exist; it must not fabricate placeholder artifacts. The final typed `LabWorkflowResult` carries accepted handles in `artifacts` and convenience snapshot paths in `artifact_paths`.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.workflow_portfolio_to_operating_system import (
    Params,
    workflow_callable,
)

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable,
    Params(task_title="Review workflow portfolio health"),
    request="Recommend lifecycle actions and governance priorities.",
)
```

Parameters are validated before work starts. `max_provider_turns` (default 32) caps all provider work and retries; human pauses have no wall-clock deadline. `request` can refine the governance objective.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_portfolio_governance` | `portfolio_governance_brief.md`, `lifecycle_criteria.md` |
| `analyze_portfolio_operating_model` | `portfolio_health_analysis.md`, `lifecycle_recommendations.json`, `portfolio_change_candidates.json` |
| `package_portfolio_operating_system` | `workflow_portfolio_operating_system.md`, `portfolio_operating_summary.json`, `portfolio_next_actions.md` |

Producer prompts remain phase-specific; independent reviewer prompts exist only for phases where a second judgment materially improves the outcome. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask_human()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
