# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c7
- Pair: test
- Phase ID: migrate-refinement-decomposition-callers
- Phase Directory Key: migrate-refinement-decomposition-callers
- Phase Title: Migrate Workflow Callers
- Scope: phase-local producer artifact

## Behaviors Covered

- Refinement workflow publish path still produces unchanged publication artifacts and receipt overlay payload after migration to shared candidate-surface validators.
- Decomposition workflow publish path still produces unchanged publication artifacts and receipt overlay payload after the same migration.
- Both workflows still reject publish-time authoritative-source drift after baseline capture.
- Both workflows still reject candidate surfaces that step outside their allowed repo-relative boundary.
- Both workflows now explicitly reject baseline-manifest boundary metadata drift through the shared seam.
- Both workflows now explicitly reject candidate-manifest boundary metadata drift through the shared seam.

## Preserved Invariants Checked

- Artifact filenames and receipt keys remain unchanged.
- Route behavior and publish-time overlay validation outcomes remain unchanged.
- Refinement keeps the historical selected-workflow boundary error wording.
- Decomposition keeps building-block index and declared doc/runtime-test policy workflow-local.

## Edge Cases

- Optional workflow doc/test boundary fields remain compatible with shared validator inputs through the runtime suites' existing fixtures.
- Candidate manifests with extra out-of-boundary files are still rejected after caller migration.
- Candidate manifests with mismatched boundary metadata are rejected even when the file tree itself still looks valid.

## Failure Paths

- Refinement:
  - baseline manifest boundary mismatch
  - candidate manifest baseline-relative-path drift
  - candidate manifest package-root boundary mismatch
  - candidate files outside selected-workflow boundary
  - authoritative source drift
- Decomposition:
  - baseline manifest boundary mismatch
  - candidate manifest parent-package boundary mismatch
  - candidate files outside allowed boundary
  - unlisted candidate-surface files
  - missing declared building-block doc/runtime-test paths
  - authoritative source drift

## Validation Executed

- `./.venv/bin/pytest -q tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `./.venv/bin/pytest -q tests/runtime/test_workflow_package_to_composable_building_blocks.py`

## Flake Risk / Stabilization

- No network or time-sensitive checks added.
- Tests stay deterministic by mutating workflow-local copied manifests inside temp workspaces and asserting exact publish-time error strings.

## Known Gaps

- No additional unit coverage added here because the shared seam itself was already covered in the earlier `extend-candidate-surface-seam` test phase.
