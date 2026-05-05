# Implementation Notes

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: implement
- Phase ID: restore-workflow-resolution-contract
- Phase Directory Key: restore-workflow-resolution-contract
- Phase Title: Restore Workflow Resolution Contract
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/workflow_catalog.py`
- `autoloop/runtime/loader.py`
- `autoloop/core/workflow_capabilities.py`
- `tests/runtime/test_workflow_catalog_roots.py`
- `tests/runtime/test_workflow_reference_resolution.py`

## Symbols touched
- `autoloop.core.workflow_catalog._effective_catalog`
- `autoloop.core.workflow_catalog._resolution_precedence`
- `autoloop.runtime.loader._resolve_catalog_entry_reference`
- `autoloop.runtime.loader._resolve_catalog_repo_module_reference`
- `autoloop.runtime.loader._should_load_catalog_entry_via_package_contract`
- `autoloop.runtime.loader._should_load_catalog_entry_via_repo_module`
- `autoloop.runtime.loader._resolve_imported_class_reference`
- `autoloop.runtime.loader._mark_named_catalog_reference`
- `autoloop.runtime.loader._named_catalog_reference_key`
- `autoloop.runtime.loader._is_repo_local_workflow_module`
- `autoloop.runtime.loader._resolve_python_path`
- `autoloop.runtime.loader._import_repo_module`
- `autoloop.runtime.loader._evict_stale_repo_workflow_modules`
- `autoloop.core.workflow_capabilities.load_workflow_package_contract`
- `autoloop.core.workflow_capabilities._inspect_catalog_entry`
- `autoloop.core.workflow_capabilities._catalog_entry_for_reference`
- `tests.runtime.test_workflow_catalog_roots.test_repo_local_unique_alias_remains_resolvable_when_workspace_claims_workflow_name`
- `tests.runtime.test_workflow_reference_resolution.test_imported_repo_local_class_references_use_workspace_isolated_module_namespace`

## Checklist mapping
- Plan item 1 `Restore the workflow reference-resolution contract`: completed.
- Plan item 2 `Reconcile optimizer observability and selected-workflow source contracts`: deferred, not changed in this phase.
- Plan item 3 `Converge packaged-workflow compile/runtime contracts`: deferred, not changed in this phase.

## Assumptions
- `workflow_search_roots(...)` ordering and numeric precedence remain part of the adjacent green catalog contract, so named-resolution authority was changed in effective catalog selection rather than by reordering the published roots.
- Repo-local named workflow fallback must preserve the `workflows.*` module namespace for cross-workflow imports and metadata, while explicit repo-local path/directory references continue to use isolated workspace modules.
- The catalog entry model remains whole-entry oriented, so mixed-root fallback for unique lower-precedence aliases is centralized in loader key resolution rather than by partially rewriting published catalog entries.

## Preserved invariants
- `.autoloop/workflows` stays authoritative for bare names and aliases in mixed-root collisions.
- Explicit repo-local path and directory references still load under `_autoloop_workspace_workflows...`.
- Installed package workflows still use the package-module contract and keep `autoloop.workflows.*` metadata.
- Worklist selector and progress-board behavior were not touched.

## Intended behavior changes
- Effective catalog shadowing now prefers `.autoloop/workflows` entries over repo-local `workflows/` entries for named keys without altering the public root list order.
- Repo-local named catalog references no longer require `__init__.py` workflow re-exports, but they still resolve through `workflows.*` imports.
- Capability inspection can recover catalog metadata for shadowed explicit-path references by looking through `include_shadowed=True`.
- Repo-local module imports now evict stale `workflows.*` modules when switching workspace roots.
- Named workflow lookup now scans shadowed catalog entries so repo-local workflows keep unique fallback aliases even when their canonical name is shadowed by `.autoloop/workflows`.
- Direct imported repo-local `workflows.*` class objects now reload through `_autoloop_workspace_workflows...`, while named repo-local classes resolved earlier keep their named reference key so internal class-object round-trips still return `workflows.*` metadata.

## Known non-changes
- No optimizer observability normalization changes were made.
- No selected-workflow source-manifest canonicalization changes were made.
- No packaged-workflow route or framework-artifact fixes were made.

## Expected side effects
- CLI/catalog consumers now see `.autoloop/workflows` as the authoritative mixed-root named workflow when a repo-local workflow shares the same name or alias.
- Repo-local named workflow runs and selected-workflow helper snapshots retain stable `workflows.*` state/params model names across repeated resolutions in one process.

## Validation performed
- Passed: `tests/runtime/test_workflow_reference_resolution.py`
- Passed: `tests/runtime/test_workflow_catalog_roots.py`
- Passed: `tests/runtime/test_runtime_cli_metadata_integration.py`
- Passed: `tests/runtime/test_workspace_and_context.py`
- Passed: `tests/unit/test_stdlib_and_extensions.py`
- Added regression coverage for repo-only alias fallback across mixed roots.
- Added regression coverage for direct imported repo-local class-object isolation.
- Observed remaining failures, unchanged in this phase: `tests/unit/test_optimization_helpers.py` -> 10 failed / 19 passed

## Deduplication / centralization
- Kept the named-vs-explicit split centralized in catalog/loader resolution helpers instead of patching individual workflow tests or package fixtures.
