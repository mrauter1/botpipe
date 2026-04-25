# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: implement
- Phase ID: typed-params
- Phase Directory Key: typed-params
- Phase Title: Typed Workflow Parameters
- Scope: phase-local authoritative verifier artifact

- `IMP-001` | `blocking` | `runtime/runner.py:_execute_compiled_workflow`, `runtime/workspace.py:create_run`, `runtime/loader.py:materialize_workflow_params`
  The runner still persists raw `RunnerOptions.workflow_params` into `run.json` before it has normalized or rejected them through the declared `Parameters` model. In a direct runtime call such as `run_workflow_package(..., workflow_params={"unknown": "x"})`, `create_run(...)` writes the unchecked mapping first, then `materialize_workflow_params(...)` validates later and may either fail after the run directory already contains invalid persisted params or silently diverge from persisted state when the `Parameters` model ignores extras. That violates the phase objective to validate, persist, and restore typed params through the runtime path, and it creates resume drift between `ctx.params` and `ctx.workflow_params`. Minimal fix direction: normalize `options.workflow_params` with the existing `coerce_workflow_parameter_mapping(...)` before `create_run(...)`/`update_run_metadata(...)`, then reuse that one normalized mapping for both persistence and `materialize_workflow_params(...)`.
