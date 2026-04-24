# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t114109-bootstrap
- Pair: implement
- Phase ID: resolver-foundation
- Phase Directory Key: resolver-foundation
- Phase Title: Resolver Foundation
- Scope: phase-local producer artifact

## Files changed

- `runtime/loader.py`
- `runtime/runner.py`
- `runtime/workspace.py`
- `runtime/cli.py`
- `runtime/__init__.py`
- `core/context.py`
- `core/engine.py`
- `core/validation.py`
- `stdlib/portfolio.py`
- `stdlib/company.py`
- `stdlib/adaptation.py`
- `stdlib/decomposition.py`
- `stdlib/evaluation.py`
- `stdlib/diagnostics.py`
- `stdlib/refinement.py`
- `tests/runtime/test_workflow_reference_resolution.py`

## Symbols touched

- `runtime.loader.WorkflowReference`
- `runtime.loader.resolve_workflow_reference`
- `runtime.loader.load_workflow_package_class`
- `runtime.loader.load_compiled_workflow_package`
- `runtime.runner.execute_workflow_package`
- `runtime.runner._ensure_workflow_workspace`
- `runtime.runner._assert_workflow_identity_consistency`
- `runtime.workspace.WorkflowWorkspace`
- `runtime.workspace.ensure_workflow_workspace`
- `runtime.workspace.update_run_metadata`
- `runtime.workspace.update_workflow_metadata`
- `core.context.Context`
- `core.engine.Engine.run`
- `core.validation.describe_workflow_class`

## Checklist mapping

- Plan item 1: added resolver/runtime regression coverage for single-file, directory, module/class, ambiguity, prompt scope, parameter precedence, and origin collisions.
- Plan items 2-6: implemented unified workflow-reference resolution, isolated file imports, prompt/package-folder propagation, parameter precedence, and snake_case fallback naming.
- Plan item 7: not addressed in this phase; shallow catalog discovery migration remains deferred.
- Plan item 8: not addressed in this phase; deep inspection/capability payload migration remains deferred.
- AC-1/AC-2/AC-3/AC-4: implemented in loader/runner/workspace/context plus new runtime tests.

## Preserved invariants

- Root `workflow` shim export surface unchanged.
- Manifest parsing remains metadata-only; no runtime topology moved into `workflow.toml`.
- Existing manifest-backed `workflow.py` packages and package-export checks remain supported.
- `specs.py` remains ordinary Python; runtime only sees it when author code imports it.

## Intended behavior changes

- `autoloop` execution now resolves names, aliases, explicit `.py` files, workflow directories, module refs, and imported workflow classes through one loader path.
- Explicit `flow.py` / `workflow.py` path loads support sibling relative imports without requiring `__init__.py`.
- Runtime metadata now persists workflow origin details under `workflow`.
- Unnamed workflow fallback identity is now snake_case rather than raw class name.
- Runtime/stdlib callers can use `ctx.root` instead of inferring repo root from package layout.

## Known non-changes

- Shallow catalog discovery/list output remains manifest-centric outside the named-runtime inference path.
- Deep capability inspection payload migration is still pending.
- Scaffold/builder/docs/template rewrites are still pending.

## Expected side effects

- Existing path-based or named runs for the same canonical workflow now reject conflicting origins before sharing a task workflow directory.
- Equivalent refs to the same origin remain compatible because collision checks key on normalized origin metadata, not the raw ref string.

## Validation performed

- `python3 -m py_compile runtime/loader.py runtime/runner.py runtime/workspace.py runtime/cli.py core/context.py core/engine.py core/validation.py stdlib/portfolio.py stdlib/company.py stdlib/adaptation.py stdlib/decomposition.py stdlib/evaluation.py stdlib/diagnostics.py stdlib/refinement.py runtime/__init__.py tests/runtime/test_workflow_reference_resolution.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_workflow_reference_resolution.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_compatibility_runtime.py tests/runtime/test_workspace_and_context.py tests/runtime/test_workflow_reference_resolution.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_package_cli.py::test_cli_workflows_show_reports_parameters_and_aliases tests/runtime/test_package_cli.py::test_cli_workflow_resolution_prefers_canonical_names_and_rejects_ambiguous_aliases tests/runtime/test_package_cli.py::test_cli_serializes_typed_workflow_parameters_as_json_safe_values tests/runtime/test_package_cli.py::test_cli_run_resume_answer_and_diagnostics_follow_package_contract`
- `.venv/bin/python -m pytest -q tests/unit/test_stdlib_and_extensions.py::test_portfolio_helper_writes_workflow_local_catalog_snapshot tests/unit/test_stdlib_and_extensions.py::test_portfolio_health_helper_writes_grouped_workflow_run_health_via_shared_resolution_and_run_summaries tests/unit/test_stdlib_and_extensions.py::test_company_helpers_write_bounded_company_operation_snapshot_without_mutating_autoloop_state tests/unit/test_stdlib_and_extensions.py::test_refinement_helper_accepts_main_workflow_class_references tests/unit/test_stdlib_and_extensions.py::test_decomposition_helper_accepts_main_workflow_class_references tests/unit/test_stdlib_and_extensions.py::test_diagnostics_helper_accepts_main_workflow_class_references_and_allows_empty_filtered_histories tests/unit/test_stdlib_and_extensions.py::test_evaluation_helper_validates_eval_cases_via_selected_workflow_snapshot_and_loader_paths`
- Broader full-file runs for `tests/runtime/test_package_cli.py` and `tests/unit/test_stdlib_and_extensions.py -k 'portfolio or diagnostics or evaluation or decomposition or refinement or adaptation or company'` still hit pre-existing wrapper/template and missing-doc failures outside this phase slice.

## Deduplication / centralization

- Centralized workflow-origin persistence in `runtime.workspace._workflow_origin_payload`.
- Centralized resolver branching and parameter precedence in `runtime.loader` instead of adding alternate execution paths.
