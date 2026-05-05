# Implementation Notes

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: implement
- Phase ID: async-branch-runtime
- Phase Directory Key: async-branch-runtime
- Phase Title: Async Branch Runtime
- Scope: phase-local producer artifact

## Files Changed

- `autoloop/core/branch_groups/manifest.py`
- `autoloop/core/branch_groups/runtime.py`
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `tests/contract/test_branch_group_runtime.py`
- `tests/runtime/test_runtime_tracing.py`
- `tests/unit/test_branch_group_context_sessions.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/strictness/test_no_compat.py`
- `runs/run-20260505T201926Z-7fdaad17/decisions.txt`

## Symbols Touched

- `branch_group_paths`
- `BranchGroupRuntime.run_async`
- `BranchGroupRuntime._run_branches`
- `BranchGroupRuntime._execute_branch`
- `BranchGroupRuntime._emit_branch_result_event`
- `Engine._resolve_workspace_read_path`
- `StepDispatcher._execute_pair_step_async`
- `StepDispatcher._execute_llm_step_async`
- `StepDispatcher._run_pair_step_async`
- `StepDispatcher._run_llm_step_async`

## Checklist Mapping

- Plan milestone 3 / phase AC-1, AC-2, AC-3:
  - Replaced sequential branch execution with `asyncio.Task` scheduling and `asyncio.Semaphore` concurrency limiting.
  - Implemented lazy launch plus `fail_fast` stop/cancel semantics with declaration-order manifest preservation.
- Plan milestone 3 / phase AC-4:
  - Kept branch-group orchestration in the dedicated subsystem, rooted branch-group evidence under `workflow_folder/_branch_groups`, and expanded runtime-tracing coverage for scheduled/completed/needs-input/failed/cancelled/skipped events.
- Plan milestone 6:
  - Added a strictness scan that fails if forbidden thread-backed primitives reappear under `autoloop/core/branch_groups`.

## Intended Behavior Changes

- Provider-backed branch groups now execute branches concurrently when `concurrency > 1`.
- `settle="fail_fast"` now cancels already-running async branch tasks best-effort and records them as `cancelled`; only never-launched tail branches are `skipped`.
- Async provider-step cancellation now propagates as `CancelledError` instead of being rewritten into retry/annotation failures.
- Branch-group evidence and fan-in helper reads now resolve under `{workflow_folder}/_branch_groups/...` instead of the task root.

## Preserved Invariants

- Composite branch-group execution still returns a normal `StepExecutionResult` to the engine.
- Branch manifest ordering remains declaration-stable regardless of completion order.
- Branch capture mode still avoids following branch destinations and still skips route `on_taken` hooks.
- Engine sync entrypoints remain thin outer callers over the async branch runtime.

## Known Non-Changes

- Branch-session overlay semantics were not changed in this phase; synthetic session-id removal and parent-fallback cleanup remain deferred.

## Assumptions

- Async cancellation guarantees are phase-scoped to provider-backed branch execution; synchronous Python branch bodies can still block the event loop until they yield/return.

## Expected Side Effects

- Runtime traces now include cancellation/skip events for fail-fast groups when async branch work is interrupted.
- Provider-backed cancellation no longer increments retry/error handling paths for the cancelled branch task.

## Validation Performed

- `.venv/bin/python -m pytest tests/contract/test_branch_group_runtime.py tests/runtime/test_runtime_tracing.py tests/unit/test_branch_group_context_sessions.py tests/unit/test_primitives_and_stores.py tests/contract/test_async_step_dispatcher.py tests/strictness/test_no_compat.py -q`
- `.venv/bin/python -m pytest tests/contract/test_engine_contracts.py tests/unit/test_branch_group_context_sessions.py tests/unit/test_primitives_and_stores.py -q`

## Deduplication / Centralization

- Centralized branch terminal event emission in `BranchGroupRuntime._emit_branch_result_event` so completed/failed/cancelled/skipped paths share one metadata shape.
- Centralized the evidence-root migration in `branch_group_paths(...)` plus `Engine._resolve_workspace_read_path(...)` so runtime writers and `_branch_groups/...` readers stay aligned without duplicating path logic in fan-in call sites.
