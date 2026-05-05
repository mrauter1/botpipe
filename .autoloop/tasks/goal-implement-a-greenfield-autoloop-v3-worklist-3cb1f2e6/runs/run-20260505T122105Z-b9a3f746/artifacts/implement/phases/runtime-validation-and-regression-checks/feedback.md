# Implement ↔ Code Reviewer Feedback

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: implement
- Phase ID: runtime-validation-and-regression-checks
- Phase Directory Key: runtime-validation-and-regression-checks
- Phase Title: Validate runtime behavior and guard regressions
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking`
  File / symbol: `autoloop/core/context.py::_resolve_context_root`, with downstream failures in `autoloop_optimizer/portfolio.py::_repo_root_from_context` and `autoloop_optimizer/company.py::_repo_root_from_context`.
  Failure: when a lifecycle context is built with `package_folder=<repo>/workflows/<name>` and no explicit `root`, `_resolve_context_root` only recognizes `autoloop/workflows` and `.autoloop/workflows`, so it falls back to `task_folder`. The portfolio and company snapshot helpers then write the wrong `repo_root` (`.../.autoloop/tasks/task-1`) and resolve workflow aliases against that task-local path, producing the failures seen in `tests/unit/test_stdlib_and_extensions.py::test_portfolio_helper_writes_workflow_local_catalog_snapshot`, `::test_portfolio_health_helper_writes_grouped_workflow_run_health_via_shared_resolution_and_run_summaries`, and `::test_company_helpers_write_bounded_company_operation_snapshot_without_mutating_autoloop_state`.
  Minimal fix direction: centralize repo-root inference so plain `workflows/` is treated as a valid repo marker, or ensure lifecycle/optimizer helpers always receive an explicit repo root instead of relying on the fallback path.

- IMP-002 `blocking`
  File / symbol: `autoloop/core/workflow_catalog.py::workflow_search_roots`.
  Failure: workflow discovery currently searches only `<root>/.autoloop/workflows` plus installed package workflows. The adjacent runtime tests create temporary packages under `<root>/workflows/<workflow_name>`, so `run_workflow_package(..., root=tmp_path)` cannot resolve names like `parent_typed`, `parent_failing`, or `compile_cache_demo`, producing the `WorkflowDiscoveryError` failures in `tests/runtime/test_workspace_and_context.py` and leaving AC-3 unmet.
  Minimal fix direction: centralize catalog discovery so the repo-local `workflows/` tree is searched alongside `.autoloop/workflows` and installed package workflows, then rerun the requested adjacent regression suites.

## Re-review

- IMP-003 `non-blocking`
  File / symbol: review sweep across `autoloop/core/context.py`, `autoloop/core/workflow_catalog.py`, `autoloop/runtime/loader.py`, `autoloop/core/workflow_capabilities.py`, `autoloop_optimizer/portfolio.py`, `tests/runtime/test_workflow_catalog_roots.py`, and `tests/unit/test_stdlib_and_extensions.py`.
  Finding: no additional issues after the follow-up patch set. The previous blockers are resolved by first-class repo-local `workflows/` discovery/import support, workspace-scoped portfolio snapshots, and updated adjacent assertions. The verifier reran the requested commands and observed `173 passed` for the adjacent regression suite and `49 passed` for the focused selector/progress suite.
  Minimal fix direction: none.
