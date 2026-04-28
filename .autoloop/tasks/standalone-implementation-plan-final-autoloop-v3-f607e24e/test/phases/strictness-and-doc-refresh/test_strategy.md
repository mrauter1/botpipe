# Test Strategy

- Task ID: standalone-implementation-plan-final-autoloop-v3-f607e24e
- Pair: test
- Phase ID: strictness-and-doc-refresh
- Phase Directory Key: strictness-and-doc-refresh
- Phase Title: Strictness And Documentation Refresh
- Scope: phase-local producer artifact

## Behavior-to-coverage map

- AC-1 maintained-tree strictness scan:
  - `tests/strictness/test_no_compat.py::test_removed_compatibility_scan_scope_covers_maintained_tree_only`
  - `tests/strictness/test_no_compat.py::test_active_tree_does_not_reintroduce_removed_compatibility_surfaces`
- AC-1 removed public surfaces and shim restrictions:
  - `tests/strictness/test_no_compat.py::test_public_packages_do_not_export_removed_board_mutation`
  - `tests/strictness/test_no_compat.py::test_workflow_primitives_shim_exports_only_core_primitives`
  - `tests/strictness/test_no_compat.py::test_workflow_shim_exports_only_the_strict_authoring_surface`
- AC-2 active docs and working-tree note wording:
  - `tests/test_architecture_baseline_docs.py::test_authoring_doc_describes_greenfield_simple_surface`
  - `tests/test_architecture_baseline_docs.py::test_architecture_doc_describes_single_public_authoring_surface`
  - `tests/test_architecture_baseline_docs.py::test_active_working_tree_note_points_to_greenfield_authoring_surface`
- Adjacent regression guard for retry-aware event checkpoint metadata:
  - `tests/contract/test_engine_contracts.py::test_provider_invalid_question_retry_exhaustion_marks_failure_context`

## Preserved invariants checked

- `workflow.primitives` exposes runtime primitives only and not authoring helpers or step classes.
- `workflow/__init__.py` stays a non-authoring shim.
- Removed route-contract, `contracts_path`, `BoardMutation`, and generated-handler vocabulary do not reappear in maintained framework-owned roots.
- Public docs and the active working-tree note point authors to `autoloop.simple` / `autoloop`.

## Edge cases and failure paths

- The strictness scan excludes itself while still scanning `tests/`, so removed-token assertions elsewhere must use indirect string construction.
- Optional top-level files are handled deterministically: `cleanup.md` and `Workflow_Instructions.md` are covered when present, `README.md` remains optional.
- Retry-exhaustion checkpoint coverage ensures `provider_attributable` survives failure-context backfill for provider-side invalid events.

## Stability notes

- Tests are pure file-content and module-surface assertions; no timing, network, or ordering sensitivity.
- Validation uses focused pytest slices for the changed docs/strictness surface plus the targeted engine-regression test; the implementation phase already recorded a passing full-suite run.

## Known gaps

- This phase does not widen strictness scanning into archived docs or user workflow packages; that exclusion is intentional per the phase contract.
