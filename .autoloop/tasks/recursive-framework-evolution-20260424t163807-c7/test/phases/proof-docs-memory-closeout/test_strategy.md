# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c7
- Pair: test
- Phase ID: proof-docs-memory-closeout
- Phase Directory Key: proof-docs-memory-closeout
- Phase Title: Proof Docs And Closeout
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Expanded candidate-surface authoring guidance
  - Coverage: `tests/test_architecture_baseline_docs.py::test_authoring_doc_describes_additive_candidate_surface_helper_boundary`
  - Checks:
    - import surface now includes `validate_baseline_surface_manifest(...)`, `validate_candidate_surface_manifest(...)`, and `normalize_candidate_surface_overlay_result(...)`
    - helper-boundary prose still keeps manifest validation and overlay-result normalization mechanical and authoring-only
- Preserved runtime/workflow behavior during closeout
  - Coverage: `tests/unit/test_stdlib_and_extensions.py`
  - Checks:
    - candidate-surface helper exports and helper-only behavior still pass after the docs/memory closeout
- Preserved migrated workflow behavior
  - Coverage:
    - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
    - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - Checks:
    - refinement and decomposition publication semantics, boundary rejections, and overlay validation remain unchanged

## Edge cases and failure paths

- Docs regression path:
  - removing the new manifest-validator names or overlay-result-normalization wording from `docs/authoring.md` now fails the baseline docs suite
- Behavior safety:
  - targeted proof still covers the shared seam plus both migrated workflows so the docs closeout cannot silently drift from tested behavior
- Flake risk and stabilization:
  - low risk; coverage uses deterministic text assertions plus the existing targeted unit/runtime suites, with no timing, network, or nondeterministic ordering dependencies

## Known gaps

- No new runtime/unit fixtures were needed because this phase changed docs and recursive-memory records only; existing helper/workflow suites already cover the underlying code paths
- Repo-wide net-line accounting remains intentionally untested because the worktree is dirty and the implementation explicitly records that constraint instead of inventing an exact value
