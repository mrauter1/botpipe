# Test Strategy

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: test
- Phase ID: branch-group-runtime-regression-coverage
- Phase Directory Key: branch-group-runtime-regression-coverage
- Phase Title: Add Missing Branch-Group Runtime Contracts
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map
- Shared branch effects
  Covered by `test_parallel_branch_group_runtime_preserves_shared_state_values_and_overlapping_writes`.
  Asserts real `Engine.run()` branch execution preserves parent-visible `ctx.state` replacement, parent-visible `ctx.values` mutation after settlement, permissive same-path workspace writes, and expected `reviews -> publish` routing history.
- Authored fan-in pending input
  Covered by `test_parallel_branch_group_fan_in_request_input_checkpoints_at_composite_boundary_and_resumes`.
  Asserts authored fan-in `RequestInput` pauses at `AWAIT_INPUT`, checkpoints with `checkpoint.stage == "reviews"`, resumes through `Engine.resume(...)`, and reaches downstream completion with expected `reviews -> publish` history.

## Preserved Invariants Checked
- Coverage stays in `tests/contract/test_branch_group_runtime.py` and exercises the real runtime path rather than helper-only branch-context construction.
- Composite-boundary checkpointing remains the pinned resume contract for authored fan-in input.
- No new merge or conflict-resolution semantics are asserted for overlapping writes.

## Edge Cases And Failure Paths
- Same-path overlapping writes are stabilized with `concurrency=1` so the final file assertion is deterministic without depending on thread scheduling.
- Existing adjacent coverage in the same file continues to own fail-fast settlement, evidence-write failure, and branch-question behavior; this slice adds only the missing shared-effect and fan-in pending-input contracts.

## Validation
- `./.venv/bin/python -m pytest tests/contract/test_branch_group_runtime.py`

## Known Gaps
- Does not assert concurrent last-writer-wins behavior for overlapping writes; the request only requires non-rejection.
- Does not assert replay suppression for resumed branch groups; the request only requires composite-boundary checkpointing and downstream completion after resume.
