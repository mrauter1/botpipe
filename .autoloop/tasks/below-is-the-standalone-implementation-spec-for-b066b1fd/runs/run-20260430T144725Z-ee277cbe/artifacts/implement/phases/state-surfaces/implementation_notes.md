# Implementation Notes

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: implement
- Phase ID: state-surfaces
- Phase Directory Key: state-surfaces
- Phase Title: Add Built-In Step State
- Scope: phase-local producer artifact

## Files Changed
- `core/step_state.py`
- `core/validation.py`
- `core/compiler.py`
- `core/engine.py`
- `autoloop/simple.py`
- `autoloop/__init__.py`
- `runtime/static_graph.py`
- `tests/unit/test_simple_surface.py`
- `tests/runtime/test_runtime_static_graph.py`
- `tests/strictness/test_no_compat.py`
- `decisions.txt`

## Symbols Touched
- `StateVar`
- `StepRuntimeState`
- `ProduceVerifyRuntimeState`
- `build_step_state_model(...)`
- `compile_workflow(...)`
- `Engine._ensure_step_state_store(...)`
- `Engine._increment_step_runtime_state(...)`
- `Engine._update_final_step_runtime_state(...)`
- `workflow_topology_payload(...)`

## Checklist Mapping
- `Phase 3 / built-in step state`: completed via shared runtime state models plus engine entry/final-route updates.
- `Phase 3 / produce_verify extra built-ins`: completed via `rework_count` / `replan_count`.
- `Phase 3 / custom step state via Pydantic`: completed by merging custom `BaseModel` state with built-ins.
- `Phase 3 / StateVar sugar`: completed for simple `produce_verify_step(..., state=...)`.
- `Phase 3 / reserved built-in names`: completed in shared validation helper.
- `Phase 3 / persist state in checkpoints`: completed by checkpointing the merged step-state model and removing parallel visit/route bookkeeping.

## Assumptions
- Keeping simple custom `state=` on `produce_verify_step(...)` only is acceptable for this scoped phase; built-in runtime step state still exists on every compiled step.

## Preserved Invariants
- Workflow `State` and `Params` remain Pydantic-based.
- `item_state` and `step_item_state` stay out of scope and remain rejected on the simple prompt surface.
- `core` still does not export `StateVar`; the public export is `autoloop` / `autoloop.simple`.

## Intended Behavior Changes
- Every compiled step now has a model-backed runtime state surface with built-ins.
- `produce_verify_step(..., state={...})` now accepts `StateVar(...)` sugar and rejects reserved-name collisions.
- Built-in step counters checkpoint and restore via `step_states`.
- Topology/static-graph state contracts now always emit step state models/fields.

## Known Non-Changes
- No `item_state` or `step_item_state` authoring/runtime support was added in this phase.
- No history/telemetry work was added in this phase.
- No new simple `state=` parameter was added to `step(...)`, `python_step(...)`, or `workflow_step(...)`.

## Expected Side Effects
- Topology hashes change for workflows because step state models/fields are now always present in compiled metadata.
- Strictness tests no longer treat `StateVar` as a forbidden removed alias on the public simple surface.

## Validation Performed
- `.venv/bin/pytest tests/unit/test_simple_surface.py tests/runtime/test_runtime_static_graph.py tests/strictness/test_no_compat.py -q`
- `.venv/bin/pytest tests/contract/test_engine_contracts.py -q`

## Deduplication / Centralization
- Centralized built-in model construction, `StateVar` sugar parsing, and reserved-name validation in `core/step_state.py` so validation, compilation, runtime, and tests share one contract.
