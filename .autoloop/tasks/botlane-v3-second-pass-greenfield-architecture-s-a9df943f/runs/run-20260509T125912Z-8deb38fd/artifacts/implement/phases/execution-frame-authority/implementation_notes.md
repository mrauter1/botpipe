# Implementation Notes

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: execution-frame-authority
- Phase Directory Key: execution-frame-authority
- Phase Title: ExecutionFrame Authority
- Scope: phase-local producer artifact

## Files changed

- `botlane/core/context.py`
- `botlane/core/engine.py`
- `botlane/core/worklists.py`
- `botlane/core/branch_groups/context.py`
- `botlane/core/branch_groups/runtime.py`
- `botlane/core/engine_collaborators.py`
- `tests/contract/test_async_step_dispatcher.py`
- `tests/contract/engine/test_execution_services.py`
- `tests/contract/test_provider_turn_plan_adapter.py`
- `tests/runtime/workflow_contract_helpers.py`
- `tests/unit/test_branch_group_context_sessions.py`
- `tests/unit/test_execution_frame_context_parity.py`
- `tests/unit/test_primitives_and_stores.py`

## Symbols touched

- `Context.__getattr__`
- `_legacy_frame_attr(...)`
- `Engine._configure_context_frame(...)`
- `ExecutionFrame.set_*` and worklist cache methods via internal callers
- `_inherit_child_frame_bookkeeping(...)`
- `ProviderContractBuilder.available_routes(...)`

## Checklist mapping

- `execution-frame-authority / AC-1`: public `Context` reads continue to resolve from `ExecutionFrame`, while internal state/session/worklist mutation moved off `Context` and onto `ExecutionFrame`.
- `execution-frame-authority / AC-2`: branch and fan-in child contexts still originate from `ExecutionFrame.child_for_branch(...)` / `child_for_fan_in(...)`, with only child-local resolver/cache setup applied afterward.

## Assumptions

- The two remaining failures in the full `tests/unit/test_branch_group_context_sessions.py` file are still Phase 2 stale assertions, not regressions from this phase.

## Preserved invariants

- Public `Context` properties and methods are unchanged.
- Explicit `message=None` remains distinct from the request-file sentinel.
- Branch/fan-in child contexts preserve shared state-cell semantics, request snapshots, and branch-local session/worklist isolation.

## Intended behavior changes

- Removed `context_runtime(...)` entirely.
- Removed `Context`-level `_set_*` and worklist cache mutator methods so runtime writes happen on `ExecutionFrame` only.
- Branch/worklist/engine internal callers now write state, selections, worklist caches, execution-source metadata, and scoped stores through `ExecutionFrame`.

## Known non-changes

- Legacy underscore reads such as `_values`, `_selections`, `_selection_snapshots`, `_worklist_items_cache`, and `_step_state` still resolve dynamically from `ExecutionFrame`.
- Public `Context` naming and branch evidence schemas are unchanged.

## Expected side effects

- No parallel context-side mutation facade remains.
- Async branch-group execution keeps provider-visible branch routes even when nested branch steps are stored only on their step-plan route cache.

## Deduplication / centralization

- Centralized mutable runtime writes on `ExecutionFrame` instead of splitting them between `Context`, worklist helpers, branch helpers, and former `context_runtime(...)` wrappers.
- Kept event emission and scoped worklist-sync logic on `Context` because they derive payloads from the public facade rather than owning mutable storage.

## Intended out-of-phase change

- `ProviderContractBuilder.available_routes(...)` now falls back to step-plan provider-visible route properties for nested branch steps when `WorkflowPlan.routes` has no direct entry.
- Justification: the execution-frame-authority validation surfaced an async branch-group regression (`legal routes: <none>`) in nested provider steps; fixing the fallback keeps branch runtime behavior stable without changing the public surface or reintroducing adapters.

## Validation performed

- `python3 -m py_compile botlane/core/context.py botlane/core/engine.py botlane/core/worklists.py botlane/core/branch_groups/context.py botlane/core/branch_groups/runtime.py botlane/core/engine_collaborators.py botlane/simple.py tests/contract/test_async_step_dispatcher.py tests/contract/engine/test_execution_services.py tests/contract/test_provider_turn_plan_adapter.py tests/runtime/workflow_contract_helpers.py tests/unit/test_branch_group_context_sessions.py tests/unit/test_execution_frame_context_parity.py tests/unit/test_primitives_and_stores.py`
- `./.venv/bin/python -m pytest -q tests/unit/test_execution_frame_context_parity.py tests/unit/test_primitives_and_stores.py tests/contract/test_provider_turn_plan_adapter.py tests/contract/test_async_step_dispatcher.py tests/contract/engine/test_execution_services.py tests/runtime/test_workspace_and_context.py`
- `./.venv/bin/python -m pytest -q tests/contract/test_async_step_dispatcher.py -k 'finalize_runs_branch_group_inside_event_loop or capture_runs_hooks_and_skips_route_on_taken'`
- `./.venv/bin/python -m pytest -q tests/contract/engine/test_worklists.py -k 'legacy_null_worklist_selection_payloads'`
- `./.venv/bin/python -m pytest -q tests/unit/test_branch_group_context_sessions.py -k 'branch_context_shares_state_cell_values_and_branch_metadata or fan_in_context_exposes_metadata_and_branch_execution_ids or branch_and_fan_in_contexts_preserve_parent_request_snapshot or branch_session_store_view_keeps_activation_local_to_branch or branch_session_store_view_uses_distinct_fresh_keys_per_branch_namespace or branch_session_store_view_snapshot_is_branch_local_only or branch_context_resolves_worklists_locally_without_mutating_parent'`

## Validation notes

- A broad run including all of `tests/unit/test_branch_group_context_sessions.py` still reports two unrelated stale failures from earlier architecture cutover work:
- `StepExecutionResult(finalization=...)`
- dataclass `replace(..., scope_name=...)` on step plans
