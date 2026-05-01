# Test Strategy

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: test
- Phase ID: namespace-cut-optimizer-boundary-prompts-and-extensions
- Phase Directory Key: namespace-cut-optimizer-boundary-prompts-and-extensions
- Phase Title: Namespace Cut Optimizer Boundary Prompts And Extensions
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Hard namespace cut for removed compatibility/internal package roots:
  covered by `tests/strictness/test_no_compat.py::test_deleted_workflow_package_paths_do_not_exist`
  and `tests/strictness/test_no_compat.py::test_deleted_top_level_and_compatibility_package_imports_fail`
  checks that `autoloop_v3` plus top-level `core`/`runtime`/`stdlib`/`extensions` paths remain absent and unsupported.
- Prompt-registry widening beyond the immediate workflow package root:
  covered by `tests/unit/test_primitives_and_stores.py::test_prompt_registry_roots_include_capability_prompt_dirs_outside_workflow_parent`
  checks capability-derived prompt directories outside the workflow parent remain part of runtime prompt resolution roots.
- `autoloop.runtime.inspection` stable read API:
  covered by `tests/runtime/test_workspace_and_context.py::test_runtime_inspection_loaders_filter_status_and_require_disambiguation`
  checks canonical status filtering, ambiguous run-id rejection, filtered record lookup, metadata/topology/history loading, and missing-run failure.
- Workflow-facing git/tracing declaration removal:
  covered by `tests/runtime/test_optional_extensions.py::test_workflow_extension_exports_drop_git_tracking_and_tracing_declarations`
  and `tests/runtime/test_optional_extensions.py::test_removed_workflow_observability_declaration_modules_are_not_importable`
  checks removed public exports stay absent, deleted declaration modules stay non-importable, and retained workflow extension helpers plus runtime-owned git helpers remain importable.

## Preserved Invariants Checked

- Namespace cut keeps runtime-owned observability/tracking support available through runtime config, not workflow declarations.
- Inspection loaders remain read-only and require explicit narrowing when run ids are not unique across task/workflow history.

## Edge Cases / Failure Paths

- Ambiguous `run_id` across tasks must fail clearly instead of returning an arbitrary run record.
- Missing run ids must raise `FileNotFoundError`.
- Removed extension declarations must not reappear through package re-exports.

## Known Gaps

- The new inspection regression currently exposes an implementation bug: `load_run_metadata()` calls `validate_persisted_schema` with the wrong argument shape and fails before the topology/history assertions complete.
- I did not broaden this pass to full optimizer workflow integration reruns because the focused inspection seam already exposed a concrete phase-local defect.
