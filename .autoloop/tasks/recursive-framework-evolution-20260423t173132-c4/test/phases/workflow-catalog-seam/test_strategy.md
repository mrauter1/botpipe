# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c4
- Pair: test
- Phase ID: workflow-catalog-seam
- Phase Directory Key: workflow-catalog-seam
- Phase Title: Workflow Catalog Seam
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Shared pure catalog discovery happy path:
  `tests/runtime/test_compatibility_runtime.py::test_discover_workflow_catalog_collects_linked_paths_without_importing_workflow_modules`
  covers metadata, linked code/doc paths, optional `params.py`, and the no-import discovery invariant.
- Runtime export happy path:
  `tests/runtime/test_compatibility_runtime.py::test_runtime_package_reexports_catalog_discovery_happy_path`
  covers the additive `autoloop_v3.runtime.discover_workflow_catalog(...)` surface and keeps the runtime re-export visible.
- Runtime wrapper failure paths:
  `tests/runtime/test_compatibility_runtime.py::test_runtime_package_reexported_catalog_discovery_preserves_runtime_error_types`
  covers missing `workflows/__init__.py` and unsupported manifest fields so runtime callers continue to see `WorkflowDiscoveryError` / `WorkflowManifestError` instead of leaked core-only exception types.
- Workflow-local portfolio snapshot helper:
  `tests/unit/test_stdlib_and_extensions.py::test_portfolio_helper_writes_workflow_local_catalog_snapshot`
  covers the published snapshot artifact shape, linked file paths, deterministic ordering, and workflow-local path validation failures.
- Authoring-only helper purity and exports:
  `tests/unit/test_stdlib_and_extensions.py::test_stdlib_modules_remain_pure_authoring_helpers`
  and the `autoloop_v3.stdlib` import surface cover the helper remaining free of runtime-owned routing behavior.
- Authoring guidance boundary:
  `tests/test_architecture_baseline_docs.py::test_authoring_doc_describes_additive_portfolio_snapshot_helper_boundary`
  covers the documented metadata-only manifest doctrine and the explicit non-routing boundary.

## Preserved invariants checked

- `workflow.toml` remains metadata-only.
- Discovery does not import workflow modules just to read catalog metadata.
- Runtime-owned loader callers still receive runtime error classes.
- The portfolio helper writes only workflow-local JSON metadata and does not encode ranking, selection, or execution policy.

## Edge cases and failure paths

- Missing `workflows/__init__.py` at the repo root.
- Unsupported manifest fields in `workflow.toml`.
- Helper output path escape via `..`.
- Helper output path with a non-`.json` suffix.
- Optional `params.py` and workflow docs absent from a discovered package.

## Flake risk and stabilization

- Coverage is filesystem-local and deterministic under `tmp_path`.
- No network, timing, randomized ordering, or external service dependencies are involved.
- Discovery tests continue to guard against accidental workflow-module imports by asserting the target `workflows.*.workflow` module is absent from `sys.modules`.

## Known gaps

- No separate runtime test was added for portfolio snapshot generation inside a full workflow package because this phase adds only the authoring helper seam, not a portfolio-routing workflow consumer.
