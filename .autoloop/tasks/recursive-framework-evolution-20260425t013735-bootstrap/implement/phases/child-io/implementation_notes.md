# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: implement
- Phase ID: child-io
- Phase Directory Key: child-io
- Phase Title: Typed Child Workflow IO
- Scope: phase-local producer artifact

## Files Changed

- `core/context.py`
- `core/compiler.py`
- `core/engine.py`
- `runtime/runner.py`
- `runtime/workspace.py`
- `stdlib/composition.py`
- `workflow/primitives.py`
- `tests/runtime/test_workspace_and_context.py`
- `.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/decisions.txt`

## Symbols Touched

- `ChildWorkflowResult`
- `Context.input`
- `Context.invoke_workflow(...)`
- `CompiledWorkflow.input_model`
- `CompiledWorkflow.output_model`
- `CompiledWorkflow.output_builder`
- `RunResult.output`
- `RunResult.output_validation_error`
- `RunnerOptions.workflow_input`
- `RunExecution.workflow_input`
- `resolve_run_workflow_input(...)`
- `run_child_workflow(...)`

## Checklist Mapping

- Phase 8 / typed child IO:
  - implemented `Input` / `Output` / `build_output` compile-time discovery
  - threaded typed child input through `ctx.invoke_workflow(...)`, runner, engine context creation, and resume metadata
  - extended `ChildWorkflowResult` additively with `output`, `artifacts`, and `metadata`
  - recorded typed-output validation status in child `run.json` and parent `children.jsonl`
  - added runtime regression coverage for typed child input/output success and typed-output validation failure

## Preserved Invariants

- Legacy `ctx.invoke_workflow(..., message=..., parameters=...)` remains valid.
- Legacy child result fields `output_metadata`, `output_artifacts`, `last_event`, and path fields remain present.
- Child output validation does not change the child run terminal/status; it is additive metadata only.
- No root-shim cleanup or docs changes were made in this phase.

## Intended Behavior Changes

- Child workflows may now declare nested `Input` / `Output` models and `build_output(state, ctx)`.
- Runtime contexts now expose typed child input via `ctx.input`.
- Parent callers can pass `input=...` to `ctx.invoke_workflow(...)` and receive validated typed output via `ChildWorkflowResult.output`.

## Known Non-Changes

- CLI/root-workflow input authoring was not added.
- Capability inspection/docs/strictness export cleanup remains deferred to later phases.
- Fatal child-run records still use the legacy minimal payload plus additive empty/default fields; no new fatal recovery path was introduced.

## Assumptions

- Nested `Input` / `Output` follow the same `BaseModel` convention as `State` / `Parameters`.
- `build_output(...)` is optional; when `Output` is declared without it, the run remains successful and the missing builder is surfaced as typed-output metadata.

## Expected Side Effects

- Child `run.json` now carries `workflow_input` when typed child input is provided.
- Child `run.json` and parent `children.jsonl` may carry additive `typed_output` / `output` / `artifacts` / `metadata` fields.

## Validation Performed

- `python3 -m py_compile core/context.py core/compiler.py core/engine.py runtime/runner.py runtime/workspace.py stdlib/composition.py workflow/primitives.py tests/runtime/test_workspace_and_context.py`
- Attempted targeted runtime validation, but the environment is missing `pydantic` and `pytest`, so import-time execution and repository tests could not be run here.

## Deduplication / Centralization

- Centralized typed child-input coercion/materialization in `runtime/runner.py` so parent invocation, new runs, and resumes share one validation path.
- Centralized terminal output construction in `Engine._build_workflow_output(...)` so success/pause/fail all use one additive typed-output contract.
