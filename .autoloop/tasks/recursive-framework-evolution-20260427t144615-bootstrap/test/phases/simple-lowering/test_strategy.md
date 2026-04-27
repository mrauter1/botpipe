# Test Strategy

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: test
- Phase ID: simple-lowering
- Phase Directory Key: simple-lowering
- Phase Title: Simple Workflow Lowering
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Simple-surface imports and prompt primitives: cover repo-root and staged-package imports plus `Prompt.inline(...)` and file-backed prompt origin metadata.
- Simple lowering happy paths: cover step-name binding, inferred step-local artifact paths, inferred entry for one-step and chained workflows, review-step accepted/rework lowering, and absence of implicit provider control schemas.
- Placeholder inference: cover unambiguous inline/file prompt reads, conservative ambiguity handling, and preserved non-inference of `requires`.
- `workflow_step(...)` lowering: cover compile-time lowering to the existing system-step model, generated child invocation, reserved `question` route mapping, and `message_from` artifact loading.

## Preserved Invariants Checked

- Simple `Workflow` remains non-strict at class-definition time, while `StrictWorkflow` preserves import-time validation.
- Lowered simple workflows still compile through `compile_workflow(...)` and keep undeclared-workspace-output behavior unchanged by staying on the existing runtime path.
- File-backed prompt inference shares the same prompt-resolution rules as runtime prompt loading.

## Edge And Failure Coverage

- Bare placeholder ambiguity against `State` fields does not create reads.
- `workflow_step(message_from=...)` rejects unknown artifact references with a compile-time validation error.
- Child workflows that pause with a `question` event map back to the reserved parent `question -> PAUSE` route.

## Stability Notes

- Tests use local fake contexts and dataclass child-result doubles instead of live runtime runs to keep coverage deterministic and phase-local.
- File-backed prompt tests use tmp-path fixtures and direct file writes; no network, timing, or nondeterministic ordering is involved.

## Known Gaps

- This phase does not exercise first-class engine support for `kind=\"workflow\"` nodes because the implementation intentionally lowers `workflow_step(...)` through generated `SystemStep` handlers on the current runtime seam.
- `before` / `after` execution semantics remain out of phase for the test scope because the runtime hook-order work is deferred to later phases.
