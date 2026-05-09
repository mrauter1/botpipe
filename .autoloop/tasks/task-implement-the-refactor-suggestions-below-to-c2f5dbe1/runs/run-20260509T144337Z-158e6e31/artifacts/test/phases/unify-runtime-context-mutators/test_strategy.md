# Test Strategy

- Task ID: task-implement-the-refactor-suggestions-below-to-c2f5dbe1
- Pair: test
- Phase ID: unify-runtime-context-mutators
- Phase Directory Key: unify-runtime-context-mutators
- Phase Title: Unify Runtime Context Mutators
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- `Context` private mutator facade:
  - Cover `_set_values`, `_set_route`, `_set_event`, `_set_outcome`, `_set_meta`, `_set_step_state`, `_set_item_state`, `_set_step_item_state`, and `_set_state` updating both `ExecutionFrame` storage and legacy underscore/public accessors.
  - Preserve the by-reference `values` identity expected by parent/child runtime contexts.
- Shared selection mutator path:
  - Cover `Context._set_worklist_selection(...)` clearing only the touched snapshot entry and invoking the configured scoped-state sync callback with the mutated worklist name.
- Branch-child lazy selection restore:
  - Cover `create_branch_context(...).ensure_selection(...)` using the child-local resolver plus the same selection mutator path, clearing only the child snapshot entry, leaving parent snapshots untouched, and invoking child sync callbacks.

## Preserved invariants checked

- `ExecutionFrame` remains the storage primitive while `Context` becomes the executable mutator surface.
- Parent and branch child contexts still share state/value cells where expected.
- Selection state remains child-local while request snapshots and untouched parent selection snapshots remain stable.

## Edge cases / failure paths

- Edge case: only the mutated worklist snapshot is invalidated when multiple snapshot entries exist.
- Edge case: child lazy selection restore does not populate or mutate parent selections.
- Failure-path coverage intentionally left to existing runtime/contract suites; no new regression expectation was added that normalizes changed behavior.

## Flake risk / stabilization

- Added tests use in-memory contexts and `Worklist.from_items(...)`; no timing, filesystem race, network, or ordering dependencies.

## Known gaps

- Fresh acceptance-batch reruns are currently blocked by an unrelated dirty-file syntax error in `botlane/core/branch_groups/outcomes.py`.
- No new tests were added in higher-level acceptance suites because the low-level parity seam validates the new mutator contract directly while broader imports remain blocked by unrelated workspace noise.
