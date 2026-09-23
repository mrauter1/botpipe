# Workflow Idea To Workflow Package

Compare candidate additions, design a workflow package, build it, verify it, and publish evidence.

Canonical name: `workflow_idea_to_workflow_package`
Aliases: `workflow-builder`, `workflow-idea-builder`

## Durable function design

`workflow.py` exports one ordinary Python function decorated with `@workflow`. Python controls phase order, optional passes, loops, and nested workflows. Each phase runs a producer with `Provider.run` and a read-only verifier with typed `Provider.query`. Producers return `LabPhaseDraft`; each verifier returns a package-specific `LabPhaseOutcome` subclass from `contracts.py`, so domain evidence is typed before control flow consumes it.

Every declared output is a required `Artifact`. Botpipe snapshots the provider-written file before the operation completes, and later phases read those immutable handles. A verifier may cite only captured artifact names. The final typed `LabWorkflowResult` carries the accepted handles in `artifacts`, convenience snapshot paths in `artifact_paths`, and unique candidate identifiers. When phases reuse an artifact name, the later accepted handle wins.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.workflow_idea_to_workflow_package import Params, workflow_callable

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable, Params(...), request="Describe the requested outcome"
)
```

Parameters are validated by the package-local Pydantic `Params` model before any operation starts. `request` contains the human-readable task or evidence request.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_candidate` | `workflow_idea_brief.md`, `candidate_selection_criteria.md` |
| `design_package` | `workflow_design.md`, `workflow_contract.json` |
| `build_package` | `workflow_package_manifest.json`, `implementation_notes.md` |
| `evaluate_package` | `workflow_evaluation.md`, `workflow_package_summary.json`, `workflow_next_action.md` |

The build manifest identifies its generated callable with an explicit repo-relative
`file.py:function` reference. The file must be the selected shape's entry file:
the single workflow file for `single`, or `flow.py` for `flow_specs` and `package`.
Catalog lookup belongs to later discovery, after the generated package is
materialized and validated, and cannot replace this entry reference.

Producer and verifier prompts remain phase-specific. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask_human()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
