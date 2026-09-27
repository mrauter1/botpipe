# Workflow improvement

The `improve_workflow` lab turns workflow intent, source, and available run
history into an isolated, validated candidate. It performs model-led diagnosis,
freezes a context-specific rubric before editing, reviews one proposal,
implements it against a captured baseline, runs executable checks, and performs
independent source review. Comparative evaluation is optional. The authoritative
workflow is never edited or promoted automatically.

```bash
botpipe run improve_workflow --workspace . \
  --input '[{"selected_workflow":"devloop","objective":"Improve review accuracy without changing valid behavior"},"Correct recurring failures"]'
```

See the [workflow guide](../labs/workflows/improve_workflow/README.md) for Python
usage and the complete parameter surface. The workflow uses ordinary durable
functions and optimizer primitives; it does not add another scheduler or phase
language.

## Evidence and diagnosis

`selected_workflow` accepts a catalog name, `module:function`, or
`file.py:function`. By default the latest 25 matching runs that are not executing
are selected. Created and running runs do not consume the history limit.
`run_refs` instead selects exact run IDs or `task/run` references.

Analysis has two frozen, read-only roots:

- the captured workflow source surface; and
- a journal-evidence tree containing run projections, operation records,
  recorded prompts, responses, errors, and the exact captured versions of
  referenced artifacts.

The model receives relative paths within the relevant root. Deterministic facts
such as recorded status, counts, and usage cite focused observation IDs without
transcribing text. Claims about prompt, response, rejection, or artifact content
use a trace citation: a relative frozen-evidence path and an exact UTF-8 quote.
Source claims name captured source paths and may quote them the same way;
inferences carry no direct citation. Python checks each basis, path boundary,
and quote verbatim. The source and evidence inventories are hashed and rechecked
between analysis, proposal, and review turns.

The investigation may repair a correctable citation, quote, or model-proposed
trial-plan error with precise feedback. `max_grounding_repairs` defaults to 2
additional attempts. Path escapes, changed frozen bytes, unsafe ownership, and
other integrity failures fail rather than entering this repair loop. Caller
supplied invalid trial cases also fail instead of being rewritten by the model.

The investigation explains intent, assesses the whole workflow and relevant
steps, and freezes a qualitative rubric before a candidate is proposed. Each
criterion names the evidence needed, how it can be falsified, and whether it is
an obligation that must be preserved. Proposal and implementation receive that
same rubric and cannot redefine success around the candidate.

`objective` is a free-text priority. `metric_view` may select `reliability`,
`token_usage`, or `latency`; otherwise the evidence record retains its
neutral metrics without computing an objective ranking. Explicit views are
descriptive summaries of recorded
burden. They do not establish causality, rank the model's target, predict benefit,
or replace source and behavioral evidence.

The active internal handoff is the typed `Recommendation`. It carries the
assessment, reviewed candidate set, baseline manifest, frozen trial plan, and
analysis identities directly. `improve_workflow` does not publish and reload an
internal optimization receipt, and `Recommendation.receipt` remains `None`.
Lower-level recommendation publication APIs remain available for external
consumers that need a durable export.

## Candidate implementation

A separate-session reviewer can reject the proposal before editing. The builder
then changes only the captured workflow surface in a candidate workspace. Each
revision starts from the same verified baseline. Compilation, discovery/import,
the caller's `target_test_argv`, and independent source review run before a
candidate is accepted. `max_revisions=2` permits three implementation attempts.
Passing these checks without a valid comparison produces `candidate_ready`.

The workflow returns `ImproveWorkflowResult`. Its candidate includes changed
paths, exact validation evidence, independent review, and any evaluation record.
Possible comparison outcomes are `improved`, `regressed`,
`no_material_change`, and `inconclusive`. Every result remains scoped to the
frozen development cases that actually ran; untested inputs are not assessed.
No outcome promotes the candidate automatically.

## Native rubric trials

Set `execute_trials=true` to execute the selected workflow itself for paired
baseline/candidate trials. This is an opt-in execution mode. Enable it only when
the caller is authorized to execute the chosen workflow and its configured
provider/tools against the supplied inputs. The trial subprocesses isolate code,
workspaces, state directories, and owned child processes. They do not isolate
remote or external side effects, so do not use production-writing cases as
experiments.
Native subprocesses reconstruct the configured Codex provider. Unsupported
in-process providers produce `inconclusive` without switching to another provider.

Cases come from `trial_cases` when the caller supplies them. Otherwise the
investigator may propose cases. In both forms Python validates invocation
arguments and freezes the cases with the rubric before candidate implementation.
A case can start from an empty workspace or from a snapshot of the explicit
`trial_fixture_path` directory. That snapshot is captured when the evaluation
plan is frozen. Historical run records do not reconstruct the workspace's
initial state; a fixture case without that explicit directory is unavailable.
A case must be self-contained through its `args`/`kwargs`, captured `assets`, or
the explicit fixture. `assets` maps a destination in the case workspace to a
file in the frozen analysis-evidence root. Every asset destination is
automatically included as inline reference evidence for the judge.

`judge_input_paths` names additional fixture-relative reference files that the
rubric requires. `output_paths` names workspace files whose post-run bytes are
part of the behavioral result, including workflows that do not publish those
files as Botpipe `Artifact` handles. Both are lists of bounded relative workspace
paths and are frozen with the case and rubric. The trial captures the declared
result bytes and a deterministic comparison with the frozen starting fixture.
Case authors and the investigating model must declare every reference and
result file needed by the rubric; a tool-free judge cannot open an unexpanded
filename from a prompt or return value.

Each baseline/candidate arm gets the same frozen case bytes and limits. The
execution order and anonymous A/B label are derived deterministically from the
run ID, case ID, and repetition, then recorded per pair. This reduces incidental
order bias without claiming randomness. The trial identity binds code-tree and
fixture-tree hashes; it does not add or rely on a Git HEAD record.

`TrialSettings` controls the native path:

| Setting | Default | Meaning |
| --- | ---: | --- |
| `max_provider_turns` | 12 | Provider dispatches available inside each trial. |
| `timeout_seconds` | 180 | Process and provider-time allowance for each arm. |
| `max_elapsed_seconds` | 1200 | Trial-phase allowance used to admit only complete pairs. |
| `repetitions` | 1 | Paired repetitions per case. |
| `max_judge_turns` | 12 | Dispatches in the separate post-trial judge phase. |
| `max_judge_seconds` | 600 | Durable time allowance for all judgments. |
| `judge_timeout_seconds` | 120 | Timeout for one judge dispatch. |
| `reverse_order_judgment` | false | Also judge the same pair with A/B reversed. |
| `max_packet_bytes` | 48000 | Maximum anonymous judge packet size. |
| `max_output_bytes` | 2 MiB | Maximum captured trial result size. |
| `max_fixture_bytes` | 50 MiB | Fixture snapshot byte bound. |
| `max_fixture_files` | 10000 | Fixture snapshot file bound. |

Before starting a pair, the trial phase checks that its remaining
`max_elapsed_seconds` can cover both arms at their full `timeout_seconds` caps.
If not, the pair is unavailable rather than running one arm asymmetrically.
The judge allowance begins after the trial phase, so execution cannot consume
the separately configured judge turns or time.

A tool-free, fresh-session judge receives the fixed task, rubric, comparison
rule, and sanitized behavioral outputs under anonymous labels. Source paths,
provider inputs, run identities, and other arm-identifying runtime metadata are
removed. This provides blindness only to the extent that the outputs themselves
do not reveal their origin. Do not describe a comparison as blind when names or
behavior intrinsically identify an arm.

The judge applies every criterion to both outputs and must quote exact excerpts
from its packet. Optional operation detail may be omitted to fit the byte limit.
Missing essential return values, errors, artifact evidence, or other required
content makes the packet and result `inconclusive`; it is never silently
truncated into proof. Raw/binary artifact content is not supplied to the judge.
The same rule applies to declared input and output files: binary, oversized, or
missing essential bytes are reported explicitly and make the comparison
inconclusive. A case that depends on them must expose suitable bounded inline
text/JSON evidence. Trial infrastructure errors are likewise not scored as
workflow behavior.

The conservative aggregation rule reports improvement only when at least one
pair favors the candidate, no evaluated pair favors the baseline, and every
required preservation criterion is met. Losses report regression, all ties
report no material change, and conflicts, missing evidence, unknown criteria,
invalid judgments, unavailable cases, or exhausted judge allowance report
inconclusive. Optional reverse-order judgments must agree after label
normalization.

## External paired evaluator

`evaluation_spec_path` remains available for a caller supplied executable
evaluator and is mutually exclusive with `execute_trials`. It freezes the
specification, evaluator, cases, repetitions, settings, metrics, and thresholds,
then runs one bounded evaluator subprocess per source arm. No external evaluator
script is required for native rubric trials or for producing a validated
`candidate_ready` result.

The external evaluator is responsible for invoking the workflow and producing
its strict result record. Freezing the case file does not freeze every service it
references. Execution trees are source isolation, not remote-effect isolation.
Missing, stale, duplicate, oversized, timed-out, cancelled, or
identity-mismatched output is incomplete and cannot support an improvement
claim. Library consumers can use `load_evaluation_spec`,
`run_paired_evaluation`, and `validate_paired_evaluation_record` from
`botpipe_optimizer.paired_evaluation` directly.

## Orchestration limits

| Parameter | Default |
| --- | ---: |
| `history_limit` | 25 runs |
| `max_grounding_repairs` | 2 additional attempts |
| `max_revisions` | 2 additional proposal/implementation attempts |
| `max_provider_turns` | 12 orchestration dispatches, including repairs |
| `provider_timeout` | 600 seconds per orchestration turn |
| `max_provider_seconds` | 1800 seconds for orchestration provider work |
| `validation_timeout` | 600 seconds per external validation command |
| `max_evidence_bytes` | 50 MiB |
| `max_snapshot_bytes` | 50 MiB |
| `max_output_bytes` | 10 MiB of recommendation records |

The orchestration provider budget covers investigation, repair, proposal,
review, implementation, and source review turns. Native trial execution and
judging use the separate settings above. External evaluators use their own
specification limits. None of these limits is evidence that an unobserved
external effect was isolated or completed.

## Lower-level optimizer APIs

The optimizer library remains usable directly, including candidate workspace
preparation, freezing, validation, recommendation publication/loading, native
`run_trial`, judge-packet construction and aggregation, and the external paired
evaluation APIs. Export receipts are appropriate at an external consumer
boundary; they are not an internal replay mechanism for `improve_workflow`.

`improve_workflow` replaces the earlier failure-mode, optimization-candidate,
refinement, and decomposition labs. Start new runs for this workflow version;
old lab journals are not rewritten or migrated.
