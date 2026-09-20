# Optimizer

Botpipe's optimizer turns durable run observations into evidence-bound change
proposals. It does not edit, execute, or promote the selected workflow. Concrete
work happens in the refinement or evaluation-suite workflows, and any measured
comparison is an explicit optional refinement step.

## Diagnose a workflow

```bash
botpipe run workflow_run_traces_to_optimization_candidates \
  --input '[{"selected_workflow":"ralph_loop","task_title":"Diagnose Ralph","objective":"reliability"},"Diagnose recent runs and recommend the next useful action"]' \
  --task-id optimizer-review-1 --workspace .
```

`selected_workflow` accepts a catalog name, `module:function`, or
`file.py:function`. By default the workflow considers the latest 25 matching
runs. `run_refs` selects exact run IDs or `task/run` references;
`run_statuses` filters automatic history selection; `route_tags` is retained as
a compatibility name for filtering observed operation outcomes. It is not a
static route-table query.

The three objectives rank observed burden:

| Objective | Eligible observations | Ordering |
| --- | --- | --- |
| `reliability` | Explicit failed/interrupted operations or typed rework/replan outcomes | Distinct affected runs, then deterministic ties |
| `token_usage` | Complete, positive provider usage | Sum of reported token counts |
| `latency` | Complete, positive physical provider-dispatch timing | Sum of provider-dispatch seconds |

These rankings do not estimate causality, probability, price, reducibility, or
future benefit. Provider-dispatch seconds are additive observed provider burden,
not end-to-end wall latency. Token counts remain literal reported counts even
when provider/model profiles differ; neither measure is normalized across
profiles. Python has dynamic topology: declared source describes what may run,
while only journaled operations prove what did run. Runs are grouped only when
recorded workflow identity and exact surface provenance permit it. Missing
historical provenance stays unknown.

Failed provider attempts remain visible in per-dispatch profile evidence. When
a later attempt completes the operation, the earlier attempt is not promoted to
a direct operation failure for reliability ranking. A missing provider, effective
model, or effort fact makes that exact dispatch noncomparable; separate unknown
dispatches never form a shared profile.

If no observation is eligible, the workflow makes zero provider calls and
publishes a typed empty `CandidateSet` whose next action is `collect_evidence`
or `no_change`. Otherwise it makes one proposal followed by one independent
review in the normal path. Schema repair, bounded rework, or an explicitly
authorized retry can consume additional dispatches.

## Limits

| Parameter | Default | Meaning |
| --- | ---: | --- |
| `history_limit` | 25 | Runs selected before evidence admission |
| `top_k_steps` | 1 | Total shortlisted observed operations in the selected evidence group |
| `max_candidates` | 3 | Total candidates accepted in one `CandidateSet` |
| `max_provider_turns` | 6 | Shared dispatch cap, including repair and retry |
| `provider_turn_timeout_seconds` | 600 | Maximum time for one dispatch |
| `max_analysis_seconds` | 1800 | Non-extending recommendation deadline |
| `max_evidence_bytes` | 50 MiB | Admitted source and run-inspection records |
| `max_output_bytes` | 10 MiB | Accepted candidate, review, and supporting records |

The workflow enforces provider limits with
`provider_budget(*, max_turns, max_seconds, turn_timeout_seconds)`. Its journaled
counter is shared by child and parallel scopes. Reservations occur before the
actual provider effect, so interrupted attempts remain charged. Resume keeps
both consumed turns and the original absolute deadline; paused time counts and
the deadline never extends.

`include_adversarial_generation`, `include_token_optimization`, and
`include_workflow_level_candidates` restrict allowed candidate kinds. They do
not add fixed specialist stages.

## Records and publication

The workflow returns `OptimizationWorkflowResult`, containing the
`EvidenceSnapshot`, `CandidateSet`, optional `CandidateReview`, accepted
`PublicationReceipt`, and final provider-budget snapshot. The run folder has
one canonical commit marker:

- `optimization_publication_receipt.json`

It selects an immutable, content-addressed directory under
`optimization_publications/publication_<sha256>/`. That generation contains:

- `workflow_optimization_evidence.json`
- `baseline_surface_manifest.json`
- `workflow_optimization_candidates.json`
- `workflow_optimization_candidate_review.json` when a proposal was reviewed
- `workflow_optimization_report.md`
- `workflow_refinement_evidence.json`
- `workflow_optimization_supporting.md` when the producer supplied it
- an immutable copy of `optimization_publication_receipt.json`

`CandidateSet` is strict and content-addressed. Each candidate names one kind
(`producer_prompt`, `verifier_rubric`, `tokens`, `workflow`, or
`evaluation_case`), target paths, cited observation IDs, a proposed change,
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

## Hand off one candidate

Choose one `candidate_id` from an accepted receipt. Prompt, rubric, token, and
workflow candidates enter refinement:

```bash
botpipe run workflow_and_eval_to_refined_workflow_package \
  --input '[{"selected_workflow":"ralph_loop","task_title":"Refine Ralph","optimization_receipt_path":"/absolute/run/optimization_publication_receipt.json","candidate_id":"candidate_..."},"Materialize and validate the selected candidate"]' \
  --task-id refinement-1 --workspace .
```

Refinement accepts exactly one complete primary input:

- `optimization_receipt_path` plus `candidate_id`; or
- `evaluation_summary_path` plus `evaluation_findings_path`.

The pairs are mutually exclusive. Refinement accepts candidate kinds
`producer_prompt`, `verifier_rubric`, `tokens`, and `workflow`.
`evaluation_case` goes instead to `workflow_to_eval_suite`, whose optional
`optimization_receipt_path` and `candidate_id` must also be supplied together.
That path validates callable inputs, stable case IDs, and artifact expectations
and creates a new evaluation-suite identity.

Candidate preparation snapshots and hashes the authoritative files, permits
changes and removals to captured files and additions only inside allowed
package roots, then builds isolated baseline and candidate execution trees.
Compilation and Python checks load project modules only from the staged tree.
The external test command is an argv sequence executed without a shell; legacy
`target_test_command` uses POSIX parsing and is mutually exclusive with
`target_test_argv`. Results and change metadata are recomputed from frozen
identities. Validation never mutates authoritative sources and never promotes a
candidate automatically.

The native helper boundary is:

```python
from botpipe_optimizer.candidates import (
    candidate_surface_manifest,
    freeze_candidate_workspace,
    prepare_candidate_workspace,
    validate_candidate,
)

workspace = prepare_candidate_workspace(repo_root, relative_paths, destination)
bundle = freeze_candidate_workspace(
    workspace,
    owned_parent,
    boundary=package_boundary,
    selected_package_root=installed_package_root,
    selected_package_import_path=import_path,
    execution_source_root=repo_root,
)
manifest = candidate_surface_manifest(workspace, bundle)
validation = validate_candidate(
    workspace,
    bundle,
    workflow_refs=["package.module:function"],
    staging_parent=owned_parent,
    target_test_argv=["pytest", "-q"],
)
```

`prepare_candidate_workspace` accepts `max_files` and `max_bytes` bounds.
`freeze_candidate_workspace` must run before editing and accepts the same tree
bounds. `validate_candidate` accepts positive compile/check/test timeouts and
bounded diagnostic streams. The older
`evaluate_candidate_workspace(workspace, argv, timeout=...)` remains a
convenience for one isolated external check with source-mutation checks.

## Optional paired evaluation

Set `evaluation_spec_path` on refinement to run the same frozen evaluation plan
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

## Migration from the graph-runtime optimizer

- Static step/route topology is replaced by callable source identity plus the
  runtime operations actually observed. `route_tags` now filters recorded
  outcome labels only.
- Filesystem checkpoints are not resumed by this major version. Start a new
  durable-function run; incompatible or changed evidence/baseline identities
  fail closed.
- `max_candidates_per_pass` maps to the total `max_candidates` cap with a
  warning; conflicting values fail. `optimization_depth=cheap|standard` maps to
  budget defaults only, and `ablation` remains planning-only.
- Old receipts remain historical evidence and are not upgraded into v2 proof.
  Revalidate a candidate to obtain current identities and results.
- `workflow_refinement_evidence.json` remains the canonical optimizer handoff.
  Other provider and activity completion is represented by the journal and
  immutable artifacts, not legacy per-stage receipt duplication.

See the [adapted optimizer v2 requirements](requirements/optimizer-v2.md) and
[acceptance inventory](optimizer-acceptance.md).
