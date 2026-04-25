# Test Strategy

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: test
- Phase ID: child-io
- Phase Directory Key: child-io
- Phase Title: Typed Child Workflow IO
- Scope: phase-local producer artifact

## Behavior → Coverage Map

- Typed child input reaches fresh child runs and is persisted in child `run.json`
  - `tests/runtime/test_workspace_and_context.py::test_context_invoke_workflow_supports_typed_child_input_and_output`
  - `tests/runtime/test_workspace_and_context.py::test_context_invoke_workflow_records_typed_child_output_validation_failures`
  - `tests/runtime/test_workspace_and_context.py::test_create_run_persists_workflow_input_and_resolve_run_workflow_input_handles_fresh_and_stored_paths`
- Typed child output is returned additively without removing legacy child metadata/artifact fields
  - `tests/runtime/test_workspace_and_context.py::test_context_invoke_workflow_supports_typed_child_input_and_output`
- Typed child-output validation failures are recorded explicitly rather than hidden
  - `tests/runtime/test_workspace_and_context.py::test_context_invoke_workflow_records_typed_child_output_validation_failures`

## Preserved Invariants Checked

- `ChildWorkflowResult.output_metadata` and `output_artifacts` remain populated as legacy surfaces.
- Parent `children.jsonl` records keep legacy fields while adding `output`, `artifacts`, and `metadata`.
- Stored `workflow_input` wins on re-read once it is present in `run.json`.

## Edge Cases / Failure Paths

- Fresh `run.json` exists but lacks `workflow_input`: helper falls back to the caller-supplied payload.
- Persisted `workflow_input` exists: helper ignores a conflicting newly passed payload and returns stored state.
- Invalid typed child output keeps child run status successful while surfacing a validation error in child metadata.

## Known Gaps

- Could not run `pytest` in this environment because runtime dependencies are unavailable here; coverage was limited to static `py_compile`.
