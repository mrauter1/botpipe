# Test Strategy

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: test
- Phase ID: typed-params
- Phase Directory Key: typed-params
- Phase Title: Typed Workflow Parameters
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- `ctx.params` exists on runs without a declared `Parameters` model.
  Coverage: `tests/unit/test_primitives_and_stores.py::test_context_defaults_params_to_an_immutable_empty_model`
  Preserved invariant: `ctx.workflow_params` remains separate compatibility data and `ctx.params` falls back to immutable `EmptyParameters`.

- New runs expose typed params alongside backward-compatible dict params.
  Coverage: `tests/runtime/test_workspace_and_context.py::test_context_exposes_typed_params_on_new_runs`
  Happy path: provider sees typed attribute access and raw dict access for the same supplied values.

- New runs persist the normalized parameter snapshot, not raw caller input.
  Coverage: `tests/runtime/test_workspace_and_context.py::test_new_runs_persist_normalized_workflow_params_snapshot`
  Edge case: defaults and Pydantic coercion are reflected identically in `ctx.params`, `ctx.workflow_params`, and `run.json`.

- Invalid direct-run workflow params fail before runtime state is created.
  Coverage: `tests/runtime/test_workspace_and_context.py::test_new_runs_validate_workflow_params_before_persisting_run_metadata`
  Failure path: unknown keys raise `WorkflowParameterError` and `.autoloop` is not created.

- Resume restores typed params from persisted metadata and ignores override drift.
  Coverage: `tests/runtime/test_workspace_and_context.py::test_resume_restores_typed_params_from_persisted_run_metadata`
  Coverage: `tests/runtime/test_workspace_and_context.py::test_resume_ignores_explicit_workflow_param_override_for_existing_run`
  Preserved invariant: stored run metadata remains authoritative on resume for both typed and dict access.

## Known Gaps

- In-turn execution coverage is limited by the local environment; the available interpreter may not have the project test dependencies installed.
- This phase does not add child-workflow typed-output assertions because that behavior is explicitly out of scope.
