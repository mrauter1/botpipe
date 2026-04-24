# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t163807-c6
- Pair: implement
- Phase ID: shared-candidate-surface-seam
- Phase Directory Key: shared-candidate-surface-seam
- Phase Title: Shared Candidate Surface Seam
- Scope: phase-local producer artifact

## Pre-change audit

- Cycle mode: `consolidate`
- Most relevant existing workflows/helpers:
  - `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
  - `workflows/workflow_package_to_composable_building_blocks/workflow.py`
  - `stdlib/refinement.py` and `stdlib/decomposition.py`
- Repeated patterns found:
  - repo-relative boundary derivation from selected-workflow authoring surfaces
  - baseline surface copy plus manifest-file digest capture
  - candidate manifest diff derivation with changed and added path tracking
  - authoritative-source immutability checks
  - isolated overlay validation with runnable-root fallback and pytest command normalization
- Simplification opportunity: move those mechanical publication helpers into one additive stdlib seam and keep workflow-specific evidence, receipt, and boundary policy local
- New workflow required: no
- Cycle decision for this phase: add the shared stdlib seam and unit proof only; defer workflow migration and closeout-only docs/memory work to later scoped phases

## Files changed

- `stdlib/candidate_surfaces.py`
- `stdlib/__init__.py`
- `tests/unit/test_stdlib_and_extensions.py`

## Symbols touched

- Added:
  - `normalize_candidate_surface_boundary(...)`
  - `materialize_baseline_surface(...)`
  - `derive_candidate_surface_manifest(...)`
  - `validate_authoritative_surface_sources_unchanged(...)`
  - `validate_candidate_surface_overlay(...)`
- Exported via `stdlib.__init__`
- Added focused unit tests for boundary normalization, baseline/candidate manifest derivation, authoritative-source drift rejection, and overlay fallback/command normalization
- Added shared repo-relative path hardening for baseline/drift/overlay copy inputs plus negative unit tests for parent traversal and absolute-path rejection

## Checklist mapping

- Plan Phase 1 `shared candidate-surface seam`: completed
- Plan Phase 2 `workflow migration`: deferred by phase scope
- Plan Phase 3 `proof, docs, and recursive memory sync`: deferred by phase scope

## Assumptions

- Phase-local scope is authoritative for this turn, so the new seam should be additive and safe to land before workflow migration
- Existing refinement and decomposition workflows must keep their current artifact names, receipt keys, and domain-specific validation behavior until the later migration phase

## Preserved invariants

- No CLI change
- No runtime contract change
- No `workflow.toml` semantic change
- No workflow route-name, artifact-name, or receipt-shape change
- No hidden runtime-owned publication, decomposition, or refinement policy
- Repo-relative path safety now stays centralized inside the shared seam for baseline and overlay copy inputs

## Intended behavior changes

- The repo now has one shared authoring-only helper seam for the repeated mechanical candidate-surface publication operations
- The shared seam now also rejects absolute-path and parent-traversal inputs before reading from `repo_root` or copying into overlay roots

## Known non-changes

- `workflow_and_eval_to_refined_workflow_package` still uses its local helper tail in this phase
- `workflow_package_to_composable_building_blocks` still uses its local helper tail in this phase
- `docs/authoring.md` and `.autoloop_recursive/*` were inspected but intentionally not edited in this phase-local turn

## Expected side effects

- Later migration work can replace duplicated workflow-local baseline/candidate surface helpers with the new stdlib seam without widening runtime behavior

## Deduplication / centralization decisions

- `stdlib/candidate_surfaces.py` owns only generic boundary, copy, diff, digest, drift-check, and overlay mechanics
- `stdlib/candidate_surfaces.py` also owns generic repo-relative path hardening for baseline/drift/overlay copy inputs
- Workflow-specific evidence validation, selected-workflow identity checks, allowed-path policy, building-block index rules, and publication receipts remain workflow-local

## Validation performed

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py -k 'candidate_surface or stdlib_modules_remain_pure_authoring_helpers'`
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py`
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py::test_workflow_and_eval_to_refined_workflow_package_compiles_with_explicit_control_contracts tests/runtime/test_workflow_package_to_composable_building_blocks.py::test_workflow_package_to_composable_building_blocks_compiles_with_explicit_control_contracts`
- Focused candidate-surface slice: `9 passed`
- Full stdlib/extensions unit suite: `67 passed`
- Targeted refinement/decomposition compile checks: `2 passed`

## Boilerplate / clarity accounting for this phase

- Files added: `1`
- Files deleted: `0`
- Net line count change: not practical to compute from repo diff because this checkout already carries a dirty/untracked worktree; phase-local additions are limited to one new stdlib module plus focused export/test updates
- Repeated validation idioms removed: `0` from live workflows in this phase; the shared seam now exists for later migration
- Repeated prompt sections removed or shortened: `0`
- Workflows changed to use shared helpers: `0` in this phase
- New helper functions introduced: `5`
- Old workflow-local validation blocks replaced: `0` in this phase
- Core flow readability before/after: unchanged in the workflow files this phase; the readability gain is preparatory because the shared seam is now ready for the later workflow migration
