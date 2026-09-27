# Improve a workflow

`improve_workflow` diagnoses one workflow from frozen source and run evidence,
reviews one bounded proposal, implements it in an isolated candidate, runs
executable checks, and performs independent source review. Comparative
measurement is optional. The authoritative workflow is never edited or promoted
automatically.

```python
from botpipe import Botpipe
from labs.workflows.improve_workflow import ImproveWorkflowParams, improve_workflow

with Botpipe(workspace=".") as runtime:
    run = runtime.run(
        improve_workflow,
        ImproveWorkflowParams(
            selected_workflow="devloop",
            objective="Improve review accuracy while preserving valid behavior",
            run_refs=["failed-run"],
            execute_trials=True,
            trial_cases=[
                {
                    "case_id": "review_failure",
                    "description": "Handle the recorded review failure",
                    "kwargs": {"request": "Review the fixture change"},
                    "workspace": "fixture",
                    "judge_input_paths": ["change.diff"],
                    "output_paths": ["review.json"],
                }
            ],
            trial_fixture_path="tests/fixtures/review_case",
        ),
        request="Fix the recurring review failure while preserving valid behavior.",
    )
```

The CLI accepts the same validated parameter object:

```bash
botpipe run improve_workflow --workspace . \
  --input '[{"selected_workflow":"devloop","objective":"Improve review accuracy"},"Correct the recurring review failure"]'
```

`selected_workflow` accepts a catalog name, `module:function`, or
`file.py:function`. `run_refs` selects exact run IDs or `task/run` references;
otherwise the latest 25 matching runs that are not executing are selected.
Created and running runs do not consume that limit.

## Evidence and proposal

The workflow freezes two read-only inputs for every analysis turn: the selected
workflow's complete captured source surface and a journal-evidence tree with run
and operation records, recorded prompts, responses, errors, and referenced
artifact versions. Deterministic facts such as recorded status, counts, and
usage cite focused observation IDs. Textual trace claims about prompts,
responses, rejection reasons, and artifact contents cite a root-relative frozen
path plus an exact quote. Source claims name captured source paths and may use
the same exact-quote form. Inference remains explicitly separate from direct
evidence. Python validates each basis and citation.

Correctable citation and model-proposed case errors receive bounded feedback.
`max_grounding_repairs=2` allows two additional attempts. Changed frozen bytes,
path escapes, and other integrity failures stop rather than being treated as
model typos. The investigator freezes the rubric and any native trial cases
before proposing a candidate.

The accepted recommendation passes directly into implementation as a typed
value. The workflow does not publish and reload an internal recommendation
receipt; its `receipt` field is `None`. A separate-session reviewer may reject
the proposal before any edit. Each implementation revision starts from the same
verified baseline and can change only the captured workflow surface.

## Evaluation choices

With neither option selected, successful checks and review return
`candidate_ready`.

Set `execute_trials=true` for native paired trials of the selected workflow. This
is explicit authorization to execute both baseline and candidate with the
configured provider, tools, inputs, and policy. Use it only when those executions
and their possible external effects are authorized. Trial processes have
separate code trees, workspaces, state, timeouts, and owned-process containment;
they do not isolate remote side effects.
Native subprocesses reconstruct the configured Codex provider. An unsupported
in-process provider produces `inconclusive` instead of silently switching providers.

Caller supplied `trial_cases` take precedence. Otherwise the investigator may
propose cases. They are validated and frozen with the rubric. Cases use an empty
workspace or a snapshot of the explicit `trial_fixture_path` directory taken
when the plan is frozen. Historical runs do not retain their initial workspace,
so they cannot reconstruct this fixture. Each case must be self-contained in its
`args`/`kwargs`, captured `assets`, or that explicit fixture.

`assets` maps a case-workspace destination to frozen analysis evidence. Every
asset destination is automatically inlined as judge reference evidence.
`judge_input_paths` adds other fixture-relative reference files needed to apply
the rubric. `output_paths` declares result files to capture after each arm, even
when the workflow does not publish them as Botpipe artifacts. These bounded
relative-path lists are frozen with the cases and rubric. Evaluation records the
exact declared result bytes and a deterministic comparison with the frozen
fixture. The caller or investigating model must name every reference and output
file the rubric requires; the tool-free judge cannot follow an otherwise
unreadable filename.

Each arm has `max_provider_turns=12` and `timeout_seconds=180` by default. The
trial phase has `max_elapsed_seconds=1200` and admits a pair only when enough
allowance remains for both arm caps. Execution order and anonymous A/B labels are
deterministic hashes of the run, case, and repetition and are recorded per pair.
The plan binds source and fixture tree hashes; it does not add a Git HEAD record.

Judging starts after trial execution under a separate
`max_judge_turns=12`, `max_judge_seconds=600`, and
`judge_timeout_seconds=120` allowance. A fresh, tool-free judge applies the
frozen rubric to a bounded anonymous behavior packet. Anonymous labels cannot
hide inherited instructions, so judging overrides provider/native instructions
and suppresses project instructions, skills, and memories in an empty workspace.
If native isolation cannot be enforced (including configured global Codex
`AGENTS.md` instructions), the comparison is `inconclusive` without a fallback
judge call. Anonymous labels also cannot
hide identity revealed intrinsically by output content. Binary artifact content
is omitted. Binary, oversized, or missing declared input/output bytes are
explicit essential-evidence omissions. Cases needing those files must supply
bounded judgeable text/JSON content; otherwise the comparison is
`inconclusive`. Infrastructure failures, unavailable cases, conflicting results,
unknown criteria, or exhausted judge allowance are also inconclusive. This
includes requested evaluations with no executable frozen case; they record why
the cases are unavailable and dispatch no trials or judges.

All native trial results are scoped to the frozen development cases. Improvement
requires at least one candidate win, no losses, and every required obligation
met. A baseline win reports `regressed`; all ties report
`no_material_change`. Nothing here claims performance on untested inputs.

Alternatively, `evaluation_spec_path` runs the existing caller supplied external
evaluator. It is mutually exclusive with `execute_trials`. Native trials do not
require an external script, and neither evaluation mode is required to build a
validated candidate.

## Outcomes

| Outcome | Meaning |
| --- | --- |
| `collect_evidence` | More relevant evidence is needed; no candidate was edited. |
| `no_change` | No change was proposed or the candidate left source unchanged. |
| `rejected` | Proposal or implementation exhausted its revision allowance. |
| `candidate_ready` | Checks and independent review passed; improvement was not measured. |
| `improved` | Frozen evaluated cases include a candidate win, no loss, and no required-criterion failure. |
| `regressed` | At least one frozen evaluated pair favors the baseline and none favors the candidate. |
| `no_material_change` | Every frozen evaluated comparison is a tie. |
| `inconclusive` | Evidence, availability, infrastructure, judgment, or consistency was insufficient. |

The typed result contains the assessment, rubric, evidence identities, reviewed
proposal, optional frozen trial plan, candidate validation/review/evaluation,
and orchestration provider-budget snapshot. Runtime failures, unsafe recovery,
or exhausted orchestration budgets still fail or suspend the Botpipe run.

## Checks and bounds

The default validation command is `python -m pytest -q`. Supply
`target_test_argv` for the selected project's checks; it is an argument list,
not a shell string. Compilation and discovery/import checks also run against the
staged candidate.

Orchestration defaults are `max_provider_turns=12`,
`max_provider_seconds=1800`, `provider_timeout=600`, `max_revisions=2`, and
`validation_timeout=600`. Provider repairs count toward these bounds. Native
trials and judges use the separate `TrialSettings` bounds above. An external
evaluator uses the bounds in its frozen specification.

See [Workflow improvement](../../../docs/optimizer.md) for the evidence layout,
all limits, judge-packet behavior, and lower-level APIs.

## Replacement of earlier labs

This workflow replaces `workflow_run_history_to_failure_modes`,
`workflow_run_traces_to_optimization_candidates`,
`workflow_and_eval_to_refined_workflow_package`, and
`workflow_package_to_composable_building_blocks`. Their entry points and legacy
parameter aliases were removed. Start a fresh `improve_workflow` run; old lab
journals are not rewritten or migrated.
