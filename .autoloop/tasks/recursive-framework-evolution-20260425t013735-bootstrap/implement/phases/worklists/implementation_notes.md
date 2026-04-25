# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: implement
- Phase ID: worklists
- Phase Directory Key: worklists
- Phase Title: Worklists And Scoped Steps
- Scope: phase-local producer artifact

## Files Changed

- `core/worklists.py`
- `core/validation.py`
- `core/engine.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_validation.py`

## Symbols Touched

- `Worklist.load_items(...)`, `_duplicate_item_ids(...)`
- `WorkflowDefinition.worklists_by_name`, `_validate_route_effects(...)`, `_validate_advance_source_scope(...)`
- `Engine._advance_worklist(...)`
- Worklist regression tests in `tests/unit/test_primitives_and_stores.py` and `tests/unit/test_validation.py`

## Checklist Mapping

- Plan milestone 7:
  tightened worklist item loading so duplicate ids now fail before scoped execution derives selection/session state
- Plan milestone 7:
  tightened scoped-step validation so `Advance(...)` is only valid for the source step's own worklist
- Plan milestone 6 follow-through:
  kept route-effect validation/runtime semantics aligned by adding the same `Advance(...)` scope guard in both places
- Phase AC-13:
  scoped item identity is now deterministic because duplicate worklist ids are rejected at load time
- Phase AC-14:
  `Advance(...)` still moves selection state explicitly, but now only from the scoped step/worklist combination that the phase contract allows

## Assumptions

- Duplicate worklist ids are always invalid because item ids are part of selector lookup, checkpoint restore, mutable status writes, and work-item session continuity.
- `Advance(...)` is meant to drive explicit progression for scoped work only; using it from an unscoped or differently scoped step would be hidden iteration, not a supported control-flow pattern.

## Preserved Invariants

- Existing workflows without worklists continue to compile and run unchanged.
- `ctx.open_session(..., scope=...)` and positional scope overrides remain valid and still take precedence over declarative continuity.
- Artifact validation still occurs before route effects execute.
- Scoped `Advance(...)` keeps its explicit self-loop-until-exhausted behavior; the fix only rejects invalid unscoped or mismatched uses.

## Intended Behavior Changes

- Worklists with duplicate item ids now fail fast on load instead of collapsing silently during selection/restore/status/session operations.
- `Advance(worklist)` now fails validation unless the source step is scoped to that same worklist, and the engine raises if an invalid route slips through runtime assembly.

## Known Non-Changes

- No child-workflow typed IO work was added in this phase.
- No docs were updated in this phase.
- `BoardMutation` still raises an explicit runtime error if invoked.
- Run metadata (`run.json`) was not expanded with worklist summaries in this phase; checkpoint persistence is the authoritative resume surface for scoped progression.

## Expected Side Effects

- Authors now get an explicit failure for duplicate item ids instead of non-deterministic worklist behavior later in the run.
- Authors now get an explicit validation/runtime failure if they try to use `Advance(...)` from an unscoped or differently scoped step.

## Validation Performed

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp /home/rauter/autoloop_v3_bkp/autoloop_v3/.venv/bin/python -m py_compile core/worklists.py core/validation.py core/engine.py tests/unit/test_primitives_and_stores.py tests/unit/test_validation.py`
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp /home/rauter/autoloop_v3_bkp/autoloop_v3/.venv/bin/pytest -q tests/unit/test_primitives_and_stores.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py`

## Deduplication / Centralization

- Worklist identity validation is centralized in `Worklist.load_items(...)` so selection, refresh, restore, mutation, and work-item session continuity all share the same duplicate-id guard.
- The scoped-step requirement for `Advance(...)` is centralized in validation and mirrored by one engine guard, keeping compile-time and runtime behavior aligned without adding a new routing layer.
