# Implementation Notes

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: execution-frame-authority
- Phase Directory Key: execution-frame-authority
- Phase Title: ExecutionFrame Authority
- Scope: phase-local producer artifact

## Files changed

- `botlane/core/context.py`
- `botlane/core/branch_groups/context.py`
- `tests/unit/test_execution_frame_context_parity.py`

## Symbols touched

- `Context.__getattr__`
- `_legacy_frame_attr(...)`
- `_ContextRuntime`
- `context_runtime(...)`
- `_inherit_child_runtime_bookkeeping(...)`

## Checklist mapping

- `execution-frame-authority / AC-1`: `Context` public properties still read from `ExecutionFrame`; legacy underscore access now resolves dynamically into frame state instead of mirrored fields.
- `execution-frame-authority / AC-2`: branch and fan-in child context creation continues through `ExecutionFrame.child_for_branch(...)` / `child_for_fan_in(...)`, with child-local bookkeeping layered on top of the child frame.

## Assumptions

- Existing internal callers may keep using `context_runtime(...)` and underscore aliases during later phases; removing those call sites is out of scope for this phase.

## Preserved invariants

- Public `Context` API surface is unchanged.
- Default request-message sentinel vs explicit `message=None` behavior is unchanged.
- Branch/fan-in request snapshot, state-cell sharing, and worklist snapshot isolation stay unchanged.

## Intended behavior changes

- Removed the `WeakKeyDictionary` context sidecar and `_sync_legacy_fields_from_execution_frame(...)`.
- `context_runtime(...)` now mutates only `ExecutionFrame` state.
- Legacy underscore reads such as `_values`, `_selections`, `_selection_snapshots`, and `_worklist_items_cache` now resolve directly from `ExecutionFrame` instead of mirrored `Context` fields.

## Known non-changes

- `context_runtime(...)` remains available as an internal facade.
- No public `Context` method/property names changed.
- No branch-runtime or provider-runtime behavior outside frame authority was intentionally changed.

## Expected side effects

- Eliminates frame/context drift caused by mirrored private fields.
- Child branch/fan-in contexts now inherit selection snapshots from the child frame and keep their worklist cache local to that frame.

## Validation performed

- `python3 -m py_compile botlane/core/context.py botlane/core/execution_frame.py botlane/core/branch_groups/context.py`
- `./.venv/bin/python -m pytest -q tests/unit/test_execution_frame_context_parity.py tests/unit/test_primitives_and_stores.py tests/unit/test_branch_group_context_sessions.py -k 'branch_context_shares_state_cell_values_and_branch_metadata or fan_in_context_exposes_metadata_and_branch_execution_ids or branch_and_fan_in_contexts_preserve_parent_request_snapshot or branch_session_store_view_keeps_activation_local_to_branch or branch_session_store_view_uses_distinct_fresh_keys_per_branch_namespace or branch_session_store_view_snapshot_is_branch_local_only or branch_context_resolves_worklists_locally_without_mutating_parent'`
- `./.venv/bin/python -m pytest -q tests/contract/engine/test_worklists.py -k 'legacy_null_worklist_selection_payloads'`
- `./.venv/bin/python -m pytest -q tests/runtime/test_workspace_and_context.py`

## Validation notes

- A broader run of `tests/unit/test_branch_group_context_sessions.py` still reports two unrelated pre-existing failures that assert removed Phase 2 internals (`StepExecutionResult(finalization=...)` and dataclass `scope_name` replacement on step plans). Those assertions were left untouched in this phase-local slice.
