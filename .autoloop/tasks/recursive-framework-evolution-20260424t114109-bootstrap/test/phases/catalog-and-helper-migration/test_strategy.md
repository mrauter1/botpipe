# Test Strategy

- Task ID: recursive-framework-evolution-20260424t114109-bootstrap
- Pair: test
- Phase ID: catalog-and-helper-migration
- Phase Directory Key: catalog-and-helper-migration
- Phase Title: Catalog And Helper Migration
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 shallow discovery without imports:
  `tests/runtime/test_compatibility_runtime.py::test_discover_workflow_catalog_infers_flow_packages_and_single_file_workflows_without_imports`
  `tests/runtime/test_package_cli.py::test_cli_workflows_list_includes_manifest_and_inferred_workflows_without_imports`
- AC-2 deep inspection shape/origin coverage:
  `tests/runtime/test_compatibility_runtime.py::test_inspect_workflow_reference_reports_authoring_shape_and_support_paths_for_inferred_shapes`
  `tests/runtime/test_compatibility_runtime.py::test_inspect_workflow_capabilities_uses_catalog_entry_origins_when_aliases_collide`
- AC-3 helper seams tolerate non-package origins and use `ctx.root`:
  existing package/inferred coverage in portfolio/adaptation/refinement/decomposition tests under `tests/unit/test_stdlib_and_extensions.py`
  new single-file coverage:
  `test_company_helper_accepts_single_file_workflow_references`
  `test_diagnostics_helper_accepts_single_file_workflow_references`
  `test_evaluation_helper_accepts_single_file_workflow_references`
- AC-4 metadata-only manifests and parameter precedence:
  manifest rejection and inspection coverage in `tests/runtime/test_compatibility_runtime.py`
  existing parameter coercion/loader-path coverage in adaptation and evaluation tests under `tests/unit/test_stdlib_and_extensions.py`

## Preserved invariants checked

- Single-file workflow references still resolve through the shared loader path instead of package-layout heuristics.
- Helper outputs continue to serialize canonical workflow names derived from resolved references.
- Existing package-based helper tests still pass after the added single-file coverage.

## Edge cases and failure paths

- Alias collision between inferred canonical workflow names and manifest aliases is pinned in runtime coverage.
- Company helper empty result sets remain valid when the selected workflow is single-file.
- Diagnostics helper filtered run-history snapshots still work when the selected workflow is resolved by file path.
- Evaluation helper validates artifact expectations against a single-file capability snapshot without requiring manifests or package folders.

## Known gaps

- Out-of-scope doc/template assertions remain outside this test slice.
- This turn did not add new scaffold/builder coverage because those behaviors are explicitly deferred from the phase.
