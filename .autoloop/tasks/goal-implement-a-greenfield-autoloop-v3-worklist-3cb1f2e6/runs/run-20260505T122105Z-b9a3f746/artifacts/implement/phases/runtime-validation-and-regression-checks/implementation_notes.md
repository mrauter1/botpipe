# Implementation Notes

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: implement
- Phase ID: runtime-validation-and-regression-checks
- Phase Directory Key: runtime-validation-and-regression-checks
- Phase Title: Validate runtime behavior and guard regressions
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/context.py`
- `autoloop/core/workflow_capabilities.py`
- `autoloop/core/workflow_catalog.py`
- `autoloop/runtime/loader.py`
- `autoloop_optimizer/portfolio.py`
- `tests/runtime/test_workflow_catalog_roots.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `.autoloop/tasks/goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6/runs/run-20260505T122105Z-b9a3f746/decisions.txt`
- `.autoloop/tasks/goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6/runs/run-20260505T122105Z-b9a3f746/artifacts/implement/phases/runtime-validation-and-regression-checks/implementation_notes.md`

## Symbols touched
- `autoloop.core.context._resolve_context_root`
- `autoloop.core.workflow_catalog.repo_workflows_root`
- `autoloop.core.workflow_catalog.workflow_search_roots`
- `autoloop.core.workflow_catalog.read_workflow_manifest`
- `autoloop.core.workflow_catalog._discover_search_root`
- `autoloop.core.workflow_catalog._build_entry`
- `autoloop.core.workflow_catalog._discover_test_paths`
- `autoloop.runtime.loader._import_repo_module`
- `autoloop.runtime.loader._evict_stale_repo_workflow_modules`
- `autoloop.runtime.loader._resolve_catalog_entry_reference`
- `autoloop.core.workflow_capabilities.load_workflow_package_contract`
- `autoloop.core.workflow_capabilities._inspect_catalog_entry`
- `autoloop.core.workflow_capabilities._import_discovered_module`
- `autoloop.core.workflow_capabilities._evict_stale_workflow_modules`
- `autoloop_optimizer.portfolio.write_workflow_portfolio_snapshot`
- `autoloop_optimizer.portfolio.write_workflow_portfolio_health_snapshot`
- `autoloop_optimizer.portfolio.write_workflow_capability_snapshot`
- `autoloop_optimizer.portfolio._workspace_catalog`
- `autoloop_optimizer.portfolio._workspace_capability_catalog`
- `tests.runtime.test_workflow_catalog_roots._clear_workflow_modules`

## Checklist mapping
- Runtime integration coverage: preserved the new progress-worklist runtime coverage and revalidated `tests/runtime/test_progress_worklists.py`.
- Focused regression command: passed via `.venv/bin/pytest tests/unit/test_worklist_selectors.py tests/unit/test_stdlib_progress_worklists.py tests/runtime/test_progress_worklists.py`.
- Adjacent regression command: fixed the directly exposed repo-root/catalog/import breakpoints surfaced by review and passed `.venv/bin/pytest tests/unit/test_stdlib_and_extensions.py tests/unit/test_primitives_and_stores.py tests/runtime/test_workspace_and_context.py`.
- Compatibility follow-up: updated adjacent expectations that intentionally moved from `autoloop/workflows/...` to repo-local `workflows/...`.

## Assumptions
- The remaining adjacent failures from the previous turn were in-scope because the new worklist paths rely on correct repo-root and workflow-discovery behavior during runtime validation.

## Preserved invariants
- No provider, checkpoint, or session internals were changed.
- No route helper wrappers, legacy selector aliases, or legacy worklist board-shape compatibility were added.
- Core and stdlib worklist behavior from earlier phases was not modified in this turn.

## Intended behavior changes
- Repo-local workflow packages under `<repo>/workflows` now participate in context root resolution, catalog discovery, capability inspection, and runtime import using `workflows.*` module names.
- Catalog discovery now finds repo-level runtime tests for discovered workflows.
- Portfolio and capability helper snapshots now stay scoped to workspace-discovered workflows instead of mixing in installed package workflows.

## Known non-changes
- Did not modify `autoloop/core/worklists.py`, `autoloop/stdlib/worklists.py`, provider code, checkpoint code, session code, or route internals in this phase.
- Did not restore unsupported legacy board shapes, aliases, or package-relative `autoloop/workflows/...` repo paths.

## Expected side effects
- Temp-root test runs no longer reuse stale cached `workflows.*` modules across different repo roots.
- Repo-local workflow diagnostics and capability payloads now emit repo-relative paths rooted at `workflows/` and `docs/workflows/`.

## Validation performed
- `.venv/bin/pytest tests/runtime/test_workflow_catalog_roots.py tests/unit/test_stdlib_and_extensions.py::test_portfolio_helper_writes_workflow_local_catalog_snapshot tests/unit/test_stdlib_and_extensions.py::test_portfolio_health_helper_writes_grouped_workflow_run_health_via_shared_resolution_and_run_summaries tests/unit/test_stdlib_and_extensions.py::test_company_helpers_write_bounded_company_operation_snapshot_without_mutating_autoloop_state tests/runtime/test_workspace_and_context.py::test_run_creates_task_workflow_run_layout_and_immutable_request_snapshots tests/runtime/test_workspace_and_context.py::test_context_invoke_workflow_supports_typed_child_input_and_output tests/runtime/test_workspace_and_context.py::test_compile_workflow_recompiles_when_source_changes`
  Result: 24 passed.
- `.venv/bin/pytest tests/unit/test_stdlib_and_extensions.py`
  Result: 97 passed.
- `.venv/bin/pytest tests/unit/test_stdlib_and_extensions.py tests/unit/test_primitives_and_stores.py tests/runtime/test_workspace_and_context.py`
  Result: 173 passed.
- `.venv/bin/pytest tests/unit/test_worklist_selectors.py tests/unit/test_stdlib_progress_worklists.py tests/runtime/test_progress_worklists.py`
  Result: 49 passed.

## Deduplication / centralization decisions
- Centralized repo-local workflow support in existing catalog, loader, context, and capability helpers rather than adding a parallel repo-workflow resolution path.
- Reused shared workspace-catalog filtering in portfolio helpers instead of duplicating per-snapshot filtering rules.
