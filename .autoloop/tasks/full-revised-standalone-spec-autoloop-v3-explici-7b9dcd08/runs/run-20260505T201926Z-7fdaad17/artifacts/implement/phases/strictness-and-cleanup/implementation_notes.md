# Implementation Notes

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: implement
- Phase ID: strictness-and-cleanup
- Phase Directory Key: strictness-and-cleanup
- Phase Title: Strictness and Cleanup
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/branch_groups/manifest.py`
- `tests/strictness/test_no_compat.py`
- `tests/contract/test_branch_group_runtime.py`
- `.../decisions.txt`

## Symbols touched
- `render_branch_group_context`
- `test_branch_group_subsystem_does_not_reintroduce_forbidden_thread_backed_primitives`
- `test_parallel_branch_group_captures_fail_runtime_control_as_failed`

## Checklist mapping
- Plan milestone 6 / AC-1: expanded forbidden-primitive scan to include the async one-step execution surface used by branch groups.
- Plan milestone 6 / AC-2: added runtime regression coverage for branch `Fail` capture and fixed the context markdown ordering mismatch exposed by the contract suite.
- Plan milestone 6 / AC-3: no sync-provider or sequential-provider compatibility path was added; validation stayed on the async-native path.

## Assumptions
- `engine_collaborators.py` is part of the branch-group execution path for strictness purposes because branch tasks and fan-in both dispatch through `execute_async(..., route_mode="capture")`.

## Preserved invariants
- Branch-group evidence remains rooted under `{workflow_folder}/_branch_groups/...`.
- Fan-in and mechanical outcome behavior are unchanged apart from evidence document ordering.
- Sync top-level callers still use the existing outer sync bridge; no branch-group internals were reworked toward sync compatibility.

## Intended behavior changes
- Failure detail lines in `context.md` now appear within the failure section before the needs-input and cancellation sections.

## Known non-changes
- No branch-group runtime scheduling logic, session overlay logic, or compile-time validation rules changed in this phase turn.
- No reviewer-owned `criteria.md` content was edited.

## Expected side effects
- Strictness will now fail if forbidden thread/fake-async helpers reappear in `engine_collaborators.py`, not just under `autoloop/core/branch_groups/`.
- The branch-group contract suite now explicitly pins `Fail` runtime-control capture semantics.

## Validation performed
- `./.venv/bin/python -m pytest -q tests/strictness/test_no_compat.py tests/unit/test_simple_surface.py tests/unit/test_branch_group_context_sessions.py tests/contract/test_async_step_dispatcher.py tests/contract/test_branch_group_runtime.py tests/runtime/test_runtime_tracing.py tests/runtime/test_runtime_static_graph.py`
- `./.venv/bin/python -m pytest -q tests/unit/test_validation.py`

## Deduplication / centralization decisions
- Reused the existing strictness scan test by broadening its scan roots instead of adding a second branch-group strictness test with duplicate forbidden-token logic.
