# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c6
- Pair: test
- Phase ID: shared-candidate-surface-seam
- Phase Directory Key: shared-candidate-surface-seam
- Phase Title: Shared Candidate Surface Seam
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Shared seam export surface
  - Covered by `test_candidate_surface_helpers_normalize_repo_boundary_and_stay_reexported_from_stdlib`
  - Checks the new helper exports stay reachable from `stdlib.__init__`
- Boundary normalization
  - Covered by `test_candidate_surface_helpers_normalize_repo_boundary_and_stay_reexported_from_stdlib`
  - Checks repo-relative package/doc/runtime-test derivation and editable-path deduplication
- Baseline copy and candidate diff derivation
  - Covered by `test_candidate_surface_helpers_materialize_baseline_and_derive_candidate_diff`
  - Checks copied baseline metadata, changed-path detection, added-path detection, and unchanged-file flags
- Authoritative-source immutability
  - Covered by `test_candidate_surface_helpers_reject_authoritative_source_drift`
  - Checks digest drift is rejected after baseline capture
- Repo-relative path hardening
  - Covered by:
    - `test_candidate_surface_helpers_reject_non_repo_relative_authoritative_drift_paths`
    - `test_candidate_surface_helpers_reject_non_repo_relative_baseline_paths`
    - `test_candidate_surface_helpers_reject_non_repo_relative_overlay_paths`
  - Checks both parent-traversal and absolute-path rejection across all guarded copy/read entry points
- Overlay validation behavior
  - Covered by `test_candidate_surface_helpers_validate_overlay_normalizes_pytest_and_falls_back_to_importable_package_root`
  - Checks runnable-root fallback, pytest command normalization, overlay file staging, and ordered workflow compilation

## Preserved invariants checked

- No CLI/runtime contract assertions changed
- Helper remains authoring-only and additive
- Overlay validation still preserves ordered workflow compilation and uses the original test-command string in its receipt payload

## Edge cases and failure paths

- Duplicate editable paths
- Candidate surface with both changed and added files
- Digest drift between authoritative source and baseline manifest
- Parent-traversal path attempts
- Absolute-path attempts
- Non-runnable repo root that must fall back to an importable package root

## Known gaps

- This phase does not migrate the refinement or decomposition workflows onto the shared seam, so workflow-level runtime receipts remain covered only by the existing compile smoke tests from implement phase validation
