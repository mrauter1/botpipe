# Test Strategy

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: test
- Phase ID: single-step-parity-and-cleanup
- Phase Directory Key: single-step-parity-and-cleanup
- Phase Title: Single Step Parity And Cleanup
- Scope: phase-local producer artifact

## Behavior Coverage Map

- `SingleStepPlan` remains parity-only and internal:
  covered by `tests/contract/test_single_step_plan_equivalence.py`
  checks supported single-step declarations, explicit route overrides, policy layering, typed input/params handling, provider-question parity, and direct synthetic-workflow equivalence.
- Workspace manifest-package capability metadata survives the final cleanup:
  covered by `tests/runtime/test_workflow_reference_resolution.py`
  checks alias-based resolution plus capability inspection still surface the exported `Params` model.
- Workspace import hygiene does not dirty the workflow tree:
  covered by `tests/runtime/test_package_cli.py`
  checks `workflows show` and `run` on a typed workspace package leave no `__pycache__` directories under `.botlane/workflows`.

## Preserved Invariants

- `Botlane.step(...)` stays on the synthetic workflow execution path in this phase.
- `SingleStepPlan` remains internal and unexported.
- Workspace package parameter discovery continues to prefer the exported/spec-defined `Params` model.

## Edge Cases And Failure Paths

- Alias-addressed manifest packages are exercised in the loader suite, and the CLI suite covers the supported workspace capability/import path used by real users.
- The no-`__pycache__` assertion is filesystem-based and deterministic; it does not depend on git output or subprocess ordering.

## Known Gaps

- Git-tracking CLI dirtiness remains covered indirectly by the existing full-suite green run rather than by a second phase-local duplicate test.
