# Company Operation To Recursive Improvement Cycle

Turn company work history plus workflow telemetry into an explicit next-cycle recursive improvement package and typed publication result.

Canonical name: `company_operation_to_recursive_improvement_cycle`
Aliases: `company-recursive-improvement`, `company-operation-cycle`

## Durable function design

`workflow.py` exports one ordinary Python function decorated with `@workflow`. Python controls phase order, optional passes, loops, and nested workflows. Each phase runs a producer with `Provider.run` and a read-only verifier with typed `Provider.query`. Producers return `LabPhaseDraft`; each verifier returns a package-specific `LabPhaseOutcome` subclass from `contracts.py`, so domain evidence is typed before control flow consumes it.

Every declared output is a required `Artifact`. Botpipe snapshots the provider-written file before the operation completes, and later phases read those immutable handles. A verifier may cite only captured artifact names. The final typed `LabWorkflowResult` carries the accepted handles in `artifacts`, convenience snapshot paths in `artifact_paths`, and unique candidate identifiers. When phases reuse an artifact name, the later accepted handle wins.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.company_operation_to_recursive_improvement_cycle import (
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
| `frame_company_operation` | `company_operation_brief.md`, `recursive_improvement_criteria.md` |
| `analyze_recursive_improvement_pressures` | `company_pressure_map.md`, `recursive_improvement_priority_matrix.md`, `recursive_improvement_candidates.json` |
| `package_recursive_improvement_cycle` | `recursive_improvement_cycle.md`, `recursive_improvement_summary.json`, `recursive_improvement_next_actions.md` |

Producer and verifier prompts remain phase-specific. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask_human()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
