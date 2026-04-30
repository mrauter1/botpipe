# Implementation Notes

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: implement
- Phase ID: scoped-item-state
- Phase Directory Key: scoped-item-state
- Phase Title: Implement Scoped Item State
- Scope: phase-local producer artifact

## Files changed

- `autoloop/simple.py`
- `tests/unit/test_simple_surface.py`
- `core/worklists.py`
- `core/steps.py`
- `core/compiler.py`
- `core/engine.py`
- `core/context.py`
- `core/validation.py`
- `core/step_state.py`
- `tests/contract/test_engine_contracts.py`
- `.../decisions.txt`

## Symbols touched

- `StepDeclaration.item_state`
- `step(..., item_state=...)`
- `Worklist.from_param`
- `Worklist.item_state_model`
- `Step.item_state`
- `CompiledStep.step_item_state_model`
- `CompiledStep.step_item_state_fields`
- `build_step_item_state_model`
- `_normalize_simple_item_state_model`
- `_known_worklist_item_state_fields`
- `_known_simple_step_item_state_fields`
- `_validate_simple_prompt_reference`
- `Engine._ensure_item_state_store`
- `Engine._ensure_step_item_state_store`
- `Engine._serialize_item_states`
- `Engine._serialize_step_item_states`

## Checklist mapping

- Plan milestone 4 / AC-1:
  Added worklist `item_state` authoring, simple scoped step `item_state` authoring on both `step(...)` and `produce_verify_step(...)`, model-backed runtime stores, per-item built-in counter updates, checkpoint serialization, and resume restoration.
- Plan milestone 4 / AC-2:
  Added simple-surface `scope=` passthrough plus prompt placeholder validation for `{item.state.*}` and `{step_name.item_state.*}` against declared Pydantic fields, with regression coverage on both scoped `step(...)` and scoped `produce_verify_step(...)` item-state models.

## Assumptions

- `Worklist.from_param(...)` reads from `workflow_params[param_name or name]` and expects a sequence of items.
- Worklist item state remains opt-in; undeclared worklists do not materialize persisted `item_states`.

## Preserved invariants

- Aggregate `ctx.step_state` behavior and built-in step runtime state remain unchanged.
- Scoped steps still key execution flow by worklist selection/current item.
- Unscoped steps still do not expose `ctx.item_state` or `ctx.step_item_state`.

## Intended behavior changes

- Scoped steps now always get model-backed `ctx.step_item_state` with built-in runtime fields, and custom per-item fields when declared.
- Worklists can declare shared per-item state via `item_state=BaseModel`.
- Simple scoped `step(...)` now accepts `item_state=...` authoring instead of limiting custom per-item step state to `produce_verify_step(...)`.
- Simple prompt validation now accepts model-backed `item.state.*` and `step.item_state.*` references instead of rejecting them categorically.

## Known non-changes

- No history/telemetry APIs were added in this phase.
- No effective-required-write rendering changes were made in this phase.
- `workflow_step(...)` and `python_step(...)` simple authoring were not expanded with scoped item-state authoring beyond existing scope rules.

## Expected side effects

- Topology hashes now change when scoped item-state/worklist item-state metadata changes.
- Checkpoints now serialize scoped item state and step-item state with `model_dump(mode="json")` when those stores are model-backed.

## Validation performed

- `python3 -m py_compile autoloop/simple.py core/step_state.py core/worklists.py core/steps.py core/compiler.py core/context.py core/engine.py core/validation.py tests/unit/test_simple_surface.py tests/contract/test_engine_contracts.py`
- `python3 -m py_compile autoloop/simple.py tests/unit/test_simple_surface.py`
- Full `pytest` execution was not possible in this shell because `pytest` is not installed and the default `python3` environment also lacks runtime dependencies such as `pydantic`.

## Deduplication / centralization

- Reused the existing step-state builder rules by adding `build_step_item_state_model(...)` instead of introducing a second item-state-specific validation path.
- Reused the same simple-surface lowering path for scoped `step(...)` and `produce_verify_step(...)` item-state declarations rather than creating a separate prompt-step-only implementation.
- Reused existing checkpoint/hook rollback stores by materializing model-backed scoped state inside the engine rather than adding a parallel persistence subsystem.
