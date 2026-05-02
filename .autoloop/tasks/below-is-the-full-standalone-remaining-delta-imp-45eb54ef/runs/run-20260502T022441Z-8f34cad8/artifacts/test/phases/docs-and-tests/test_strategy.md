# Test Strategy

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: test
- Phase ID: docs-and-tests
- Phase Directory Key: docs-and-tests
- Phase Title: Docs And Tests
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- Final hook docs and direct-control docs: `tests/test_architecture_baseline_docs.py`
  - Asserts `hook(ctx)` examples only, final hook return set (`None`, route tag, `Event`, `RequestInput`, `Goto`, `Fail`), canonical `python_step(ctx)` examples, and worklist-helper guidance.
- Removed-surface validation: `tests/unit/test_simple_surface.py`, `tests/unit/test_validation.py`, `tests/contract/test_engine_contracts.py`
  - Asserts fail-fast rejection of removed `on_route`/legacy route keywords and helper-based scoped-route declarations.
- Hook short-circuiting and direct controls: `tests/contract/test_engine_contracts.py`
  - Covers `before_producer`, `before_verifier`, `RequestInput`, `Goto`, `Fail`, pending-input checkpointing, and provider-attempt attribution.
- Worklist helpers and preserved invariants: `tests/unit/test_primitives_and_stores.py`, `tests/contract/test_engine_contracts.py`
  - Covers `advance_or(...)`, `validation_error()`, runtime-event attribution, and explicit helper-driven progression via `on_taken`.
- Trace/history/static-graph alignment: `tests/runtime/test_history.py`, `tests/runtime/test_runtime_tracing.py`, `tests/runtime/test_runtime_static_graph.py`
  - Covers `on_taken` as the live route-local hook phase, hook-route redirects, runtime-control trace fields, and absence of step-level `on_route`.
- Optimizer/status normalization adjacency: `tests/unit/test_optimization_helpers.py`
  - Covers `"question"` route vs `AWAIT_INPUT` terminal normalization.

## Preserved invariants checked
- Step-level `on_route` stays removed while route-local `on_taken` remains documented and traced.
- Worklist helpers mutate selection/status and do not auto-route except through explicit hook returns.
- Direct runtime controls preserve distinct trace/history fields rather than being normalized into routes.

## Edge cases and failure paths
- Doc regression guard for removed `(state, ctx)` `python_step` examples and `Advance(...)` route-effect guidance.
- Invalid or removed route-hook keywords remain explicit failures.
- Pending-input and direct-control paths keep `source_phase`/`pending_input_id` stable in traces and checkpoints.

## Flake risk and stabilization
- Coverage is deterministic: no network, no timing assertions, and only local filesystem/trace fixtures.
- Validation uses narrow targeted pytest invocations so failures stay attributable to this phase.

## Known gaps
- No new runtime code paths were introduced in this phase; test work is intentionally limited to doc-regression tightening and revalidation of existing runtime coverage.
