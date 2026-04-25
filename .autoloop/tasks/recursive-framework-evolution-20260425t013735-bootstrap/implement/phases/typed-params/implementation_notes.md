# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: implement
- Phase ID: typed-params
- Phase Directory Key: typed-params
- Phase Title: Typed Workflow Parameters
- Scope: phase-local producer artifact

## Files Changed

- `core/context.py`
- `core/engine.py`
- `runtime/loader.py`
- `runtime/runner.py`
- `tests/runtime/test_workspace_and_context.py`
- `tests/unit/test_primitives_and_stores.py`
- `.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/decisions.txt`

## Symbols Touched

- `core.context.EmptyParameters`
- `Context.__init__`
- `Context.params`
- `Engine.run`
- `Engine.resume`
- `runtime.loader.materialize_workflow_params`
- `runtime.loader._instantiate_workflow_parameters`
- `runtime.loader._workflow_parameter_payload`
- `runtime.loader._workflow_parameter_snapshot_model`
- `runtime.runner.execute_workflow_package`
- `runtime.runner._execute_compiled_workflow`

## Checklist Mapping

- Phase 5 / typed params:
  - implemented `ctx.params`
  - preserved `ctx.workflow_params`
  - restored typed params from persisted run metadata on resume
  - defaulted missing `Parameters` declarations to immutable empty params
- Deferred:
  - no docs updates in this phase
  - no child-workflow typed output changes in this phase

## Assumptions

- Runtime callers still resolve workflow references before execution, so the runner can derive the active `Parameters` type there without expanding compiled-workflow metadata in this phase.
- Existing workflows that pass ad hoc `workflow_params` programmatically without a declared `Parameters` model should keep working through `ctx.workflow_params`; `ctx.params` is additive and empty in that case.

## Preserved Invariants

- `ctx.workflow_params` remains a dict copy.
- Resume continues to prefer persisted `run.json` params over new overrides.
- No route/effect, worklist, or child-output behavior was changed.
- No root `workflow` shim exports were changed in this phase.

## Intended Behavior Changes

- Runtime-backed contexts now expose `ctx.params` as a typed Pydantic model.
- When a workflow declares `Parameters`, the runner materializes `ctx.params` from the resolved/persisted parameter mapping on both new runs and resumes.
- When a workflow does not declare `Parameters`, `ctx.params` is `EmptyParameters()` and is frozen.

## Known Non-Changes

- `run.json` continues to persist only the JSON-safe `workflow_params` mapping.
- `resolve_run_workflow_params(...)` still treats persisted metadata as authoritative on resume.
- CLI/help/capability inspection surfaces were not edited in this phase.

## Expected Side Effects

- Programmatic runner calls that pass invalid values to a declared `Parameters` model now fail when the runner materializes `ctx.params`, matching the typed-runtime contract.
- Non-BaseModel `Parameters` types are adapted into a frozen BaseModel snapshot for `ctx.params`; `ctx.workflow_params` remains the serialized compatibility surface.

## Validation Performed

- `python3 -m py_compile core/context.py core/engine.py runtime/loader.py runtime/runner.py tests/runtime/test_workspace_and_context.py tests/unit/test_primitives_and_stores.py`
- Attempted but unavailable in this environment:
  - `pytest` not installed
  - `python3 -m pytest ...` unavailable because `pytest` is missing
  - runtime import exercise unavailable because the system interpreter also lacks `pydantic`

## Deduplication / Centralization

- Centralized typed-param construction in `runtime.loader.materialize_workflow_params(...)` so runner startup and resume share the same reconstruction path.
- Reused `EmptyParameters` from `core.context` as the single fallback model instead of duplicating empty-model definitions across runtime modules.
