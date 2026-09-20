# Workflow Run Traces To Optimization Candidates

Turn selected workflow run traces into step-local and workflow-level optimization candidates without mutating the authoritative workflow.

Canonical name: `workflow_run_traces_to_optimization_candidates`
Aliases: `workflow-optimization-candidates`, `trace-to-optimization-candidates`

## Durable function design

`workflow.py` exports one ordinary Python function decorated with `@workflow`. Python controls phase order, optional passes, loops, and nested workflows. Each phase runs a producer and verifier through durable `Session` operations. Producers return `LabPhaseDraft`; each verifier returns a package-specific `LabPhaseOutcome` subclass from `contracts.py`, so domain evidence is typed before control flow consumes it.

Every declared output is a required `Artifact`. Botpipe snapshots the provider-written file before the operation completes, and later phases read those immutable handles. A verifier may cite only captured artifact names. The final typed `LabWorkflowResult` carries the accepted handles in `artifacts`, convenience snapshot paths in `artifact_paths`, and unique candidate identifiers. When phases reuse an artifact name, the later accepted handle wins.

The optimizer reads `Botpipe.inspect()` records and a captured callable/source manifest. Only observed operations receive metrics or candidate scores. Declared paths with no observations are published as evidence gaps. Every deterministic candidate cites the operation IDs that support it.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.workflow_run_traces_to_optimization_candidates import (
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
| `frame_observed_optimization` | `workflow_optimization_scope.json`, `observed_trace_corpus.json`, `selected_workflow_source_manifest.json` |
| `rank_observed_targets` | `step_optimization_priority_report.json`, `step_trace_metrics.json` |
| `mine_observed_failures` | `workflow_failure_scenarios.json` |
| `optimize_producer_contracts` | `producer_prompt_optimization_candidates.json` |
| `optimize_verifier_rubrics` | `verifier_rubric_optimization_candidates.json` |
| `optimize_tokens` | `token_optimization_candidates.json` |
| `generate_adversarial_cases` | `adversarial_case_candidates.json` |
| `optimize_workflow_boundary` | `workflow_level_optimization_candidates.json` |
| `package_validated_candidates` | `workflow_optimization_scorecard.json`, `optimization_next_actions.md` |

Producer and verifier prompts remain phase-specific. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
