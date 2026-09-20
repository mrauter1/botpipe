# Workflow To Eval Suite

Turn one selected workflow into a reusable evaluation-suite package with a validated eval-case manifest and typed publication result.

Canonical name: `workflow_to_eval_suite`
Aliases: `workflow-eval-suite`, `eval-suite-package`

## Durable function design

`workflow.py` exports one ordinary Python function decorated with `@workflow`. Python controls phase order, optional passes, loops, and nested workflows. Each phase runs a producer and verifier through durable `Session` operations. Producers return `LabPhaseDraft`; each verifier returns a package-specific `LabPhaseOutcome` subclass from `contracts.py`, so domain evidence is typed before control flow consumes it.

Every declared output is a required `Artifact`. Botpipe snapshots the provider-written file before the operation completes, and later phases read those immutable handles. A verifier may cite only captured artifact names. The final typed `LabWorkflowResult` carries the accepted handles in `artifacts`, convenience snapshot paths in `artifact_paths`, and unique candidate identifiers. When phases reuse an artifact name, the later accepted handle wins.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.workflow_to_eval_suite import Params, workflow_callable

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable, Params(...), request="Describe the requested outcome"
)
```

Parameters are validated by the package-local Pydantic `Params` model before any operation starts. `request` contains the human-readable task or evidence request.

After case design, a retry-safe activity validates the manifest before packaging. Every case must have a unique ID, one of `benchmark`, `edge`, or `adversarial`, a prompt, expected artifacts, and valid callable inputs. For the common `workflow(params: BaseModel, request: str = "")` shape, `workflow_parameters` is the flat `Params` object and the case `prompt` supplies the human request separately. Other callable shapes use a full keyword-argument mapping. The typed validation result states when expected artifact names could not be checked against a static surface because ordinary Python workflows declare outputs dynamically.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_evaluation_target` | `evaluation_request_brief.md`, `evaluation_dimensions.md` |
| `design_eval_cases` | `benchmark_case_matrix.md`, `edge_case_matrix.md`, `adversarial_case_matrix.md`, `eval_case_manifest.json`, `eval_rubric.md` |
| `package_workflow_eval_suite` | `workflow_eval_suite.md`, `workflow_eval_suite_summary.json`, `workflow_eval_next_action.md` |

Producer and verifier prompts remain phase-specific. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
