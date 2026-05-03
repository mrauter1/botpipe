# Follow-up request: close remaining framework-authoring-flexibility acceptance gaps

The main framework-authoring-flexibility changes are largely implemented, but the repository is not yet at acceptance. Complete the follow-up work below without reopening already-finished feature areas.

## Required fixes

1. Fix late-bound runtime placeholder rendering for payload paths.
   - `{item.payload.<path>}` must render successfully at runtime when the payload path exists.
   - `{worklist.<name>.current.payload.<path>}` must keep working with the same semantics.
   - Missing payload paths must still fail with clear placeholder-specific `WorkflowExecutionError` messages.

2. Make the regression suite consistent with the shipped route and artifact contracts.
   - Resolve the remaining contract-test failures caused by the new artifact ownership diagnostic and the new route-policy behavior.
   - If provider route ordering is intended to be stable, restore the intended ordering in code and document it.
   - If ordering is not intended to be contractual, update the stale tests to assert the new contract without overspecifying order.

3. Finish the runner/config plumbing acceptance path for `full_auto`.
   - The runtime config path used by tests must be executable in the supported test environment.
   - `run_workflow_package(...)` must handle core-style workflows whose compiled prompts are still represented as plain strings on the prompt-registry path.
   - The full-auto runner regression test added for this task must pass.

4. Reconcile the remaining runtime fixture regressions in `tests/runtime/test_workspace_and_context.py`.
   - Decide whether temporary test workflow packages should use the current canonical `ctx`-only `python_step` handler signature.
   - Update those fixtures accordingly, unless compatibility for legacy `python_step(state, ctx)` handlers is explicitly required and restored.

## Validation required

- Re-run the same audited regression slice:
  - `./.venv/bin/python -m pytest -q tests/runtime/test_runtime_static_graph.py tests/runtime/test_package_cli.py tests/test_architecture_baseline_docs.py tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py tests/contract/test_canonical_runtime_contracts.py tests/contract/test_engine_contracts.py tests/unit/test_simple_surface.py tests/unit/test_primitives_and_stores.py tests/unit/test_provider_boundary_core.py tests/unit/test_provider_retries.py tests/runtime/test_provider_backends.py tests/runtime/test_workspace_and_context.py`
- The follow-up is complete only when that slice is green and the late-bound payload placeholder behavior matches the original request.
