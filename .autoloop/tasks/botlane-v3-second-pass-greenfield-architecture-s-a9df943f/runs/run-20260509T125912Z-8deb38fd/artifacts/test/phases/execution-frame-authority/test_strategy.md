# Test Strategy

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: test
- Phase ID: execution-frame-authority
- Phase Directory Key: execution-frame-authority
- Phase Title: ExecutionFrame Authority
- Scope: phase-local producer artifact

## Behavior to coverage map

- Helper removal from `botlane.core.context`
  - `tests/unit/test_execution_frame_context_parity.py::test_context_module_has_no_weakref_runtime_sidecar`
  - Covers absence of `_CONTEXT_RUNTIMES`, `_ContextRuntime`, and `context_runtime`.

- Public `Context` facade stays non-mutating while reading from `ExecutionFrame`
  - `tests/unit/test_execution_frame_context_parity.py::test_context_frame_mutators_update_execution_frame_and_legacy_fields`
  - `tests/unit/test_primitives_and_stores.py::test_public_context_hides_runtime_mutators`
  - Covers frame-backed reads, preserved underscore compatibility reads, and hidden mutator/cache helper names.

- Worklist/session/state mutation moves onto frame-backed paths
  - `tests/unit/test_execution_frame_context_parity.py::test_worklist_runtime_mutators_keep_frame_and_public_selection_in_sync`
  - `tests/unit/test_primitives_and_stores.py`
  - Covers selection writes, active-worklist updates, cache behavior, and preserved public worklist accessors.

- Branch/fan-in child contexts originate from `ExecutionFrame.child_for_branch(...)` / `child_for_fan_in(...)`
  - `tests/unit/test_execution_frame_context_parity.py::test_branch_child_context_uses_child_frame_and_preserves_shared_state`
  - `tests/unit/test_execution_frame_context_parity.py::test_fan_in_child_context_exposes_fan_in_frame_metadata`
  - `tests/unit/test_branch_group_context_sessions.py`
  - Covers child frame state-cell sharing, copied selection snapshots, child-local resolver/cache objects, preserved request snapshots, and branch/fan-in metadata access.

- Nested branch/provider execution remains valid after frame-authority cutover
  - `tests/contract/test_async_step_dispatcher.py::test_step_dispatcher_execute_async_finalize_runs_branch_group_inside_event_loop`
  - Covers the nested branch-step route-visibility fallback when branch steps are absent from `WorkflowPlan.routes`, plus async branch-group execution success.

## Preserved invariants checked

- Explicit `message=None` remains distinct from the default request-file sentinel.
- Legacy underscore reads still resolve from `ExecutionFrame`.
- Branch/fan-in child contexts keep shared mutable state via `StateCell` and preserve parent request/message/input snapshots.

## Edge cases and failure paths

- Public `Context` object does not expose runtime mutator/cache helper names.
- Child branch contexts do not reuse parent selection snapshot/cache objects.
- Async branch-group dispatch still succeeds when provider-visible routes come only from the nested step plan.

## Stabilization approach

- Tests use `InMemorySessionStore` and local temp paths only.
- Async coverage uses an in-process fake provider with deterministic route outputs.
- No timing, network, or nondeterministic ordering assumptions are introduced.

## Known gaps

- The broader `tests/unit/test_branch_group_context_sessions.py` file still contains two unrelated stale assertions from earlier architecture work; they are intentionally excluded from this phase-local validation slice.
