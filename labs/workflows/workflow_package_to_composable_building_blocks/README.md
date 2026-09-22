# Workflow Package To Composable Building Blocks

Turn one selected workflow package plus decomposition evidence into a candidate decomposition overlay and typed evaluation result without mutating the authoritative workflow package.

Canonical name: `workflow_package_to_composable_building_blocks`
Aliases: `workflow-package-to-building-blocks`, `workflow-decomposition-package`

## Durable function design

`workflow.py` exports one ordinary Python function decorated with `@workflow`. Python controls phase order, optional passes, loops, and nested workflows. Each phase runs a managed `Provider` producer and an independent provider verifier. Producers return `LabPhaseDraft`; each verifier returns a package-specific `LabPhaseOutcome` subclass from `contracts.py`, so domain evidence is typed before control flow consumes it.

Every declared output is a required `Artifact`. Botpipe snapshots the provider-written file before the operation completes, and later phases read those immutable handles. A verifier may cite only captured artifact names. The final typed `LabWorkflowResult` carries the accepted handles in `artifacts`, convenience snapshot paths in `artifact_paths`, and unique candidate identifiers. When phases reuse an artifact name, the later accepted handle wins.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.workflow_package_to_composable_building_blocks import (
    Params,
    workflow_callable,
)

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable, Params(...), request="Describe the requested outcome"
)
```

Parameters are validated by the package-local Pydantic `Params` model before any operation starts. `request` contains the human-readable task or evidence request.

Candidate validation freezes the original project and selected workflow surface
before model edits, imports the staged workflow in a clean subprocess, and runs
the configured check inside an isolated execution arm. Prefer
`target_test_argv`; legacy `target_test_command` is parsed into argv without a
shell, and the two forms are mutually exclusive. `validation_timeout` bounds the
check. The derived manifest and validation report are evidence for review only;
the workflow never promotes the candidate into the authoritative package.

The candidate workspace snapshots the selected package and hashes each original file. The decomposition may add new building-block modules only inside that package boundary, while explicit `candidate_paths` can narrow the editable surface. A configured `target_test_argv` command runs without shell parsing in an isolated repository overlay. Its typed report distinguishes modified, added, removed, and unchanged paths and verifies that authoritative sources were not changed.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_decomposition_request` | `decomposition_request_brief.md`, `decomposition_success_criteria.md` |
| `design_decomposition_plan` | `decomposition_plan.md`, `building_block_contracts.json` |
| `implement_candidate_decomposition` | `candidate_decomposition_manifest.json`, `candidate_decomposition_notes.md` |
| `evaluate_candidate_decomposition` | `decomposition_verification_report.md`, `decomposition_summary.json`, `decomposition_next_action.md` |

Producer and verifier prompts remain phase-specific. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask_human()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
