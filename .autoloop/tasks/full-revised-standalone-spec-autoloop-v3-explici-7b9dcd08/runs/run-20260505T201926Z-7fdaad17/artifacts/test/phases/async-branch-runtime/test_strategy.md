# Test Strategy

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: test
- Phase ID: async-branch-runtime
- Phase Directory Key: async-branch-runtime
- Phase Title: Async Branch Runtime
- Scope: phase-local producer artifact

## Behavior Coverage Map

- AC-1 thread-free async scheduler:
  - `tests/strictness/test_no_compat.py` scans the branch-group subsystem for forbidden thread-backed primitives.
- AC-2 provider-backed concurrency:
  - `tests/contract/test_branch_group_runtime.py` covers concurrent `parallel(...)` and `fan_out(...)` execution with the async fake provider and asserts overlapping in-flight execution.
- AC-3 fail-fast cancellation and manifest stability:
  - `tests/contract/test_branch_group_runtime.py` covers lazy launch, in-flight cancellation, skipped tail branches, and declaration-order manifest results.
  - `tests/runtime/test_runtime_tracing.py` covers the emitted `branch_failed`, `branch_cancelled`, `branch_skipped`, and composite completion events for the same fail-fast shape.
- AC-4 runtime tracing and evidence paths:
  - `tests/runtime/test_runtime_tracing.py` asserts the required branch-group event set and workflow-folder-relative evidence paths.
  - `tests/contract/test_branch_group_runtime.py` covers fan-in helper reads and ordinary downstream `_branch_groups/...` reads resolving to workflow-folder evidence.

## Preserved Invariants Checked

- Branch route capture still does not follow branch destinations and still skips route `on_taken` hooks.
- Shared state, shared values, and overlapping workspace writes remain allowed and observable.
- Evidence write failures still stop before fan-in or mechanical outcome routing.

## Edge Cases / Failure Paths

- Sync-only providers still fail for provider-backed branch groups.
- `concurrency=1` still goes through branch-group semantics while staying async-provider-safe.
- Downstream non-fan-in reads of `_branch_groups/...` stay readable after the workflow-folder evidence-root migration.

## Flake Control

- Concurrency tests use scripted async delays plus provider-side active-count tracking instead of timing thresholds alone.
- Fail-fast tests assert statuses and manifest ordering rather than cancellation timing details.

## Known Gaps

- This phase does not add coverage for deferred branch-session overlay changes or synthetic session-id removal because those behaviors remain out of scope.
