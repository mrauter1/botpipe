# Improve a workflow

`improve_workflow` investigates workflow intent, source, and recorded runs before
proposing one useful change, then implements it
in an isolated candidate, run executable checks, and independently review the
result. An optional fixed evaluator measures the original and the candidate.
The authoritative workflow is never automatically edited or replaced.

```python
from botpipe import Botpipe
from labs.workflows.improve_workflow import ImproveWorkflowParams, improve_workflow

with Botpipe(workspace=".") as runtime:
    run = runtime.run(
        improve_workflow,
        ImproveWorkflowParams(
            selected_workflow="devloop",
            objective="Improve review accuracy while preserving valid behavior",
            metric_view="reliability",
            run_refs=["failed-run"],
            evaluation_spec_path="evaluation-spec.json",
        ),
        request="Fix the recurring review failure while preserving valid behavior.",
    )
    if run.ok:
        print(run.value.outcome, run.value.summary)
        if run.value.candidate:
            print(run.value.candidate.root)
```

The CLI accepts the same validated parameter object:

```bash
botpipe run improve_workflow --workspace . \
  --input '[{"selected_workflow":"devloop","objective":"Improve review accuracy"},"Correct the recurring review failure"]'
```

`selected_workflow` accepts a catalog name, `module:function`, or
`file.py:function`. `run_refs` selects exact run IDs or `task/run` references;
otherwise the latest 25 matching runs that are not executing are selected.
Created and running runs do not consume that limit; explicit references remain exact.
`objective` is a free-text priority; the older `reliability`, `token_usage`, and
`latency` values remain valid. `metric_view` optionally selects one of those
three deterministic summaries. When it is unset, the evidence-v3 record retains
its compatibility reliability view; active model inputs still omit its ranking.
Deterministic summaries describe recorded burden, not predicted benefit, and do
not gate investigation or choose its target. Source identity and evidence checks
prevent
unrelated runs from being treated as observations of the selected workflow.
The workflow captures one canonical full surface manifest for the optimizer
baseline and fails clearly when that attribution is unavailable or changes
during capture.

## Outcomes

| Outcome | Meaning |
| --- | --- |
| `collect_evidence` | More relevant evidence is needed; no candidate was edited. |
| `no_change` | No change was proposed or the candidate left the source unchanged. |
| `rejected` | The proposal or implementation exhausted its revision allowance. |
| `candidate_ready` | Executable checks and independent review passed; improvement was not measured. |
| `improved`, `regressed`, `no_material_change`, `inconclusive` | The fixed baseline/candidate comparison produced this result. |

The typed result includes the structured intent/diagnostic assessment and its
frozen context-specific rubric, evidence, optional candidate
validation/review/comparison, and the consumed provider budget. A completed run
can therefore be a useful negative result. Runtime failures, unsafe recovery,
or exhausted provider budgets still fail or suspend the Botpipe run normally.

## Checks and limits

The default executable check is `python -m pytest -q`. Supply
`target_test_argv` for the project's actual checks; it is an argument list, never
a shell command. Discovery/import and compilation checks also run in isolation.
The model investigates, proposes, implements, and reviews in separate bounded
turns; deterministic code owns identities, metrics, validation, and comparison
outcomes. A source-only proposal carries no invented observation ID. When no run
history exists, source inspection may still identify an opportunity or explain
why execution evidence is needed.

`max_revisions=2` allows at most three implementation/check/review attempts
after one reviewed proposal. All provider work shares `max_provider_turns=12`,
`max_provider_seconds=1800`, and `provider_timeout=600`. Provider repair turns
are included. Executable validation has its own `validation_timeout=600`, and
the evaluation specification carries process and evaluator limits. These are
bounded operations, not an unbounded optimization search.

The evaluation specification, evaluator, and cases are frozen before
investigation. The model's qualitative success rubric is frozen before proposal
generation. Both remain fixed through editing and review.
Each implementation revision starts from the same verified source baseline and
gets its own workspace and evaluation records. Interrupted external evaluations
are reconciled from their exact attempt/result records; an unknown result is
never silently rerun. Completed Botpipe operations replay without provider calls.

An improvement claim is limited to the supplied cases and thresholds. Keep
development cases distinct from independent evaluation cases. Without a
comparative evaluator, passing tests produces `candidate_ready`.

## Replacement of earlier labs

This workflow replaces `workflow_run_history_to_failure_modes`,
`workflow_run_traces_to_optimization_candidates`,
`workflow_and_eval_to_refined_workflow_package`, and
`workflow_package_to_composable_building_blocks`. Their entry points and legacy
parameter aliases were removed. Start a fresh `improve_workflow` run; old lab
journals are not rewritten or replayed as this workflow.

Other labs remain separate experiments. This change does not introduce a new
runtime, phase language, or generic lab controller.
