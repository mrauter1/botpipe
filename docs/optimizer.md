# Workflow improvement

The `improve_workflow` lab turns observed workflow problems into an isolated,
validated candidate. It combines diagnosis, one reviewed proposal,
implementation, executable checks, independent source review, and optional
baseline/candidate evaluation. The authoritative source remains unchanged.

```bash
botpipe run improve_workflow --workspace . \
  --input '[{"selected_workflow":"devloop","objective":"reliability"},"Correct recurring failures without changing valid behavior"]'
```

See the [workflow guide](../labs/workflows/improve_workflow/README.md) for Python
usage, parameters, and outcomes. The workflow uses the existing durable runtime;
there is no additional phase engine or scheduler.

## Evidence and decisions

`selected_workflow` accepts a catalog name, `module:function`, or
`file.py:function`. By default the latest 25 matching runs that are not executing
are selected. Created and running runs do not consume the history limit.
`run_refs` selects exact run IDs or `task/run` references.

| Objective | Eligible observations | Ordering |
| --- | --- | --- |
| `reliability` | Failed/interrupted operations or typed rework/replan outcomes | Distinct affected runs, then deterministic ties |
| `token_usage` | Complete, positive provider usage | Sum of reported token counts |
| `latency` | Complete, positive provider-dispatch timing | Sum of provider-dispatch seconds |

These rankings describe recorded burden. They do not estimate causality,
price, reducibility, or future benefit. Provider seconds are additive dispatch
burden, not end-to-end elapsed time. Tokens are literal reported counts, not
normalized across models. Unknown source provenance stays unknown; it cannot
make unrelated runs comparable.

One observed operation is shortlisted. If there is no eligible evidence, the
workflow makes zero provider calls and returns `collect_evidence` or `no_change`.
Otherwise it proposes at most one change. The model supplies the useful proposal
fields; Python binds it to the exact evidence and baseline and derives its IDs.
An independent reviewer can reject the proposal before any candidate edit.

Implementation is limited to the captured workflow surface. Each revision starts
from a verified baseline in a separate workspace. Executable checks run on staged
source, followed by independent source review. Failed checks provide feedback
for a bounded revision. All model calls and repairs share one provider budget.
The inherited provider output-repair configuration is respected.

Passing checks and review without a comparative evaluation returns
`candidate_ready`. A measured candidate reports `improved`, `regressed`,
`no_material_change`, or `inconclusive`. None automatically promotes a candidate.

## Limits

| Parameter | Default |
| --- | ---: |
| `history_limit` | 25 runs |
| `max_revisions` | 2 additional attempts per proposal/implementation loop |
| `max_provider_turns` | 12 total dispatches, including repairs |
| `provider_timeout` | 600 seconds per turn |
| `max_provider_seconds` | 1800 seconds, a durable deadline on provider work |
| `validation_timeout` | 600 seconds per external validation command |
| `max_evidence_bytes` | 50 MiB |
| `max_snapshot_bytes` | 50 MiB |
| `max_output_bytes` | 10 MiB of recommendation records |

Provider limits survive resume and are shared by the complete job. External
checks and evaluations use their own bounded process settings. No limit is
reset by a semantic revision. Evaluation cases, evaluator bytes, and comparison
criteria are frozen before the first candidate edit.

## Records and publication

The workflow returns `ImproveWorkflowResult`: its outcome and summary, a
recommendation with evidence and the reviewed proposal, an optional candidate
with executable validation and comparison results, and the final provider-budget
snapshot. Accepted recommendations also have a `PublicationReceipt`. The run
folder has one canonical recommendation commit marker:

- `optimization_publication_receipt.json`

It selects an immutable, content-addressed directory under
`optimization_publications/publication_<sha256>/`. That generation contains:

- `workflow_optimization_evidence.json`
- `baseline_surface_manifest.json`
- `workflow_optimization_candidates.json`
- `workflow_optimization_candidate_review.json` when a proposal was reviewed
- `workflow_optimization_report.md`
- `workflow_refinement_evidence.json`
- an immutable copy of `optimization_publication_receipt.json`

`CandidateSet` is strict and content-addressed. This workflow produces one
`workflow` candidate with target paths, cited observation IDs, a proposed change,
expected effect, risks, and a falsifiable validation plan. Deterministic code
owns evidence grouping, metrics, identities, byte counts, and publication. The
producer cannot author those facts, and the independent reviewer cannot alter
them.

Publication serializes and validates the complete generation, including its
aggregate recommendation byte budget, before writing it. It durably installs
the generation and then atomically replaces the root receipt as the commit
point. A failed or interrupted attempt can leave an unreferenced generation,
but it cannot change the previously accepted receipt or any file that receipt
names. Retrying identical input reuses the same generation. Concurrent
publishers may race to select the latest root receipt, while each accepted
generation and its own receipt remain complete and loadable.

Ordinary workflow artifacts otherwise use the durable journal and immutable
`ArtifactHandle`s; Botpipe does not create duplicate generic receipt files for
every operation. Every recommendation receipt reports
`improvement = not_evaluated`.
Downstream code uses `load_optimization_candidate(...)`, which verifies the
same-directory receipt and referenced byte counts, hashes, evidence, baseline,
candidate set, review, and handoff identities before returning a selection.

## Optional paired evaluation

Set `evaluation_spec_path` on `improve_workflow` to run the same frozen evaluation plan
against isolated baseline and candidate trees. Omit it to skip comparison. The
harness freezes the specification, evaluator, cases, ordered case IDs,
repetitions, settings, metrics, thresholds, and limits before launching exactly
one evaluator subprocess per arm.

The evaluator receives absolute `BOTPIPE_EVAL_REQUEST` and
`BOTPIPE_EVAL_RESULT` paths. It must atomically write one strict
`botpipe.optimizer.eval_result/v1` record with exactly one result for every
planned `(case_id, repetition)` pair. IDs must match; metrics must be finite;
evidence paths must be regular files in the allowed output directory. Missing,
stale, duplicate, oversized, timed-out, cancelled, or identity-mismatched output
is incomplete and cannot produce an improvement claim.

The harness reports `improved`, `regressed`, `no_material_change`, or
`inconclusive` from the frozen primary and guardrail thresholds. Development
cases remain labeled as such. Botpipe-backed evaluators require a symmetric
provider budget per arm; external evaluators receive process and output limits
but make no claim about hidden internal model calls. There is no third arm,
search loop, or automatic promotion.

Library consumers can call `load_evaluation_spec(path)`,
`run_paired_evaluation(...)`, and `validate_paired_evaluation_record(...)` from
`botpipe_optimizer.paired_evaluation`.
Validation of a saved complete record rechecks the frozen specification,
surface/execution-tree IDs, output parent, and optional invocation identity
without rerunning either evaluator.


## Removed lab interfaces

`improve_workflow` replaces the failure-mode, optimization-candidate,
refinement, and decomposition labs. Deprecated depth, command-string, and
per-pass aliases are removed. Existing lab journals require their original
workflow source; start new runs for this replacement. Recommendation and
paired-evaluation record formats retain their existing validation guarantees.

The lower-level `botpipe_optimizer` library remains usable directly, including
`load_optimization_candidate`, `prepare_candidate_workspace`,
`freeze_candidate_workspace`, `validate_candidate`, and `run_paired_evaluation`.
The evaluation-suite lab still accepts an externally supplied evaluation-case
recommendation, but the improvement workflow proposes implementation changes.
