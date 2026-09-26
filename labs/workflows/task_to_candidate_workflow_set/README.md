# Task To Candidate Workflow Set

Turn an arbitrary software-work task into a ranked candidate-workflow set, fit-gap package, and strategy-ready handoff.

Canonical name: `task_to_candidate_workflow_set`
Aliases: `candidate-workflow-set`, `workflow-candidate-set`

## Durable function design

`workflow.py` exports one ordinary Python workflow. Python controls framing, analysis, packaging, and replanning. Producers make the domain judgments; runtime checks keep rankings within the observed catalog and preserve them through packaging.

Every declared output is required when a phase returns `accepted`. Botpipe snapshots those files before completion, and later phases read immutable handles. A prerequisite-seeking `question` or `blocked` result may pause before files exist; it must not fabricate placeholder artifacts. The final typed `LabWorkflowResult` carries accepted handles in `artifacts` and convenience snapshot paths in `artifact_paths`.

## Invocation

```python
from botpipe import Botpipe
from labs.workflows.task_to_candidate_workflow_set import Params, workflow_callable

client = Botpipe(workspace=".")
result = client.run(
    workflow_callable,
    Params(task_title="Automate release-readiness review"),
    request="Find and rank workflows that can support this task.",
)
```

Parameters are validated before work starts. `max_provider_turns` (default 32) caps the whole workflow, including retries; human pauses have no wall-clock deadline. `request` contains the human-readable task.

## Phases and evidence

| Phase | Required produced artifacts |
| --- | --- |
| `frame_candidate_request` | `candidate_request_brief.md`, `workflow_fit_criteria.md` |
| `analyze_candidate_workflows` | `workflow_comparison_matrix.md`, `fit_gap_analysis.md` |
| `package_candidate_workflow_set` | `candidate_workflow_set.md`, `candidate_workflow_set_summary.json`, `candidate_workflow_next_action.md` |

Producer prompts remain phase-specific; independent reviewer prompts exist only for phases where a second judgment materially improves the outcome. `accepted` advances, while `needs_rework` repeats the phase with structured feedback and its previous artifact snapshots. `needs_replan` returns control to the phase's declared target through a workflow-owned Python loop. `question` and `blocked` suspend with `ask_human()` and retry the phase with the operator's `input_answer`; `failed` rejects the phase. No route table executes these outcomes.

## Inspection and replay

The journal records prompt reads, provider results, typed outcomes, usage, artifact dependencies, and operation timing. Replay uses the committed typed results and artifact snapshots. Source inspection reports dynamic topology and does not claim that unvisited Python branches executed.

## Validation

`tests/test_labs.py` imports and resolves every labs manifest, stages every package with `FakeProvider`, checks typed accepted outcomes, and verifies that all required artifacts were captured.
