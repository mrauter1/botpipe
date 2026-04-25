# Cycle 7 Plan

## Cycle mode and rationale

- Chosen mode: `consolidate`.
- Rationale: the highest-leverage pressure is no longer workflow portfolio breadth. The refinement and decomposition workflows still carry large repeated candidate-surface publication and validation mechanics even after cycle 6 introduced `stdlib/candidate_surfaces.py`. Extending that existing seam shortens two of the hardest workflow files to author and review without widening runtime behavior or adding portfolio sprawl.

## Pre-change audit summary

### Most relevant existing workflows/helpers

1. `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
   - Owns refinement-specific policy, but still carries extensive local baseline/candidate manifest validation and overlay-result checks.
2. `workflows/workflow_package_to_composable_building_blocks/workflow.py`
   - Owns decomposition-specific policy, but repeats the same mechanical manifest/file/digest/overlay patterns around a different domain boundary.
3. `stdlib/candidate_surfaces.py`
   - Already owns baseline copying, candidate diff derivation, authoritative-source drift checks, and overlay execution; it is the obvious convergence point for the remaining shared mechanics.

### Repeated patterns found

- Baseline manifest validation repeated: `surface_kind`, `repo_root`, boundary-path alignment, `relative_paths`/`files` consistency, `source_path` existence, and `surface_sha256` checks.
- Candidate manifest validation repeated: baseline-path preservation, candidate boundary enforcement, `relative_paths`/`files` consistency, and candidate-surface digest checks.
- Repo-relative file helpers repeated: manifest-entry maps, non-empty file reads, SHA-256 helpers, and input-path resolution.
- Overlay validation post-processing repeated: compiled workflow name checks, normalized test command checks, and non-negative `test_returncode` assertions.
- Selected-workflow identity/boundary alignment repeated in slightly different forms across the refinement and decomposition family.

### Simplification opportunity

- Extend the existing `stdlib/candidate_surfaces.py` seam so it also validates baseline/candidate manifests and normalizes overlay-validation outputs.
- Leave only workflow-specific rules local:
  - refinement-only evaluation-summary and capability/authoring-surface alignment
  - decomposition-only evidence capture, building-block index validation, and allowed-path policy

### New workflow necessity

- No new workflow is necessary.
- The pressure is duplicated authoring mechanics inside existing workflows, not a missing end-to-end package or terminal artifact contract.

### What would make this family 10x easier to author/read/reason about

- One obvious shared authoring path for candidate-surface publication:
  - capture selected-workflow context
  - derive the allowed boundary
  - call shared manifest/overlay helpers
  - keep only domain-specific publication assertions in the workflow file

### Cycle decision

- Change and consolidate existing helpers and workflows.
- Do not add, split, merge, or retire workflows in this cycle.

## Candidate options considered

1. Extract shared governance/publication validation between `workflow_portfolio_to_operating_system` and `company_operation_to_recursive_improvement_cycle`.
   - Rejected for this cycle: real duplication exists there, but the stronger immediate leverage is in the refinement/decomposition family because those workflow files are larger, harder to trace, and already sit adjacent to an existing helper seam that can absorb the remaining mechanics cleanly.
2. Extend `stdlib/candidate_surfaces.py` and migrate the refinement/decomposition family.
   - Chosen: converges onto an existing seam, removes repeated validator tails, and preserves the strict workflow/runtime/provider boundary.
3. Add another workflow or move more publication logic into runtime or `workflow.toml`.
   - Rejected: increases surface area or hides workflow semantics instead of reducing boilerplate in the current portfolio.

## Chosen improvement

- Extend `stdlib/candidate_surfaces.py` with additive shared validators and normalizers for the remaining mechanical candidate-surface publication path.
- Migrate:
  - `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
  - `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- Preserve:
  - CLI behavior
  - runtime/provider boundary
  - `ctx.invoke_workflow(...)` compatibility
  - route names and prompt paths
  - artifact filenames and receipt payload shapes
  - existing `workflow.toml` semantics

## Why this is higher leverage than a new workflow

- It reduces duplicated mechanics in two of the most complex workflow authoring surfaces instead of increasing portfolio size.
- It improves future workflow refinement/decomposition authoring without adding another workflow family to maintain, test, document, and govern.
- It follows the cycle bias directly: converge helper seams and remove repeated validation before considering new packages.

## Proposed implementation shape

### Shared helper seam

- Extend `stdlib/candidate_surfaces.py`; do not create a second helper module for the same family.
- Export any new helper surface through `stdlib/__init__.py`.
- Keep the seam authoring-only and additive.

### Planned helper responsibilities

- Validate baseline surface manifests against repo-root and workflow-boundary invariants shared by refinement and decomposition.
- Validate candidate surface manifests against:
  - preserved baseline paths
  - file-entry and digest consistency
  - caller-supplied allowed boundary rules for added files
- Normalize overlay-validation results so workflows do not repeat compiled-workflow-name and test-command sanity checks.
- Reuse existing baseline copy, candidate diff derivation, authoritative-source immutability, and isolated overlay execution helpers instead of replacing them.

### Workflow-local responsibilities that stay local

- Refinement:
  - evaluation-summary selected-workflow alignment
  - capability versus authoring-surface alignment
  - refinement receipt shaping and publication policy
- Decomposition:
  - decomposition evidence capture and request fallback
  - `candidate_building_block_index.json` validation
  - allowed building-block path policy
  - decomposition receipt shaping and publication policy

### Interface notes

- Prefer extending the current helper API over introducing a parallel seam.
- Any new helper parameters should accept caller-supplied boundary metadata rather than encoding refinement or decomposition policy in stdlib.
- Artifact names remain workflow-owned; shared helpers validate structure and boundary, not receipt naming.

## Milestones

### Phase 1: extend the shared candidate-surface seam

- Add the missing shared baseline/candidate manifest validators to `stdlib/candidate_surfaces.py`.
- Consolidate shared manifest-file parsing and overlay-result normalization there.
- Update `stdlib/__init__.py` exports and focused unit coverage in `tests/unit/test_stdlib_and_extensions.py`.

### Phase 2: migrate refinement and decomposition callers

- Refactor `workflow_and_eval_to_refined_workflow_package` to consume the expanded shared seam.
- Refactor `workflow_package_to_composable_building_blocks` to consume the same seam.
- Remove duplicated workflow-local helper tails that become mechanical shared behavior.
- Update targeted runtime tests:
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`

### Phase 3: proof, docs, and recursive memory sync

- Update `docs/authoring.md` only if the seam boundary needs new author-facing guidance.
- Update `.autoloop_recursive/framework_evolution_charter.md` with either a no-doctrine-change note or an explicit doctrine change if required by the implementation.
- Update:
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
  - `.autoloop_recursive/validation_debt_ledger.md`
- Run targeted proof and record the required cycle accounting explicitly, including zero-value categories where unchanged.

## Interfaces and invariants

### Compatibility notes

- No public CLI changes.
- No root `workflow` surface expansion.
- No runtime-owned hidden routing, promotion, decomposition, or scoring behavior.
- No new semantic `workflow.toml` fields.
- No change to prompt file paths, route grammar, or publication artifact names.

### Regression-risk notes

- Highest risk: changing candidate-surface validation semantics while moving checks into stdlib.
  - Control: keep workflow-specific policy local and assert unchanged artifact/receipt behavior in runtime tests.
- Highest risk: changing overlay validation behavior indirectly.
  - Control: preserve the current runnable-repo fallback, command normalization, compiled-workflow checks, and isolated overlay execution path.
- Highest risk: over-generalizing the helper seam.
  - Control: extend the existing helper with only mechanical manifest and overlay checks; do not absorb evidence, evaluation, or building-block policy.

## Validation plan

- Unit:
  - `tests/unit/test_stdlib_and_extensions.py`
- Runtime:
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- Docs baseline:
  - `tests/test_architecture_baseline_docs.py`

## Boilerplate and clarity targets

- Files added: target `0`; prefer extending the existing helper surface.
- Files deleted: target `0`.
- Net line count: target neutral to negative after removing repeated workflow-local helpers.
- Repeated validation idioms removed:
  - baseline manifest validation tails
  - candidate manifest validation tails
  - shared file-entry/digest helper tails
  - shared overlay-result normalization tails
- Repeated prompt sections removed or shortened:
  - expected `0` unless implementation uncovers incidental prompt cleanup; closeout must still report the final value explicitly
- Workflows changed to use shared helpers:
  - `workflow_and_eval_to_refined_workflow_package`
  - `workflow_package_to_composable_building_blocks`
- New helper functions introduced:
  - final closeout must list the additive `stdlib/candidate_surfaces.py` exports or newly shared internal helpers explicitly
- Old workflow-local validation blocks replaced:
  - manifest/file/digest/overlay validation mechanics only
- Core-flow readability target:
  - before: publish-time helper tails bury the domain logic in both workflows
  - after: workflow code shows boundary derivation and domain-specific assertions first, with the shared seam handling the mechanical validation path

### Required closeout accounting

- The implementation closeout must explicitly report:
  - files added
  - files deleted
  - net line count change, if practical
  - if net added lines exceed 500, why that added surface was not avoidable
  - repeated validation idioms removed
  - repeated prompt sections removed or shortened, including `0` when unchanged
  - workflows changed to use shared helpers
  - new helper functions introduced
  - old workflow-local validation blocks replaced
  - core flow readability before/after

## Deferred debt after this cycle

- Do not move decomposition evidence capture into `stdlib/candidate_surfaces.py` unless a third workflow needs the same request-fallback and evidence-copy contract.
- Do not move refinement evaluation-summary alignment into stdlib unless another workflow shares the same evaluation receipt boundary.
- Governance-family duplication remains deferred; revisit it only after this candidate-surface consolidation lands and the current seam shape settles.
