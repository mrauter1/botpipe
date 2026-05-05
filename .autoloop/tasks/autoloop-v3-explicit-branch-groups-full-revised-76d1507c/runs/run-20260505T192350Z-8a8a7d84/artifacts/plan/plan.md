# Branch-Group Regression Coverage Plan

## Scope And Invariants
- Stay inside branch-group runtime and checkpoint behavior only.
- Primary implementation surface is [tests/contract/test_branch_group_runtime.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_branch_group_runtime.py); runtime code changes are allowed only if the new regression tests fail.
- Any fix must stay minimal and local to [autoloop/core/branch_groups/runtime.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/branch_groups/runtime.py) and/or [autoloop/core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/engine.py).
- Preserve the established v1 rule that checkpointing happens at the composite branch-group boundary, not inside individual branches or inside the authored fan-in step.
- Do not widen scope into compiler/simple-surface work, topology/tracing payloads, session-policy changes, or new merge/conflict semantics for overlapping writes.

## Codebase Fit
- [tests/contract/test_branch_group_runtime.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_branch_group_runtime.py) already owns branch-group runtime contracts for fan-in routing, fail-fast settlement, evidence persistence, and mechanical outcomes; the missing request coverage belongs in this same file.
- [autoloop/core/branch_groups/context.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/branch_groups/context.py) already shares the parent `state_cell` and `values` mapping into branch and fan-in child contexts, so the unresolved gap is committed end-to-end coverage, not missing design intent.
- [autoloop/core/branch_groups/runtime.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/branch_groups/runtime.py) already maps authored fan-in direct runtime control back onto the composite step result, which is the seam most likely to matter if fan-in `RequestInput` checkpointing fails.
- [autoloop/core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/engine.py) already checkpoints `AWAIT_INPUT` at the current composite step name and resumes from `checkpoint.stage`; the new tests need to pin that contract for branch-group fan-in explicitly.

## Milestone
### 1. Add The Missing Runtime Contracts And Only Then Patch A Failing Seam
- Add one real-runtime contract case proving shared-effect semantics under actual branch execution:
  - a branch assigns `ctx.state = ...` and the parent state reflects the new value after branch settlement;
  - a branch mutates `ctx.values[...]` and the parent-visible mapping retains the mutation after the composite step returns;
  - multiple branches write the same workspace-relative path and the framework does not reject execution because of the overlap.
- Keep the overlapping-write assertion scoped to non-rejection, persisted output existence, and downstream completion. Do not add a stronger ordering or merge contract unless the test uses deterministic serialization such as `concurrency=1`.
- Add one authored fan-in pending-input contract case:
  - the fan-in step itself returns `RequestInput`;
  - the initial run stops at `AWAIT_INPUT`;
  - `checkpoint.stage` stays on the branch-group composite step name rather than the nested fan-in step name;
  - normal `Engine.resume(...)` with an answer continues through the composite and reaches the authored downstream step.
- If either test exposes a bug, fix only the failing runtime/checkpoint seam:
  - use [autoloop/core/branch_groups/runtime.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/branch_groups/runtime.py) for fan-in-to-composite direct-control mapping issues;
  - use [autoloop/core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/engine.py) only for composite checkpoint stage or resume propagation issues.

## Interface And Contract Notes
- No public authoring API changes are planned.
- The request-level contracts this slice must pin are:
  - branch `ctx.state` assignment reaches the shared parent state cell by the time the branch group settles;
  - branch `ctx.values` mutation remains visible after branch settlement;
  - overlapping writes to the same workspace path are permitted and are not preemptively rejected by the framework;
  - fan-in `RequestInput` becomes parent pending input at the composite boundary, with `checkpoint.stage` equal to the branch-group step and resume continuing through ordinary downstream routing.
- Existing behavior outside branch groups must remain unchanged.

## Compatibility Notes
- No checkpoint schema or artifact schema changes are expected.
- Composite-boundary checkpointing remains the compatibility anchor for resume behavior; this slice only adds explicit regression coverage around that rule.
- Overlapping-write support remains permissive rather than conflict-resolving; this work must not introduce any new workspace arbitration behavior.

## Validation
- Run the targeted branch-group contract file after the test additions, and rerun the same targeted file after any minimal runtime fix.
- Keep the new coverage in the contract suite rather than only the unit suite, because the missing request surface is `Engine.run()` / `Engine.resume()` behavior under real branch-group settlement.

## Risk Register
- Composite vs nested checkpoint confusion:
  - Risk: a fan-in `RequestInput` could checkpoint the nested fan-in step name instead of the composite branch-group step.
  - Control: assert `checkpoint.stage` is the composite step name and that resume reaches downstream completion.
- False confidence from helper-only coverage:
  - Risk: context-sharing unit tests can pass while the full branch runtime or checkpoint handoff regresses.
  - Control: exercise the new semantics through real workflow execution in the contract suite.
- Nondeterministic overlapping-write assertions:
  - Risk: concurrent writes can make final file contents scheduler-dependent.
  - Control: assert only non-rejection unless the test intentionally serializes execution for deterministic content.
- Scope creep into already-shipped branch-group features:
  - Risk: a failing test could trigger unrelated refactors in discovery, compiler, or topology code.
  - Control: keep any fix local to the branch-group runtime/checkpoint path and stop after the targeted contracts pass.
