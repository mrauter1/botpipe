# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: implement
- Phase ID: worklists
- Phase Directory Key: worklists
- Phase Title: Worklists And Scoped Steps
- Scope: phase-local producer artifact

## Files Changed

- `core/worklists.py`
- `core/steps.py`
- `core/validation.py`
- `core/compiler.py`
- `core/context.py`
- `core/artifacts.py`
- `core/engine.py`
- `core/stores/protocols.py`
- `runtime/stores/filesystem.py`
- `core/__init__.py`
- `workflow/__init__.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_compatibility_runtime.py`
- `tests/strictness/test_no_compat.py`

## Symbols Touched

- `WorkItem`, `Selector`, `Selection`, `SelectionSnapshot`, `Worklist`
- `LLMStep(..., scope=...)`, `PairStep(..., scope=...)`
- `WorkflowDefinition.worklists_by_name`
- `CompiledWorkflow.worklists`, `CompiledStep.scope_name`
- `Context.selection(...)`, `Context.current(...)`, `Context.item`
- `resolve_artifact_template(...)` placeholder handling for `item` / `worklist.*`
- `Engine._initialize_worklist_selections(...)`, `_restore_worklist_selections(...)`, `_advance_worklist(...)`
- `CheckpointPayload.worklist_selections`
- `FilesystemCheckpointStore` selection snapshot persistence

## Checklist Mapping

- Plan milestone 7:
  added `core/worklists.py` with item, selector, selection, and artifact-backed/static worklist sources
- Plan milestone 7:
  added scoped-step validation/compilation and context selection helpers
- Plan milestone 7:
  implemented item-aware artifact placeholders and checkpoint selection snapshots
- Plan milestone 6 follow-through:
  worklist-bound route effects now validate against declared worklists and execute after artifact contracts
- Phase AC-13:
  scoped steps resolve the current item deterministically and artifact templates can reference `item.id` / `item.dir_key`
- Phase AC-14:
  `Advance(...)` moves selection state explicitly and resolves exhaustion to declared terminal behavior

## Assumptions

- Additive public-surface widening is justified in this phase because `Worklist`, `Selector`, `WorkItem`, `Continuity`, and the effect types must be authorable from `workflow` once worklist semantics exist.
- Board mutations remain intentionally non-executable beyond validation because the active phase contract excludes extra board semantics.

## Preserved Invariants

- Existing workflows without worklists continue to compile and run unchanged.
- `ctx.open_session(..., scope=...)` and positional scope overrides remain valid and still take precedence over declarative continuity.
- Artifact validation still occurs before route effects execute.
- No hidden automatic full-worklist iteration was introduced; looping happens only when a route explicitly includes `Advance(...)`.

## Intended Behavior Changes

- Worklists can now be declared on workflow classes and referenced from scoped provider steps and typed route effects.
- `Context` now exposes live selection helpers, and artifact templates may reference the active item or named worklist current item.
- Checkpoints now persist worklist selection snapshots so resume restores explicit progression state.
- The root `workflow` shim now exports the now-executable effect types plus worklist primitives and `Continuity`.

## Known Non-Changes

- No child-workflow typed IO work was added in this phase.
- No docs were updated in this phase.
- `BoardMutation` still raises an explicit runtime error if invoked.
- Run metadata (`run.json`) was not expanded with worklist summaries in this phase; checkpoint persistence is the authoritative resume surface for scoped progression.

## Expected Side Effects

- Scoped `Advance(...)` re-enters the same step while items remain and then resolves exhaustion via `if_exhausted`; downstream authors should not expect the enclosing route target to win before exhaustion.
- Work-item session continuity now becomes practically usable because scoped contexts supply `ctx.current(...)` / `ctx.item`.
- Strictness tests now treat effects/worklists as part of the public authoring shim.

## Validation Performed

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp /home/rauter/autoloop_v3_bkp/autoloop_v3/.venv/bin/python -m py_compile core/worklists.py core/steps.py core/validation.py core/compiler.py core/context.py core/artifacts.py core/engine.py core/__init__.py workflow/__init__.py runtime/stores/filesystem.py`
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp /home/rauter/autoloop_v3_bkp/autoloop_v3/.venv/bin/pytest -q tests/unit/test_primitives_and_stores.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py tests/runtime/test_compatibility_runtime.py tests/strictness/test_no_compat.py`
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp /home/rauter/autoloop_v3_bkp/autoloop_v3/.venv/bin/pytest -q tests/runtime/test_package_cli.py tests/runtime/test_workspace_and_context.py`

## Deduplication / Centralization

- Worklist item selection, snapshotting, refresh, and status mutation are centralized in `core/worklists.py`.
- Scoped session continuity now reuses the existing continuity/session-key machinery instead of adding worklist-specific session code in the engine.
- Route-effect execution stays centralized in `Engine._execute_route_effect(...)` with only one worklist advancement path.
