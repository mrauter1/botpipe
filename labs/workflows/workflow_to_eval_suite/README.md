# Workflow To Eval Suite

Turn one selected workflow into a reusable evaluation-suite package with a validated eval-case manifest and typed publication result.

Canonical name: `workflow_to_eval_suite`
Aliases: `workflow-eval-suite`, `eval-suite-package`

## Durable function design

`workflow.py` exports one ordinary Python workflow. Python observes the selected contract, validates the case manifest, computes suite identity, and controls replanning. Producers design cases and package the suite but never execute it or claim measured quality.

Every declared output is required when a phase returns `accepted`. Botpipe snapshots those files before completion, and later phases read immutable handles. A prerequisite-seeking `question` or `blocked` result may pause before files exist; it must not fabricate placeholder artifacts. The final typed `LabWorkflowResult` carries accepted handles in `artifacts` and convenience snapshot paths in `artifact_paths`.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.workflow_to_eval_suite import Params, workflow_callable

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable,
    Params(
        selected_workflow="devloop",
        task_title="Build a regression evaluation suite",
    ),
    request="Design reusable cases for review accuracy and recovery behavior.",
)
```

Parameters are validated before work starts. `max_provider_turns` (default 32) caps all provider work and retries; human pauses have no wall-clock deadline. `request` contains the evaluation intent.

An optimizer-v2 evaluation-case recommendation may be supplied with the
`optimization_receipt_path` and `candidate_id` pair. Both fields are optional as
a pair and neither may appear alone. The workflow validates the accepted
receipt, review, evidence snapshot, baseline surface, handoff, and candidate,
and rejects every candidate kind except `evaluation_case`.

After case design, a retry-safe activity validates the manifest before packaging. Every case must have a unique ID, one of `benchmark`, `edge`, or `adversarial`, a prompt, expected artifacts, and valid callable inputs. For the common `workflow(params: BaseModel, request: str = "")` shape, `workflow_parameters` is the flat `Params` object and the case `prompt` supplies the human request separately. Other callable shapes use a full keyword-argument mapping. The typed validation result states when expected artifact names could not be checked against a static surface because ordinary Python workflows declare outputs dynamically.

The suite must contain at least one case, but need not include all three categories. Design chooses categories that add meaningful coverage and explains omitted categories in their corresponding matrices.

The published suite receives a content-derived `evaluation_suite_id`. Suites
created from an optimizer recommendation also retain the exact
`source_candidate_id`. Candidate-suggested cases remain development cases; this
workflow packages and validates them but does not execute them or claim measured
improvement.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_evaluation_target` | `evaluation_request_brief.md`, `evaluation_dimensions.md` |
| `design_eval_cases` | `benchmark_case_matrix.md`, `edge_case_matrix.md`, `adversarial_case_matrix.md`, `eval_case_manifest.json`, `eval_rubric.md` |
| `package_workflow_eval_suite` | `workflow_eval_suite.md`, `workflow_eval_suite_summary.json`, `workflow_eval_next_action.md` |

Producer prompts remain phase-specific; independent reviewer prompts exist only for phases where a second judgment materially improves the outcome. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask_human()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
