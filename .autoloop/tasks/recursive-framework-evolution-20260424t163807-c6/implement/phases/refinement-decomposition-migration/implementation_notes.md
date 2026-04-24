# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t163807-c6
- Pair: implement
- Phase ID: refinement-decomposition-migration
- Phase Directory Key: refinement-decomposition-migration
- Phase Title: Workflow Migration
- Scope: phase-local producer artifact

## Pre-change audit

- Cycle mode: `consolidate`
- Most relevant existing workflows/helpers:
  - `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
  - `workflows/workflow_package_to_composable_building_blocks/workflow.py`
  - `stdlib/candidate_surfaces.py`
- Repeated patterns found:
  - selected-workflow/decomposition boundary normalization from authoring surfaces
  - baseline surface copy plus manifest-file digest recording
  - candidate manifest derivation from copied baseline metadata
  - authoritative-source drift rejection
  - isolated overlay compile-and-test validation
- Simplification opportunity: remove the duplicated mechanical helper tails from both workflows and keep only the domain-specific validation and receipt logic local
- New workflow required: no
- Cycle decision for this phase: migrate the two existing workflows to the shared candidate-surface seam, then update scoped proof and recursive-memory closeout notes

## Files changed

- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `.autoloop/tasks/recursive-framework-evolution-20260424t163807-c6/decisions.txt`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`

## Symbols touched

- Refinement workflow:
  - `_write_baseline_workflow_manifest(...)`
  - `_write_candidate_workflow_manifest(...)`
  - `_authoring_surface_boundary(...)`
  - `_validate_authoritative_files_unchanged(...)`
  - `_validate_candidate_overlay(...)`
- Decomposition workflow:
  - `_decomposition_surface_boundary(...)`
  - `_write_baseline_parent_manifest(...)`
  - `_write_candidate_decomposition_manifest(...)`
  - `_validate_authoritative_files_unchanged(...)`
  - `_validate_candidate_overlay(...)`
- Runtime proof:
  - `test_workflow_and_eval_to_refined_workflow_package_publish_rejects_authoritative_source_drift(...)`
  - `test_workflow_package_to_composable_building_blocks_publish_rejects_authoritative_source_drift(...)`

## Checklist mapping

- Plan Phase 1 `shared candidate-surface seam`: already landed in the earlier scoped phase and reused here
- Plan Phase 2 `workflow migration`: completed in this phase
- Plan Phase 3 `proof, docs, and recursive memory sync`: completed for the scoped runtime suites, architecture-doc baseline, decisions ledger, and recursive-memory ledgers touched here

## Assumptions

- The shared seam should stay additive and mechanical; receipt schema ownership and domain publication policy still belong to the workflow files
- Existing tests that inspect receipt payloads and manifest shapes are the compatibility boundary for this migration

## Preserved invariants

- No CLI change
- No runtime/provider boundary change
- No `workflow.toml` semantic change
- No prompt-path or route-name change
- No artifact-name or receipt-key change
- No change to `ctx.invoke_workflow(...)` compatibility

## Intended behavior changes

- Refinement and decomposition now share one authoring-only implementation for:
  - repo-relative selected-workflow boundary normalization
  - baseline surface materialization
  - candidate-manifest derivation
  - authoritative-source drift rejection
  - isolated overlay compile-and-test validation

## Known non-changes

- Refinement-specific evaluation-summary alignment and capability/authoring-surface checks remain local
- Decomposition-specific evidence capture, building-block index validation, allowed-path policy, and hidden-execution rejection remain local
- `docs/authoring.md`, prompt files, and workflow docs were inspected but intentionally left unchanged because the shared seam did not require a doctrine change

## Expected side effects

- Later candidate-publication workflows can reuse the same mechanical seam without copying baseline/candidate/overlay helper tails again
- Runtime rejection messages for authoritative-source drift now come from one shared validation implementation while preserving the workflow-specific error prefix

## Deduplication / centralization decisions

- `stdlib/candidate_surfaces.py` now owns the duplicated mechanical publication operations in both workflow families
- Workflow-local code still owns the semantic publication checks that differ between refinement and decomposition

## Validation performed

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`
- Results:
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`: `23 passed`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`: `24 passed`
  - `tests/test_architecture_baseline_docs.py`: `27 passed`

## Boilerplate / clarity accounting

- Files added: `0`
- Files deleted: `0`
- Net line count change: tracked scoped diff is `-214` lines (`289` insertions, `503` deletions) across the migrated workflow/test files
- Repeated validation idioms removed:
  - baseline surface copy and manifest entry recording
  - candidate manifest diff derivation
  - authoritative-source drift rejection
  - isolated overlay compile/test validation
- Repeated prompt sections removed or shortened: `0`
- Workflows changed to use shared helpers:
  - `workflow_and_eval_to_refined_workflow_package`
  - `workflow_package_to_composable_building_blocks`
- New helper functions introduced: `0` in this phase; it consumes the seam added earlier
- Old workflow-local validation blocks replaced:
  - duplicated baseline/candidate/overlay mechanics only
- Core flow readability before/after:
  - before: each workflow carried a long publish-time helper tail for baseline/candidate/overlay mechanics
  - after: each workflow keeps only domain-specific publication checks while delegating the mechanical tail to `stdlib/candidate_surfaces.py`
