# Implementation Notes

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: execution-frame-context-migration
- Phase Directory Key: execution-frame-context-migration
- Phase Title: ExecutionFrame Behind Context
- Scope: phase-local producer artifact

## Files Changed

- `botlane/core/execution_frame.py`
- `botlane/core/context.py`
- `botlane/core/branch_groups/context.py`
- `tests/unit/test_execution_frame_context_parity.py`

## Symbols Touched

- `ExecutionFrame`
- `_DEFAULT_FRAME_MESSAGE`
- `Context`
- `_ContextRuntime`
- `create_branch_context(...)`
- `create_fan_in_context(...)`
- `_create_child_context(...)`

## Checklist Mapping

- Phase objective `Add botlane/core/execution_frame.py`: completed.
- Phase objective `Synthesize ExecutionFrame inside Context and mirror legacy private-field behavior`: completed.
- Phase objective `Add context/frame parity coverage, including message sentinel, worklists, branch metadata, and fan-in metadata`: completed via `tests/unit/test_execution_frame_context_parity.py`.
- Out-of-scope `Remove WeakKeyDictionary sidecar state`: intentionally not changed.
- Out-of-scope `Change Context constructor signatures`: intentionally not changed.

## Assumptions

- Existing direct writes to mutable `Context` runtime state continue to flow through `context_runtime(...)`, `Context.state`, or child-context constructors; legacy private attributes are still mirrored for read compatibility.
- Child branch/fan-in contexts should keep sharing the parent state cell and values mapping, but selection snapshots should remain child-local copies.

## Preserved Invariants

- Public `Context` constructor and public facade remain unchanged.
- `_DEFAULT_MESSAGE` sentinel identity remains stable for engine/runner callers by aliasing it to the frame sentinel.
- `_CONTEXT_RUNTIMES` and worklist runtime sidecar behavior remain in place.
- Branch/fan-in child contexts still preserve request snapshot, shared state cell, and parent runtime bookkeeping semantics.

## Intended Behavior Changes

- Internal only: mutable runtime state is now also represented by `Context._execution_frame`, and `_ContextRuntime` writes update the frame first before mirroring legacy fields.

## Known Non-Changes

- No `ExecutionServices` work.
- No workflow-plan or engine ownership migration.
- No placeholder, branch-manifest, or provider-turn behavior changes.
- No public export changes.

## Expected Side Effects

- Internal code can now inspect `Context._execution_frame` for run-scoped mutable state.
- Child branch/fan-in context construction now derives from frame child copies, reducing duplication for the migrated fields.

## Deduplication / Centralization

- Centralized child-context field cloning in `ExecutionFrame.child_for_step(...)` / `child_for_branch(...)` / `child_for_fan_in(...)` instead of repeating the mutable field bundle in branch-context helpers.
- Centralized frame-to-legacy mirroring in `Context._sync_legacy_fields_from_execution_frame(...)`.

## Validation Performed

- `./.venv/bin/python -m pytest tests/unit/test_execution_frame_context_parity.py`
- `./.venv/bin/python -m pytest tests/unit/test_branch_group_context_sessions.py`
- `./.venv/bin/python -m pytest tests/unit/test_run_paths.py`
- `./.venv/bin/python -m pytest tests/runtime/test_workspace_and_context.py`
- `./.venv/bin/python -m pytest tests/unit/test_simple_surface.py`
- `./.venv/bin/python -m pytest tests/unit/test_sdk_facade.py`
- `./.venv/bin/python -m pytest tests/contract/engine/test_prompt_context.py`
- `./.venv/bin/python -m pytest tests/contract/engine/test_worklists.py`
- `./.venv/bin/python -m pytest tests/contract/test_branch_group_runtime.py`
- `./.venv/bin/python -m pytest tests/unit/test_primitives_and_stores.py`
- `./.venv/bin/python -m pytest tests/strictness/test_no_compat.py`
- `./.venv/bin/python -m pytest tests/strictness/test_core_runtime_boundary.py`
