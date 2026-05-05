# Gap Report

## Original intent considered
- The immutable request requires committed runtime/contract coverage for three shared-effect behaviors under real branch execution: branch `ctx.state` assignment reaches the shared parent state cell, branch `ctx.values` mutation remains visible after settlement, and overlapping writes to the same workspace path are not rejected.
- The immutable request also requires committed runtime/contract coverage for an authored fan-in `RequestInput` path: checkpoint at the composite branch-group boundary, then resume normally and reach downstream completion.
- The request allows a minimal fix only in the branch-group runtime/checkpoint path if the new tests fail.

## Clarifications / superseding decisions
- The run decisions constrain the work to a narrow slice centered on `tests/contract/test_branch_group_runtime.py`, with runtime edits limited to `autoloop/core/branch_groups/runtime.py` or `autoloop/core/engine.py` only if the new contract tests fail (`decisions.txt:2-4`).
- Later decisions narrow the overlapping-write contract to permissive execution only, not a broader concurrent last-writer-wins guarantee, and explicitly allow `concurrency=1` to make the assertion deterministic (`decisions.txt:8-12`).
- Later decisions also record that fan-in downstream routing must stay attached to the authored fan-in step rather than the composite declaration because the current lowering contract rejects composite routes when `fan_in` is present; this is treated as an implementation detail, not a change in requested runtime/checkpoint behavior (`decisions.txt:9,12-13`).

## Implemented behavior
- `tests/contract/test_branch_group_runtime.py:301-380` adds `test_parallel_branch_group_runtime_preserves_shared_state_values_and_overlapping_writes`, which exercises `Engine.run()` end to end and asserts:
  - branch-written state is visible in the final workflow state and in the downstream `publish` step (`lines 317-318, 347-349, 373-375`);
  - branch-mutated shared values are visible after branch-group settlement and observed by downstream execution (`lines 323-325, 348-349, 375`);
  - same-path writes are allowed to complete without framework rejection and produce persisted output (`lines 329-335, 376-380`).
- `tests/contract/test_branch_group_runtime.py:383-455` adds `test_parallel_branch_group_fan_in_request_input_checkpoints_at_composite_boundary_and_resumes`, which asserts:
  - the authored fan-in step asks for input (`lines 397-403`);
  - the paused run checkpoints at composite step `reviews`, not nested step `combine_reviews` (`lines 433-438`);
  - `Engine.resume(...)` completes downstream routing through `publish` and clears the checkpoint (`lines 440-455`).
- The final runtime code already supports the covered behavior:
  - child branch/fan-in contexts reuse the parent `state_cell` and `values` mapping in `autoloop/core/branch_groups/context.py:160-187`;
  - branch-group runtime wraps and restores shared values around branch execution in `autoloop/core/branch_groups/runtime.py:94-155`;
  - fan-in direct runtime control is remapped back to the composite step in `autoloop/core/branch_groups/runtime.py:590-622,654-685`;
  - checkpointing on `AWAIT_INPUT` persists `stage=current_step_name`, which is the composite branch-group step during branch-group execution, in `autoloop/core/engine.py:559-576`.
- Pair artifacts are consistent with the codebase: implementation notes record “coverage only, no runtime patch,” and test artifacts record independent targeted validation with `./.venv/bin/python -m pytest tests/contract/test_branch_group_runtime.py`.

## Unresolved gaps
- None. The final codebase contains committed contract coverage for every unresolved item from the request, and the targeted contract suite passed independently with `10 passed`.

## Differences justified by later clarification or analysis
- The overlapping-write regression test uses `concurrency=1` and checks permissive execution plus persisted output, not a general concurrent merge policy. That narrower assertion is explicitly justified by run decisions and still satisfies the original “not rejected by the framework” request.
- The fan-in regression routes downstream from the authored fan-in step instead of the composite declaration. That is justified by the recorded lowering constraint and does not weaken the requested behavior because the test still proves composite-boundary checkpointing and normal downstream completion after resume.
- No runtime code was changed because the new tests passed against the existing branch-group runtime and checkpoint path. This is consistent with the request’s “minimal fix only if tests fail” rule.

## Recommended next run
- No follow-up implementation run is required for this request slice.
