# Test Strategy

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: test
- Phase ID: async-engine-spine
- Phase Directory Key: async-engine-spine
- Phase Title: Async engine spine
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Async engine core for sequential provider-backed steps:
  Covered by `tests/contract/test_async_engine_spine.py::test_engine_run_async_is_the_sequential_execution_core`
  Checks that `Engine.run_async(...)` drives an async-only provider without touching sync provider methods.

- Sync shells remain thin outer wrappers:
  Covered by `tests/contract/test_async_engine_spine.py::test_engine_run_wrapper_executes_async_core_for_sequential_workflows`
  Checks that `Engine.run(...)` still works while the provider-backed step runs through the async-authoritative path.

- Active-event-loop failure for sync runtime wrappers:
  Covered by `tests/contract/test_async_engine_spine.py::test_engine_sync_wrappers_reject_active_event_loop_without_running_coroutines`
  Checks both `run(...)` and `resume(...)` rejection and guards against leaked never-awaited coroutine warnings.

- Sequential sync-provider compatibility preserved during this phase:
  Covered by `tests/contract/test_async_engine_spine.py::test_engine_run_async_preserves_sequential_sync_provider_compatibility`
  Checks that ordinary `route_mode="finalize"` execution still accepts the current sync-only `LLMProvider` contract.

- Async resume core:
  Covered by `tests/contract/test_async_engine_spine.py::test_engine_resume_async_uses_async_core_after_pending_input`
  Checks that `resume_async(...)` resumes from a real pending-input checkpoint and finishes on a provider-backed async step.

- Capture/branch execution stays async-only:
  Covered by existing `tests/contract/test_branch_group_runtime.py::test_parallel_branch_group_rejects_sync_only_provider_for_provider_backed_steps`
  Checks that the sequential sync-provider compatibility does not leak into branch-group execution.

## Preserved invariants checked

- Public sequential entrypoints remain `Engine.run(...)` and `Engine.resume(...)`.
- Sync wrappers fail clearly instead of bridging an already-running event loop.
- Provider-backed sequential execution no longer depends on sync engine internals.
- Resume behavior still restores checkpointed state and pending input before continuing.

## Edge cases and failure paths

- Sync wrapper invocation from an active event loop.
- Sync-only provider used in ordinary sequential execution.
- Sync-only provider used in provider-backed branch execution.
- Resume path after a direct `RequestInput` control from a Python step.

## Stabilization / flake control

- All new tests use in-memory stores and local temp directories only.
- No timing assertions, subprocesses, network calls, or ordering-sensitive concurrency expectations were added.
- Active-loop tests use warning capture plus `gc.collect()` to detect leaked coroutines deterministically.

## Known gaps

- CLI/runner entrypoints are still covered indirectly through engine-facing smoke tests rather than a new phase-local CLI test.
- Provider transport async-native conversion remains out of phase; current coverage assumes the existing rendered-provider transport compatibility stays in place.
