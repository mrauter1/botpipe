# Cycle 6 Plan

## Cycle mode and rationale

- Chosen mode: `consolidate`.
- Rationale: the highest-leverage pressure is no longer portfolio coverage. The refinement and decomposition workflows each carry large, near-identical publish-time helpers for repo-root resolution, boundary derivation, baseline copying, candidate manifest diffing, authoritative-source immutability checks, overlay validation, and supporting SHA/module-preservation utilities. Removing that duplication makes the two hardest-to-read authoring workflows materially shorter without widening runtime behavior.

## Pre-change audit summary

### Most relevant existing workflows/helpers

1. `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
   - Carries baseline/candidate manifest derivation, authoritative-file drift checks, and isolated overlay validation for candidate refinement publication.
2. `workflows/workflow_package_to_composable_building_blocks/workflow.py`
   - Carries the same publish-time baseline/candidate overlay machinery plus decomposition-specific boundary checks.
3. `stdlib/refinement.py` and `stdlib/decomposition.py`
   - Already split selected-workflow capture into authoring-only helper seams, but publication-side surface handling stayed duplicated in the workflow files instead of converging into a shared authoring helper.

### Repeated patterns found

- Repo-root and repo-relative path normalization helpers repeated across both workflow files.
- Baseline surface copy loops repeated with the same `source_path`, `surface_path`, `surface_sha256`, and `authoritative_source_sha256` record shape.
- Candidate surface diff/manifest loops repeated with the same `relative_path`, `surface_sha256`, `size_bytes`, `changed_from_baseline`, `changed_relative_paths`, and `added_relative_paths` logic.
- Authoritative-source immutability checks repeated against baseline manifest digests.
- Isolated overlay validation repeated: temp repo copy, `.venv` symlink preservation, workflow-module cache isolation, compile check, and test-command execution.
- Supporting `_manifest_file_map`, `_sha256_file`, `_resolve_overlay_source_root`, `_is_runnable_repo_root`, and `_preserved_workflow_modules` helpers repeated nearly verbatim.

### Simplification opportunity

- Extract one additive, authoring-only shared helper seam for candidate-surface publication mechanics, then leave only workflow-specific rules local:
  - refinement-specific evaluation-summary and authoring-surface/capability alignment
  - decomposition-specific evidence capture, declared building-block index validation, and allowed-path policy

### New workflow necessity

- No new workflow is necessary.
- The problem is duplicated authoring mechanics inside existing workflows, not a missing terminal artifact package.

### What would make this family 10x easier to author/read/reason about

- A single helper module should own the mechanical surface-copy/digest/overlay work so each workflow file reads as:
  - capture selected-workflow context
  - define workflow-specific publication boundary
  - call shared surface helpers
  - enforce only the remaining domain-specific assertions

### Cycle decision

- Change and consolidate existing workflows/helpers.
- Do not add, split, or retire workflows in this cycle.

## Candidate options considered

1. Keep both workflows local and only rename/reorder helper blocks.
   - Rejected: improves readability slightly but preserves duplicated publication logic and future drift risk.
2. Extract a shared authoring-only candidate-surface publication seam in `stdlib/`, then migrate refinement and decomposition to it.
   - Chosen: highest leverage with low compatibility risk because the duplication is mechanical and the workflows can retain their current artifact contracts.
3. Move publish-time manifest/overlay behavior into runtime code or add richer `workflow.toml` metadata.
   - Rejected: violates the workflow/runtime boundary, hides workflow semantics, and widens framework contracts unnecessarily.

## Chosen improvement

- Add one shared authoring-only helper seam for candidate-surface publication mechanics.
- Migrate:
  - `workflow_and_eval_to_refined_workflow_package`
  - `workflow_package_to_composable_building_blocks`
- Preserve:
  - CLI behavior
  - runtime/provider boundary
  - `ctx.invoke_workflow(...)` compatibility
  - current route names
  - current artifact filenames and folder names
  - current receipt payload shape
  - current prompt paths
  - current `workflow.toml` semantics

## Proposed implementation shape

### Shared helper seam

- New module: `stdlib/candidate_surfaces.py`
- Boundary: authoring-only helper surface for baseline/candidate workflow overlays and publish-time validation.
- Non-goals:
  - no runtime-owned promotion, decomposition, or refinement behavior
  - no new workflow discovery or routing policy
  - no generic handling of decomposition evidence manifests or building-block indexes
  - no receipt-shape ownership

### Helper responsibilities

- Normalize repo-relative authoring boundaries from selected-workflow surfaces.
- Materialize baseline surface copies and deterministic file-entry records.
- Derive candidate-surface file entries and changed/added path sets from a copied baseline manifest.
- Provide shared manifest-entry parsing and authoritative-source immutability checks.
- Run isolated overlay validation against a runnable repo root while preserving the current compile-and-test behavior.

### Workflow-local responsibilities that stay local

- Refinement:
  - evaluation summary selected-workflow alignment
  - capability/authoring-surface cross-checks
  - refinement receipt shaping
- Decomposition:
  - evidence capture and fallback-to-request behavior
  - `candidate_building_block_index.json` validation
  - allowed package/doc/test boundary enforcement
  - decomposition receipt shaping

## Milestones

### Phase 1: shared candidate-surface seam

- Add `stdlib/candidate_surfaces.py` and export the helper surface from `stdlib/__init__.py`.
- Move only mechanical baseline/candidate overlay helpers into the shared module.
- Add focused unit coverage in `tests/unit/test_stdlib_and_extensions.py` for:
  - boundary normalization
  - baseline copy metadata
  - candidate diff metadata
  - authoritative-source drift rejection
  - overlay validation repo-root fallback and command normalization

### Phase 2: workflow migration

- Refactor `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py` to consume the shared helper seam while keeping current artifacts and receipt keys intact.
- Refactor `workflows/workflow_package_to_composable_building_blocks/workflow.py` to consume the same helper seam while keeping decomposition-only validation local.
- Remove duplicated local helper tails that become shared.
- Update targeted runtime suites:
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`

### Phase 3: proof, docs, and recursive memory sync

- Update `docs/authoring.md` only if the new seam needs explicit authoring guidance.
- Update `.autoloop_recursive/framework_evolution_charter.md` with either a no-doctrine-change note or an explicit doctrine change if the implementation proves one is required.
- Update:
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
  - `.autoloop_recursive/validation_debt_ledger.md`
- Record the full required cycle audit and boilerplate/clarity budget closeout, including zero-value entries when a category is unchanged.
- Run targeted proof and capture actual files added/deleted and net line delta.

## Interfaces and invariants

### Compatibility notes

- No public CLI changes.
- No change to root `workflow` imports.
- No change to runtime-injected control contract.
- No new semantic `workflow.toml` fields.
- No hidden downstream execution.
- No selected-workflow mutation before explicit later promotion.

### Regression-risk notes

- Highest risk: changing overlay validation behavior while refactoring shared helpers.
  - Control: preserve current test-command normalization, repo-copy isolation, `.venv` symlink behavior, and runnable-repo fallback semantics.
- Highest compatibility risk: accidentally changing artifact filenames or receipt payload keys.
  - Control: keep workflow-local manifest/receipt assembly and assert unchanged schemas in runtime tests.
- Highest maintainability risk: over-generalizing the seam and obscuring domain-specific rules.
  - Control: share only mechanical surface logic; leave evaluation/evidence/building-block rules in workflow code.

## Validation plan

- Unit:
  - `tests/unit/test_stdlib_and_extensions.py`
- Runtime:
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- Docs baseline:
  - `tests/test_architecture_baseline_docs.py`

## Boilerplate and clarity targets

- Files added: expected `1` shared stdlib helper module; keep additions minimal.
- Files deleted: expected `0`.
- Net line count: target neutral to negative after workflow-local helper removal.
- Repeated validation idioms removed:
  - manifest entry parsing
  - SHA/digest helpers
  - repo-root overlay helpers
  - authoritative-source drift checks
  - candidate diff derivation
- Repeated prompt sections removed or shortened:
  - expected `0` for workflow prompts unless implementation uncovers incidental prompt cleanup; record the final value explicitly either way
- Workflows changed to use shared helpers:
  - `workflow_and_eval_to_refined_workflow_package`
  - `workflow_package_to_composable_building_blocks`
- New helper functions introduced:
  - record the final exported and workflow-local helper list explicitly during closeout, anchored to `stdlib/candidate_surfaces.py` and any remaining workflow-local boundary helpers
- Old workflow-local validation blocks replaced:
  - repeated surface-copy/manifest/overlay mechanics only
- Core-flow readability target:
  - before: long publish-time helper tails obscure each workflow’s domain logic
  - after: publish handlers read as domain-specific checks plus a small shared surface-helper call path

### Required closeout accounting

- The implementation closeout must explicitly report:
  - files added
  - files deleted
  - net line count change, if practical
  - repeated validation idioms removed
  - repeated prompt sections removed or shortened, including `0` when unchanged
  - workflows changed to use shared helpers
  - new helper functions introduced
  - old workflow-local validation blocks replaced
  - core flow readability before/after

## Deferred debt after this cycle

- Do not merge decomposition-specific building-block index validation into the shared seam unless a third workflow proves the same boundary rules.
- Do not merge refinement-specific evaluation-summary checks into the shared seam unless another workflow reuses the exact evidence contract.
- Revisit whether other candidate-publication workflows emerge after this consolidation; until then keep the seam narrow and additive.
