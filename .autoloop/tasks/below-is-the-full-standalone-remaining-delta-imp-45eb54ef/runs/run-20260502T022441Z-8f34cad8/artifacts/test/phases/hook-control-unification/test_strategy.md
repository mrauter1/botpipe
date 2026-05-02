# Test Strategy

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: test
- Phase ID: hook-control-unification
- Phase Directory Key: hook-control-unification
- Phase Title: Hook And Control Unification
- Scope: phase-local producer artifact

## Coverage Map
- `tests/contract/test_engine_contracts.py`: pre-provider `before` route short-circuit now asserts `candidate_route is None`, `provider_attributable is False`, and zero provider calls.
- `tests/contract/test_engine_contracts.py`: pre-provider `before` `RequestInput(...)` short-circuit now asserts zero provider calls, pending-input checkpointing, `runtime_control == "request_input"`, and no finalized `last_route`.
- `tests/contract/test_engine_contracts.py`: `before_verifier` route short-circuit now asserts verifier skipping, producer-only provider activity, and `candidate_route is None`.
- `tests/contract/test_engine_contracts.py`: stale multi-argument `after` / `after_producer` hook tests were migrated to `hook(ctx)` and now read route/event/raw-output data through `ctx.route` and `ctx.outcome`.
- `tests/unit/test_validation.py`: new fail-fast validation coverage rejects multi-argument `after` hooks and multi-argument `after_producer` hooks.

## Preserved Invariants Checked
- Hook short-circuits before any provider candidate exists do not fabricate a `candidate_route`.
- Hook-originated direct controls keep finalized route state unset until a real route finalizes.
- Pair lifecycle short-circuits do not run verifier turns when a hook exits earlier.

## Edge Cases
- `RequestInput(...)` from `before` preserves mutated state and leaves `last_route` unset.
- `before_verifier` route selection finalizes successfully without verifier output.

## Failure Paths
- Invalid legacy multi-argument lifecycle hooks fail during workflow validation rather than at runtime.

## Stabilization
- Tests use `ScriptedLLMProvider` with explicit call-count assertions instead of timing or ordering assumptions outside deterministic workflow history.

## Known Gaps
- Full pytest execution is still blocked in this shell because `pytest` and `pydantic` are unavailable, so this turn validates syntax and stale-signature removal but not runtime execution in-process.
