# Test Strategy

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: test
- Phase ID: namespace-cut-optimizer-boundary-prompts-and-extensions
- Phase Directory Key: namespace-cut-optimizer-boundary-prompts-and-extensions
- Phase Title: Namespace Cut Optimizer Boundary Prompts And Extensions
- Scope: phase-local producer artifact

## Behavior Coverage Map

- `autoloop.runtime.inspection` stable read API:
  covered by `tests/runtime/test_workspace_and_context.py::test_runtime_inspection_loaders_filter_status_and_require_disambiguation`
  checks canonical status filtering, ambiguous run-id rejection, filtered record lookup, metadata/topology/history loading, and missing-run failure.
- Workflow-facing git/tracing declaration removal:
  covered by `tests/runtime/test_optional_extensions.py::test_workflow_extension_exports_drop_git_tracking_and_tracing_declarations`
  checks removed public exports stay absent while retained workflow extension helpers and runtime-owned git helpers remain importable.

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
