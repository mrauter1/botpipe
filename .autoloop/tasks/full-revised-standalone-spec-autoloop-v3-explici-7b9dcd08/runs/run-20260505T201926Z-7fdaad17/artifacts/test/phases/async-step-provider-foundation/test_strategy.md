# Test Strategy

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: test
- Phase ID: async-step-provider-foundation
- Phase Directory Key: async-step-provider-foundation
- Phase Title: Async Step Foundation
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 native async provider execution without thread offloading:
  - `tests/unit/test_provider_boundary_core.py`
    - fake provider async turn methods
    - rendered provider async turn methods
  - `tests/runtime/test_runtime_providers.py`
    - async Codex and Claude transport subprocess execution
  - `tests/contract/test_branch_group_runtime.py`
    - provider-backed branch groups use async-only provider methods from sync `Engine.run(...)`
  - `tests/contract/test_async_step_dispatcher.py`
    - direct `await step_dispatcher.execute_async(...)` on a composite branch-group step uses async provider-backed branch execution inside an active event loop

- AC-2 async one-step execution with hooks, artifacts, validation, and route capture:
  - `tests/contract/test_async_step_dispatcher.py`
    - capture mode runs before/after hooks, writes artifacts, and skips route `on_taken`
    - finalize mode on a branch-group composite step resolves through the async runtime path and reaches the expected destination
  - `tests/contract/test_branch_group_runtime.py`
    - fan-in helper metadata remains available after async capture-mode nested execution
    - sync-only providers still fail before branch-group execution can degrade into implicit sync fallback

- AC-3 clear failure for sync-only providers in provider-backed branch groups:
  - `tests/contract/test_branch_group_runtime.py`
    - sync-only provider raises `WorkflowExecutionError` with async-provider requirement language

## Preserved invariants checked

- Sync top-level entrypoints remain usable while delegating branch-group internals to the async runtime path.
- Capture-mode direct use from a running event loop raises cleanly instead of silently bridging.
- The lazy sync bridge no longer recreates the old unawaited-coroutine warning path.

## Edge cases and failure paths

- Active event loop + sync capture wrapper:
  - `tests/contract/test_async_step_dispatcher.py` captures warnings, forces `gc.collect()`, and asserts that no `coroutine ... was never awaited` warning is emitted after the expected `RuntimeError`.
- Composite branch-group execution from an async caller:
  - verified with direct `await step_dispatcher.execute_async(...)` on a provider-backed `parallel(...)` step.
- Sync-only provider on provider-backed branch group:
  - verified as explicit failure, not fallback.

## Flake-risk controls

- No wall-clock timing assertions.
- Async tests use deterministic fake providers and `asyncio.run(...)` around bounded local coroutines only.
- Warning-path coverage forces `gc.collect()` so the old coroutine-leak warning is observed deterministically if it regresses.

## Known gaps

- This phase does not cover `asyncio.Task`/`Semaphore` branch scheduling because concurrent scheduler work is explicitly deferred.
- This phase does not extend evidence-root or branch-session overlay coverage, which remain deferred by plan.
