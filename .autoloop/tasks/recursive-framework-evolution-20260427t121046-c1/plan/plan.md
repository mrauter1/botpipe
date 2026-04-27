# Recursive Framework Evolution Cycle 1 Plan

## Cycle mode

`consolidate`

Rationale: the highest-leverage pressure is not missing workflow coverage. It is the oversized `workflow_run_traces_to_optimization_candidates` surface, which is now the largest workflow in the repo, carries a long workflow-local validation/publication tail, and is not yet reflected in the recursive memory files.

## Pre-change audit

Most relevant existing workflows/helpers:
- `workflows/workflow_run_traces_to_optimization_candidates/workflow.py`
- `stdlib/optimization.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`

Repeated patterns and pressure:
- The optimizer repeats selected-workflow snapshot capture and alignment checks in both `on_capture_frame_context(...)` and `on_publish_optimization_packet(...)`.
- Optional candidate passes repeat the same skip routing, empty-artifact publication, and accepted-artifact finalization pattern for token, adversarial, and workflow-level outputs.
- Candidate-publication validation is encoded as workflow-local filename/schema/list-field conditionals instead of one authoritative optimization-pass surface.
- Recursive memory has drifted: the optimization workflow exists in code/docs/tests, but the standing memory set, including the charter, roadmap, and ledgers, does not yet treat it as part of the active portfolio.

Simplification opportunity:
- Move only clearly reusable deterministic optimization context/publication mechanics into `stdlib/optimization.py`, keep workflow-specific optimization policy package-local, and trim the workflow file down to state, artifacts, steps, transitions, and thin handlers.

New workflow necessary:
- No. The current gap is readability and consolidation inside an existing workflow family.

10x authoring improvement for the touched family:
- One optimization-pass registry that defines artifact names, schema expectations, empty-payload behavior, count aggregation, and publication evidence rules once, so the workflow reads like a flow again instead of a validator catalogue.

Cycle action:
- Consolidate and refactor existing optimization helpers and workflow code.
- Update docs and recursive memory to record the optimizer and its new helper boundary.
- Do not add, merge, or retire workflows in this cycle.

## Candidate options considered

1. Add a follow-on optimization or ablation workflow.
Why not chosen: fails the default consolidation bias, increases portfolio size, and does not address the current readability/validation concentration in the existing optimizer.

2. Migrate `release_candidate_to_go_no_go` and `incident_to_hardening_program` onto more building blocks.
Why not chosen: still valuable, but it touches mature domain workflows with broader regression surface and yields less immediate authoring leverage than shortening the current optimizer monolith first.

3. Consolidate the optimizer’s deterministic helper and publication seams, then sync docs/memory.
Why chosen: highest leverage, smallest public-contract risk, directly improves workflow readability, and fixes live architecture drift in recursive memory.

## Chosen improvement

Refactor `workflow_run_traces_to_optimization_candidates` so clearly reusable deterministic optimization mechanics live behind one authoritative helper seam, while workflow-specific optimization policy stays package-local and the workflow file keeps only the global SOP and route topology.

Planned implementation shape:
- Extend `stdlib/optimization.py` only for deterministic mechanics that already behave like shared optimizer infrastructure, such as snapshot/context capture, optional-pass finalization primitives, and publication-surface validation.
- Refactor `workflows/workflow_run_traces_to_optimization_candidates/workflow.py` to consume those helpers instead of carrying repeated filename/schema/list-field conditionals and per-pass empty-artifact logic inline.
- If an extracted helper remains optimizer-only or policy-laden after refactoring, keep it package-local rather than forcing it into stdlib.
- Keep `workflows/workflow_run_traces_to_optimization_candidates/contracts.py` as the authoritative artifact-model and route-contract surface unless a small supporting spec extraction is clearly needed.
- Update the full standing memory set so the optimizer and this consolidation seam are recorded in `.autoloop_recursive/framework_evolution_charter.md`, the roadmap, and the active ledgers.

Likely helper/interface changes:
- `stdlib/optimization.py`
  - add a narrow optimization pass registry/spec surface only if it clearly removes duplicated deterministic mechanics across capture/publication paths
  - add helper(s) for selected-workflow optimization context capture and validation
  - add helper(s) for optional-pass artifact finalization and empty-artifact publication
  - add helper(s) for candidate-publication surface aggregation and scorecard validation
  - keep non-goals explicit: no reruns, no ablation execution, no source mutation, no runtime-owned downstream execution
- `workflows/workflow_run_traces_to_optimization_candidates/workflow.py`
  - replace repeated deterministic helper tails with calls into the stdlib optimization seam
  - keep candidate selection policy, route semantics, prompt-facing optimization judgments, and other optimizer-only behavior package-local if they do not clearly generalize
  - preserve current step names, route tags, artifact filenames, and published schemas
- `.autoloop_recursive/*`
  - update `.autoloop_recursive/framework_evolution_charter.md`
  - record the optimizer as a real current portfolio surface in the roadmap and ledgers
  - record the consolidation seam and any remaining deferred debt

## Compatibility and invariants

Must remain unchanged:
- CLI invocation shape and workflow discovery
- strict workflow/runtime/provider boundary
- `ctx.invoke_workflow(...)` behavior
- `workflow.toml` semantics
- optimizer artifact filenames and schemas
- optimizer route tags and ordered-prefix `pairs` behavior
- candidate-only publication boundary
- no selected-workflow source mutation
- no hidden downstream execution
- no automatic reruns, ablations, or refinement execution
- `workflow_refinement_evidence.json` handoff semantics consumed by `workflow_and_eval_to_refined_workflow_package`

## Regression-risk notes

Primary regression surfaces:
- `on_capture_frame_context(...)` selected-workflow snapshot alignment and trace-corpus writing
- optional-pass skip behavior for token/adversarial/workflow-level outputs
- candidate artifact validation for accepted vs not-applicable routes
- scorecard `candidate_counts` and `requires_ablation_before_promotion` consistency checks
- selected-workflow source-manifest immutability validation at publication
- refinement workflow acceptance of optimization evidence output

Required validation approach:
- unit proof for any new optimization helper registry/finalizers/publication validators
- runtime proof for optimizer bootstrap, frame capture, optional skips, candidate generation, no-op packaging, publication, and failure cases
- refinement integration proof for optimization evidence handoff
- docs baseline proof for authoring and recursive-memory alignment

## Milestones

1. Helper consolidation
- Define the optimization helper boundary in `stdlib/optimization.py`.
- Move deterministic context/publication mechanics behind that seam.
- Reduce workflow-local helper count and inline schema/filename branching in the optimizer.

2. Workflow refactor
- Update optimizer handlers to call the new helpers.
- Keep the top-level workflow story obvious: capture context, rank, mine, optional passes, package, publish.

3. Proof and memory sync
- Update docs/recursive memory, including the charter, for the optimizer and the new seam.
- Run targeted tests and record closeout metrics in the touched memory files.

## Tests and docs to update

Targeted tests:
- `tests/unit/test_optimization_helpers.py`
- `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
- `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `tests/test_architecture_baseline_docs.py`

Docs/memory:
- `docs/authoring.md` only if the new helper seam needs an explicit optimizer-specific boundary note
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`

## Boilerplate and clarity targets

Implementation closeout must report:
- files added / deleted
- net line count change if practical
- repeated validation idioms removed
- repeated prompt sections removed or shortened
- workflows changed to use shared helpers
- new helper functions introduced
- old workflow-local validation blocks replaced
- readability before/after for the optimizer core flow

Expected direction:
- no new workflow files
- no workflow additions
- net workflow-local line reduction or neutral line movement with clearer helper ownership

## Risk register

- Risk: helper extraction changes skip-route behavior for disabled optional passes.
Mitigation: preserve route tags exactly and keep regression tests for both missing-artifact and existing-artifact skip cases.

- Risk: publication helpers accidentally loosen schema or count validation.
Mitigation: keep scorecard/count/source-manifest assertions exact and back them with failure-path tests already present in the optimizer suite.

- Risk: optimization helper growth widens into runtime policy.
Mitigation: keep helpers deterministic and authoring-owned in `stdlib/optimization.py`; do not move ranking policy, execution policy, downstream orchestration, or optimizer-only route/prompt judgments out of package-local code unless reuse is explicit.

- Risk: recursive memory keeps drifting from the live portfolio.
Mitigation: update roadmap/gap/candidate/validation ledgers in the same slice as code changes, not as a later cleanup.

## Rollback

- Revert the optimizer/helper refactor patch as one slice if proof fails.
- Preserve existing artifact contracts so rollback is code-only, with no migration needed for persisted task/run data.
- Do not land partial helper extraction without the matching workflow refactor and regression proof.
- If a helper extraction proves too optimizer-specific during implementation, roll it back to package-local code rather than keeping a weak stdlib abstraction.

## Deferred debt after this cycle

- Evaluate later whether `release_candidate_to_go_no_go` and `incident_to_hardening_program` should consume more reusable building blocks.
- Defer any new optimization-ablation execution workflow until the existing optimizer surface is shorter and more legible.
- Defer runtime-owned automation, scoring, or downstream execution; this cycle is authoring-surface consolidation only.
