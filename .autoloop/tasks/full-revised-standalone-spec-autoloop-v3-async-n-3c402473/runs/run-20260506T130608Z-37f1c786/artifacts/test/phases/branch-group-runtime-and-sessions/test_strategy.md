# Test Strategy

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: test
- Phase ID: branch-group-runtime-and-sessions
- Phase Directory Key: branch-group-runtime-and-sessions
- Phase Title: Branch-group runtime and sessions
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- `AC-1 async provider contract only`
  Covered by `tests/contract/test_branch_group_runtime.py`
  Checks provider-backed branch steps use async execution, support concurrency, and reject sync-only providers at construction/runtime boundaries.

- `AC-2 branch-local fresh sessions`
  Covered by `tests/contract/test_branch_group_runtime.py`
  Checks branch provider requests start with `session_id=None`, provider-returned ids persist into branch manifests, parent session store does not receive branch provider sessions, and fresh keys are unique per branch execution identity.
  Covered by `tests/unit/test_branch_group_context_sessions.py`
  Checks `BranchSessionStoreView` keeps activation local, preserves `session_id=None` for fresh sessions, and allocates distinct fresh keys across branch namespaces.

- `AC-3 evidence rooting and single composite finalization`
  Covered by `tests/contract/test_branch_group_runtime.py`
  Checks `_branch_groups/...` evidence paths, fan-in helper exposure, fan-in checkpoint/resume behavior, evidence-write failure short-circuiting, captured route semantics, and fail-fast cancellation/skipped ordering.
  Covered by `tests/runtime/test_runtime_tracing.py` and `tests/runtime/test_runtime_static_graph.py`
  Checks branch-group observability payloads and additive static-graph metadata remain consistent.

## Preserved invariants checked

- Branch completion order does not affect manifest order.
- Branch `Goto`, `Fail`, and `RequestInput` remain captured rather than followed directly.
- Branch `on_taken` hooks stay disabled in capture mode.
- Shared state/value mutation semantics remain unchanged inside branch groups.

## Edge cases and failure paths

- `concurrency=1` still uses branch-group semantics.
- `settle="fail_fast"` cancels in-flight branches and marks unscheduled branches as skipped.
- Missing provider-returned session ids leave manifest provider-session fields empty.
- Evidence write failures block fan-in/mechanical outcome progression.

## Stabilization notes

- New fresh-key assertions are deterministic because they inspect branch namespace prefixes and inequality rather than call ordering.
- Existing concurrency tests rely on explicit sleeps only for overlap/cancellation proof; session-key assertions avoid timing dependence.

## Known gaps

- Out-of-phase provider transport cancellation behavior remains covered elsewhere and is not expanded here.
