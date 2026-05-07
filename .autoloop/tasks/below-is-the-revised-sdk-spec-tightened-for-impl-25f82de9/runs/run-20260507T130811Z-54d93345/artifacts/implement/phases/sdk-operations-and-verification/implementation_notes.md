# Implementation Notes

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: implement
- Phase ID: sdk-operations-and-verification
- Phase Directory Key: sdk-operations-and-verification
- Phase Title: Finish Operations And Verification
- Scope: phase-local producer artifact

## Files changed
- `autoloop/sdk.py`
- `autoloop/runtime/runner.py`
- `tests/unit/test_sdk_facade.py`

## Symbols touched
- `autoloop.sdk.Autoloop.step`
- `autoloop.sdk._build_synthetic_step_workflow`
- `autoloop.sdk._synthetic_step_transitions`
- `autoloop.sdk._synthetic_terminal_target`
- `autoloop.runtime.runner._build_workflow_invoker`
- `autoloop.runtime.runner._execute_child_workflow_package`
- `tests.unit.test_sdk_facade.test_sdk_run_exposes_params_without_leaking_them_into_ctx_input`
- `tests.unit.test_sdk_facade.test_sdk_run_maps_failed_terminal_to_failed_result_status`

## Checklist mapping
- `Autoloop.llm/classify route through existing operation helpers`
  Status: preserved from prior phase; regression-checked in scoped SDK tests.
- `Synthetic one-step workflow execution for Autoloop.step`
  Status: completed by preserving explicit strict-step terminal tags and keeping the fallback `done -> FINISH` only for undeclared routes.
- `Acceptance-focused SDK and runtime regression tests`
  Status: completed with direct SDK coverage for params, failed-result mapping, standalone operations, pause handling, provider-question behavior, and runtime regression verification for child workflow invocation.

## Assumptions
- Bare strict `Step` instances do not carry workflow-level transition targets, so the synthetic wrapper may only derive one-step terminal routing from explicit `route_metadata` tags or the fallback `done` contract.

## Preserved invariants
- Public sync engine entrypoints still raise the active-event-loop error instead of silently bridging.
- `ctx.invoke_workflow(...)` remains synchronous for Python handlers.
- SDK `client.step(...)` still executes through `client.run(...)` and the filesystem runtime.

## Intended behavior changes
- Strict core `Step` instances passed to `client.step(...)` now honor explicit terminal route tags declared via `route_metadata` instead of being forced onto `done`.
- Child workflow invocations from synchronous Python-step handlers succeed when the parent workflow is already running inside the engine event loop.
- SDK acceptance coverage now directly verifies `params` handling at the `client.run(...)` boundary and `FAIL` to `WorkflowResult(status="failed", ok=False)` mapping.

## Known non-changes
- No async SDK API was added.
- No artifact cleanup or replay-folder deletion was introduced.
- Public sync `run`/`step` active-loop behavior remains unchanged.

## Expected side effects
- Child workflow invocations from Python steps may use a short-lived worker thread when nested inside an active engine loop.

## Validation performed
- `.venv/bin/python -m pytest -q tests/unit/test_sdk_facade.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_workspace_and_context.py`
- `.venv/bin/python -m pytest -q tests/unit/test_sdk_facade.py tests/unit/test_primitives_and_stores.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_workspace_and_context.py tests/unit/test_primitives_and_stores.py`

## Deduplication / centralization
- Centralized synthetic strict-step route synthesis in `autoloop/sdk.py` instead of hardcoding `done -> FINISH` inline.
- Centralized active-loop child workflow fallback in `autoloop/runtime/runner.py` so both `ctx.invoke_workflow(...)` and workflow-step child invocation reuse the same bridge.
