# Workflow Portfolio To Operating System

Turn workflow capability and portfolio health evidence into explicit lifecycle recommendations, change candidates, and an operating-system governance package.

Canonical name: `workflow_portfolio_to_operating_system`
Aliases: `portfolio-operating-system`, `workflow-portfolio-governance`

## Durable function design

`workflow.py` exports one ordinary Python function decorated with `@workflow`. Python controls phase order, optional passes, loops, and nested workflows. Each phase runs a producer and verifier through durable `Session` operations. Producers return `LabPhaseDraft`; each verifier returns a package-specific `LabPhaseOutcome` subclass from `contracts.py`, so domain evidence is typed before control flow consumes it.

Every declared output is a required `Artifact`. Botpipe snapshots the provider-written file before the operation completes, and later phases read those immutable handles. A verifier may cite only captured artifact names. The final typed `LabWorkflowResult` carries the accepted handles in `artifacts`, convenience snapshot paths in `artifact_paths`, and unique candidate identifiers. When phases reuse an artifact name, the later accepted handle wins.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.workflow_portfolio_to_operating_system import (
    Params,
    workflow_callable,
)

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable, Params(...), request="Describe the requested outcome"
)
```

Parameters are validated by the package-local Pydantic `Params` model before any operation starts. `request` contains the human-readable task or evidence request.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_portfolio_governance` | `portfolio_governance_brief.md`, `lifecycle_criteria.md` |
| `analyze_portfolio_operating_model` | `portfolio_health_analysis.md`, `lifecycle_recommendations.json`, `portfolio_change_candidates.json` |
| `package_portfolio_operating_system` | `workflow_portfolio_operating_system.md`, `portfolio_operating_summary.json`, `portfolio_next_actions.md` |

Producer and verifier prompts remain phase-specific. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
