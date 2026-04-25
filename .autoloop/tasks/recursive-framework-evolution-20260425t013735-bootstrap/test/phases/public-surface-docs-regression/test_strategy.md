# Test Strategy

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: test
- Phase ID: public-surface-docs-regression
- Phase Directory Key: public-surface-docs-regression
- Phase Title: Public Surface, Docs, And Regression
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Public export split:
  - `tests/strictness/test_no_compat.py`
  - `tests/unit/test_primitives_and_stores.py`
  - Verifies root `workflow` exports only the authoring primitives and `workflow.primitives` carries `ChildWorkflowResult` with the low-level runtime surface.
- Docs contract:
  - `tests/test_architecture_baseline_docs.py`
  - Verifies `workflow.toml` remains metadata-only, `ctx.open_session(..., scope=...)` remains supported, and the docs describe continuity, typed params, artifact contracts, typed routes/effects, worklists, and typed child outputs.
- Legacy child-invoker compatibility:
  - `tests/unit/test_primitives_and_stores.py`
  - Verifies `Context.invoke_workflow(...)` omits `input=` for older invoker callback shapes and raises instead of silently dropping typed input when the invoker cannot accept it.
- Directory-backed artifact compatibility:
  - `tests/unit/test_primitives_and_stores.py`
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - Verifies schema-less directory outputs remain valid while JSON/schema-backed directory outputs fail.
- Typed child-output strictness:
  - `tests/runtime/test_workspace_and_context.py`
  - Verifies invalid typed child outputs are recorded as validation failures rather than being coerced into successful outputs.
- Placeholder regression safety:
  - `tests/unit/test_primitives_and_stores.py`
  - Verifies mid-chain `None` state placeholders collapse to an empty path segment instead of being misclassified as missing work-item context.

## Preserved Invariants Checked

- `ctx.open_session(..., scope=...)` keyword and positional compatibility remain documented and covered.
- Existing child composition helpers keep working with older runtime-backed invoker shapes.
- Existing candidate-surface workflows that publish directories do not regress under artifact enforcement.
- Full repository regression stays green after the public-surface/doc assertions tighten.

## Edge Cases

- Missing optional artifact files remain allowed.
- Mid-chain `None` placeholder values in `state.*` paths resolve deterministically.
- Typed child input against a legacy invoker shape fails loudly instead of being ignored.

## Failure Paths

- JSON/schema artifacts pointing at a directory fail validation.
- Typed child outputs with coercion-only values fail strict validation and surface metadata errors.
- Legacy invokers without `input` support reject typed child input.

## Flake Risks / Stabilization

- Tests are filesystem-only and deterministic; no timing, network, or external service dependencies were introduced.
- Runtime coverage reuses existing package fixtures and synthetic providers to avoid nondeterministic ordering or provider-side behavior.

## Validation Performed

- `.venv/bin/pytest -q tests/unit/test_primitives_and_stores.py tests/runtime/test_workspace_and_context.py::test_context_invoke_workflow_records_typed_child_output_validation_failures`
- `.venv/bin/pytest -q`

## Known Gaps

- No new docs/template text under `.autoloop_recursive/` was authored in this turn; coverage only guards the maintained canonical docs and current recursive-memory assertions.
