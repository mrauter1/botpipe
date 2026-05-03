# Test Strategy

- Task ID: standalone-remaining-delta-implementation-spec-g-e919a184
- Pair: test
- Phase ID: runtime-correctness-and-telemetry
- Phase Directory Key: runtime-correctness-and-telemetry
- Phase Title: Runtime Correctness And Telemetry
- Scope: phase-local producer artifact

## Coverage map

- AC-1 failure preservation: keep the existing invalid-direct-control checkpoint coverage and add pair-step short-circuit assertions that preserved pending-input ids and source attribution survive producer-only execution.
- AC-2 status and attribution: add explicit checks that `before_producer` and `after_producer` short-circuits preserve `source_hook`, `source_phase`, and provider-attempt flags, and add a workspace-level blocked-route regression test so `blocked` stays distinct from generic `awaiting_input`.
- AC-3 scoped-state/runtime payload clarity: rely on the maintained scoped item-state, checkpoint, static-graph, and worklist-event suites already present in `tests/contract/test_engine_contracts.py`, `tests/runtime/test_runtime_static_graph.py`, and `tests/unit/test_primitives_and_stores.py`.

## Behaviors covered

- Pair-step route short-circuit before any provider turn.
- Pair-step direct control after producer but before verifier.
- Public run metadata and `list_run_records(...)` filtering for blocked routes targeting `AWAIT_INPUT`.

## Preserved invariants checked

- Short-circuit routes from hooks keep `candidate_route=None` when no provider selected a route.
- Direct controls do not fabricate a final route and preserve pending-input identity.
- Producer-only short-circuits report `provider_attempted=True`, `producer_attempted=True`, `verifier_attempted=False`.

## Edge cases and failure paths

- Hidden blocked route remains queryable as `blocked` instead of collapsing into `awaiting_input`.
- Request-input short-circuit from `after_producer` keeps the checkpointed pending-input id and hook attribution.

## Known gaps

- This slice does not add new broad worklist-helper event tests because the existing `tests/unit/test_primitives_and_stores.py` coverage already exercises `worklist_advanced` and `worklist_exhausted` event emission deterministically.

## Flake control

- All added coverage uses `ScriptedLLMProvider`, temporary local workflow packages, and in-process runtime extensions only; no timing, network, or nondeterministic ordering assumptions were introduced.
