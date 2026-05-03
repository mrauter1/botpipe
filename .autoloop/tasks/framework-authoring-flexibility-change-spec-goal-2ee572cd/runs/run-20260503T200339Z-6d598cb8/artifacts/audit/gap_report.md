# Original intent considered

- The immutable request snapshot at `.autoloop/tasks/framework-authoring-flexibility-change-spec-goal-2ee572cd/runs/run-20260503T200339Z-6d598cb8/request.md`.
- The authoritative clarification / execution ledger in `raw_phase_log.md`.
- The recorded decisions in `decisions.txt`.
- The phase-local plan, implementation, and test artifacts under `.autoloop/tasks/framework-authoring-flexibility-change-spec-goal-2ee572cd/runs/run-20260503T200339Z-6d598cb8/artifacts`.
- The landed code and tests in `autoloop/`, `docs/`, `workflows/`, and `tests/`.

# Clarifications / superseding decisions

- `decisions.txt` block 9 narrows runtime prompt interpolation to late-bound `item.*` and `worklist.*` placeholders only. That is consistent with the request’s late-bound namespace goal and avoids silently broadening general prompt interpolation.
- `decisions.txt` block 10 adds an explicit managed-artifact role for shipped workflows that intentionally declare the same artifact as workflow-owned and step-produced. This is a justified extension of the requested compile-time ownership diagnostic, not a rollback of it.
- `decisions.txt` blocks 1, 2, 3, 4, and 11 consistently treat compiled route metadata as the single source of truth for authored routes, runtime-control routes, and policy-specific provider visibility.

# Implemented behavior

- Route policy rebase landed:
  - `autoloop/core/steps.py` adds `ControlRoutes`.
  - `autoloop/core/providers/models.py` adds `RuntimeInteractionPolicy`.
  - `autoloop/core/discovery.py`, `autoloop/core/compiler.py`, `autoloop/core/engine.py`, and `autoloop/core/engine_collaborators.py` now compile and expose authored routes, runtime-control routes, and provider-visible routes for interactive vs full-auto modes.
- Lazy worklists and work-item session continuity landed:
  - `autoloop/core/context.py` adds lazy selection access.
  - `autoloop/core/engine.py` restores only snapshotted selections and materializes missing selections on first use.
  - `autoloop/core/engine_collaborators.py` forces scoped selection resolution before artifacts, item state, and session binding.
- Typed effects and the validation helper landed:
  - `autoloop/core/effects.py` adds `WorklistEffect` and `Effects`.
  - `autoloop/core/routes.py` adds `Route.advance(...)`, `Route.refresh(...)`, and `Route.complete_current(...)`.
  - `autoloop/simple.py` and `autoloop/core/validation_helpers.py` add `validation_step` and `ValidationResult`.
- Artifact ownership diagnostics and prompt-validation relaxation landed:
  - `autoloop/core/inventory.py` now rejects same-identity workflow-level plus produced artifacts unless `role="managed"`.
  - `autoloop/core/discovery.py` allows late-bound `item.*` and `worklist.*` placeholders at compile time.
  - `autoloop/core/artifacts.py` and `autoloop/core/engine.py` perform runtime placeholder resolution.
- Inspection, static graph, and docs landed:
  - `autoloop/core/workflow_capabilities.py`, `autoloop/runtime/static_graph.py`, and `autoloop/runtime/cli.py` expose the richer route metadata.
  - `docs/authoring.md` and `docs/architecture.md` document the new validation split, route policy, lazy worklists, managed artifacts, and typed effects.

Audit rerun evidence:

- Command run from repo root:
  - `./.venv/bin/python -m pytest -q tests/runtime/test_runtime_static_graph.py tests/runtime/test_package_cli.py tests/test_architecture_baseline_docs.py tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py tests/contract/test_canonical_runtime_contracts.py tests/contract/test_engine_contracts.py tests/unit/test_simple_surface.py tests/unit/test_primitives_and_stores.py tests/unit/test_provider_boundary_core.py tests/unit/test_provider_retries.py tests/runtime/test_provider_backends.py tests/runtime/test_workspace_and_context.py`
- Result:
  - `557 passed`
  - `12 failed`

# Unresolved gaps

1. Direct spec regression: late-bound payload placeholders compile but do not render correctly at runtime.
   - Evidence:
     - `tests/contract/test_engine_contracts.py::test_prompt_runtime_lazily_renders_item_and_worklist_placeholders` failed during the audit rerun.
     - `autoloop/core/artifacts.py` currently sends `item.payload.foo` through `_resolve_work_item_path(...)` with `parts=["payload", "foo"]`, but `_resolve_item_placeholder(...)` obtains `current = context.item`, which is already the item payload mapping in this failing test shape; runtime then raises `prompt placeholder {item.payload.foo} references missing payload path 'foo'`.
   - Why material:
     - This violates request section 7 and acceptance criterion 10. `{item.payload.<path>}` is one of the explicitly required late-bound prompt contexts.

2. The repository is not at requested acceptance because several tests were not rebased to the new contract.
   - Evidence:
     - `tests/contract/test_engine_contracts.py::test_pair_step_contract_logs_raw_output_and_updates_state` still declares the same artifact as both workflow-level and step-produced without `managed`, and now fails with the new compile-time ownership diagnostic from `autoloop/core/inventory.py`.
     - `tests/contract/test_engine_contracts.py::test_llm_requests_include_step_control_contracts` and `::test_pair_requests_include_step_control_contracts` still expect provider route order `("done", "failed", "question")`, while current code returns `("done", "question", "failed")`.
   - Why material:
     - The request explicitly required updating existing tests to the new behavior instead of preserving old blanket defaults. The run is not complete while these contract tests are still red.

3. The route-policy runner/config coverage added for this work is not actually green at audit time.
   - Evidence:
     - `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_reads_full_auto_runtime_policy` failed because `autoloop/runtime/config.py` still requires `PyYAML` to parse `autoloop.yaml` in the current test environment.
     - `tests/runtime/test_workspace_and_context.py::test_runner_full_auto_hides_default_question_route_from_provider_contract` failed because `autoloop/runtime/runner.py::_prompt_registry_roots(...)` assumes every compiled prompt has `.source`, but `PromptStep(producer="ask.md")` leaves a plain string prompt on the compiled step path used by that test.
   - Why material:
     - Request section 10 requires full-auto / interaction policy plumbing through the runner and config surface, with regression coverage. The added coverage path is still broken.

4. Audit rerun found collateral runtime-fixture regressions that were not reconciled after this refactor.
   - Evidence:
     - `tests/runtime/test_workspace_and_context.py` has five failures where generated temporary workflow packages still declare legacy `@python_step def launch(state, ctx)` / `def wait(state, ctx)` handlers, and validation now rejects them with `"python_step 'launch' handler" must accept 1 positional arguments`.
   - Why material:
     - These are not part of the original feature request, but they keep the audited regression slice red. The next run needs to decide whether these fixtures must be rewritten to the current `ctx`-only canonical handler style or whether compatibility is intentionally being preserved.

# Differences justified by later clarification or analysis

- The implementation added `Artifact.managed(...)` / `role="managed"` instead of keeping the initial diagnostic escape hatch unimplemented. This is justified by `decisions.txt` block 10 and is consistent with the request’s allowance for an explicit managed/shared mechanism.
- Runtime prompt interpolation remains intentionally narrow. Only late-bound `item.*` and `worklist.*` placeholders are rendered at runtime; other placeholders remain literal. This is justified by `decisions.txt` block 9 and remains consistent with the request’s scope.
- Inspection surfaces expose richer route metadata than the minimum request wording. This is additive and justified by the recorded decision to make compiled route metadata the authoritative route-classification source.

# Recommended next run

- Fix the direct late-bound placeholder runtime bug so `{item.payload.<path>}` and equivalent worklist payload paths resolve correctly at execution time.
- Reconcile the remaining red tests with the new contract:
  - update stale ownership and route-order expectations where the implementation is correct,
  - or restore any intended stable ordering semantics if provider route order is meant to be contractual.
- Repair the full-auto runner/config regression path uncovered by the audit rerun:
  - make the config test path executable in the supported test environment,
  - and make `_prompt_registry_roots(...)` tolerate string prompt declarations used by core-style workflows.
- Rebase the temporary runtime workflow fixtures in `tests/runtime/test_workspace_and_context.py` to the current canonical `ctx`-only `python_step` handler contract, unless compatibility with legacy `state, ctx` handlers is intentionally required and explicitly restored.
