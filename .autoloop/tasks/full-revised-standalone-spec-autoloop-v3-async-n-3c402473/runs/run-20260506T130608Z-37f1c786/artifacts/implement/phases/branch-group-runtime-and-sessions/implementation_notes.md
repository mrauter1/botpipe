# Implementation Notes

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: implement
- Phase ID: branch-group-runtime-and-sessions
- Phase Directory Key: branch-group-runtime-and-sessions
- Phase Title: Branch-group runtime and sessions
- Scope: phase-local producer artifact

## Files changed
- `.autoloop/tasks/full-revised-standalone-spec-autoloop-v3-async-n-3c402473/runs/run-20260506T130608Z-37f1c786/decisions.txt`
- `.autoloop/tasks/full-revised-standalone-spec-autoloop-v3-async-n-3c402473/runs/run-20260506T130608Z-37f1c786/artifacts/implement/phases/branch-group-runtime-and-sessions/implementation_notes.md`

## Symbols touched
- No runtime code changes in this turn.

## Checklist mapping
- `M4. Branch-group runtime and session refactor`: verified current `autoloop/core/branch_groups/runtime.py`, `context.py`, and `sessions.py` satisfy the scoped acceptance criteria.
- `M6. Test and strictness hardening`: ran focused branch-group/runtime/session suites relevant to this phase; did not change provider transport code because the only observed failure is out of phase.

## Assumptions
- The branch-group runtime/session implementation already landed earlier in the run and this phase turn is allowed to close out with validation-only notes when no further code delta is justified.

## Preserved invariants
- Provider-backed branch execution still goes through async `StepDispatcher.execute_async(..., route_mode="capture")` without provider async-capability probing in branch runtime.
- Fresh branch sessions remain branch-local, start with `session_id=None`, do not activate parent session slots, and only persist provider-returned session ids into branch results.
- Branch evidence remains rooted under `{workflow_folder}/_branch_groups/...`, and fan-in still resolves through a single composite finalization path.

## Intended behavior changes
- None in this turn.

## Known non-changes
- Did not edit `autoloop/core/branch_groups/*`, `autoloop/core/context.py`, `autoloop/core/engine_collaborators.py`, or related tests because the phase-local contract already passes.
- Did not address the unrelated provider transport cancellation regression in `tests/runtime/test_runtime_providers.py`; that belongs to the transport/provider phase rather than branch-group runtime/session scope.

## Expected side effects
- None beyond updated phase documentation and decision ledger entries.

## Validation performed
- `./.venv/bin/pytest -q tests/contract/test_branch_group_runtime.py tests/runtime/test_runtime_tracing.py tests/runtime/test_runtime_static_graph.py tests/unit/test_simple_surface.py tests/unit/test_primitives_and_stores.py`
- `./.venv/bin/pytest -q tests/unit/test_branch_group_context_sessions.py`
- `./.venv/bin/pytest -q tests/strictness/test_no_compat.py tests/unit/test_provider_boundary_core.py tests/runtime/test_runtime_providers.py`
  Result: one out-of-phase failure remains in `tests/runtime/test_runtime_providers.py::test_communicate_text_subprocess_terminates_then_kills_on_cancellation` (`wait_calls == 2`, expected `1`).

## Deduplication / centralization decisions
- Chose not to make speculative runtime/session edits without a failing phase-local signal, to avoid redundant churn in already-green branch-group internals.
