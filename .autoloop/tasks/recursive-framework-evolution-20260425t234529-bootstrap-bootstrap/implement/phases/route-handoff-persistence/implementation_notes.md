# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-bootstrap
- Pair: implement
- Phase ID: route-handoff-persistence
- Phase Directory Key: route-handoff-persistence
- Phase Title: Route Handoff Delivery
- Scope: phase-local producer artifact

## Files changed
- `core/effects.py`
- `core/stores/protocols.py`
- `core/primitives.py`
- `core/__init__.py`
- `workflow/__init__.py`
- `core/validation.py`
- `core/engine.py`
- `runtime/stores/filesystem.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_validation.py`
- `tests/runtime/test_compatibility_runtime.py`
- `tests/contract/test_engine_contracts.py`

## Symbols touched
- `Handoff`
- `Event.handoff`
- `PendingHandoff`
- `CheckpointPayload.pending_handoffs`
- `Engine._execute_step`
- `Engine._execute_pair_step`
- `Engine._execute_llm_step`
- `Engine._run_pair_step`
- `Engine._run_llm_step`
- `Engine._request_control_contract`
- `Engine._matching_pending_handoffs`
- `Engine._schedule_route_handoffs`
- `FilesystemCheckpointStore.save/load`

## Checklist mapping
- Phase deliverable: effect, primitive, compiler/validation surface updates for handoffs.
  Implemented via `Handoff`, `Event.handoff`, workflow/core shim exports, and validation for static handoff-to-`SystemStep` rejection.
- Phase deliverable: pending handoff persistence in checkpoints and stores.
  Implemented via `PendingHandoff`, additive checkpoint schema, in-memory roundtrip coverage, and filesystem serialization/deserialization.
- Phase deliverable: engine delivery, scoping, consumption, and resume behavior.
  Implemented via engine-side pending handoff matching, target-step scheduling, worklist/item scoping, local retry reuse, and resume preservation before first successful provider dispatch.
- Phase deliverable: handoff-focused tests.
  Added primitive/store, validation, filesystem checkpoint, and engine contract coverage.

## Assumptions
- Dynamic `Event.handoff` aimed at terminal or `SystemStep` destinations is dropped at runtime instead of raising, while static `Handoff(...)` routes to `SystemStep` are rejected during validation.
- Worklist scoping is keyed from the resolved target step after route effects mutate selection state, so handoffs follow the next active item when the route changes scope position before dispatch.

## Preserved invariants
- No `max_chars` field was added to `Handoff` or `Event`.
- Handoffs are not rendered into unrelated steps and are not delivered to terminal destinations.
- Provider retries still reuse local step context without persisting rejected attempt state back into checkpointed handoff queues.
- Existing public workflow shims remain strict and do not expose engine/compiler internals.

## Intended behavior changes
- Workflow authors can declare static route handoffs with `Handoff(...)` and dynamic route handoffs with `Event(..., handoff=...)`.
- Checkpoints now persist pending handoffs additively and restore them across resume.
- Provider-facing requests receive route handoff text only when the resolved target step and worklist/item scope match.

## Known non-changes
- No prompt-budget controls were added beyond the existing renderer policy.
- `SystemStep` handoff consumption was not introduced.
- Provider raw-output telemetry behavior was not changed in this phase.

## Expected side effects
- Existing checkpoints without `pending_handoffs` continue to load with an empty tuple.
- Static handoffs targeting a `SystemStep` now fail validation with a deterministic error.

## Validation performed
- `.venv/bin/pytest -q tests/unit/test_primitives_and_stores.py`
- `.venv/bin/pytest -q tests/unit/test_validation.py`
- `.venv/bin/pytest -q tests/contract/test_engine_contracts.py`
- `.venv/bin/pytest -q tests/runtime/test_compatibility_runtime.py`
- `.venv/bin/pytest -q tests/runtime/test_runtime_providers.py`
- `.venv/bin/pytest -q tests/runtime/test_provider_backends.py`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`

## Deduplication / centralization
- Handoff persistence stays centralized in the engine and checkpoint stores; no provider/runtime transport code was made handoff-aware.
- Static and dynamic handoff message combination is centralized in `Engine._schedule_route_handoffs` so pair/llm/system paths use the same resolution rule.
