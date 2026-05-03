# Framework-Authoring-Flexibility Follow-Up Plan

## Scope

Close the remaining acceptance gaps without reopening earlier framework-authoring-flexibility work:

- restore late-bound payload placeholder rendering at runtime
- reconcile route/artifact regression tests with the shipped contracts
- finish the `full_auto` runner/config path in the supported test environment
- align temporary runtime workflow fixtures with the current canonical `python_step(ctx)` surface

Observed audited-slice failures on 2026-05-03: 12 failures, concentrated in `tests/contract/test_engine_contracts.py`, `tests/runtime/test_provider_backends.py`, and `tests/runtime/test_workspace_and_context.py`.

## Milestones

### 1. Restore runtime contract behavior

Implementation targets:

- `autoloop/core/artifacts.py`
- `autoloop/core/lowering.py` and any dependent compile/inspection surfaces
- `tests/contract/test_engine_contracts.py`
- `docs/authoring.md` to document the stable route-order contract

Plan:

- Fix payload placeholder traversal so `{item.payload.<path>}` resolves against the item payload mapping instead of the enclosing item object.
- Preserve the same runtime semantics for `{worklist.<name>.current.payload.<path>}` and keep missing-path failures placeholder-specific.
- Restore stable route ordering as a contract: authored step-local routes first, authored global routes next, runtime-injected control routes last. Keep `provider_visible_routes_*` as filtered views that preserve that order.
- Update `docs/authoring.md` so the public `available_routes` contract explicitly states that stable ordering.
- Keep the new dual-role artifact ownership validation intact. Update stale regression fixtures that still declare the same artifact as both workflow-level and step-produced.

Acceptance notes:

- Successful payload lookups must render inline prompt text at runtime.
- Missing payload paths must still raise `WorkflowExecutionError` messages that include the original placeholder and missing path.
- `available_routes` ordering must be deterministic across engine, runtime graph/CLI payloads, and provider calls.
- `docs/authoring.md` must explicitly describe the stable `available_routes` ordering that Phase 1 restores.
- No rollback of the artifact ownership diagnostic unless authoritative clarification later requires it.

### 2. Finish `full_auto` runner/config plumbing

Implementation targets:

- `autoloop/runtime/config.py`
- `autoloop/runtime/runner.py`
- targeted runtime tests that cover file-backed config and prompt-registry preparation

Plan:

- Make the typed runtime config file path used by regression tests executable without optional PyYAML. Prefer a narrow built-in fallback parser for the existing mapping/scalar config surface over adding a broad new dependency or changing public config precedence.
- Keep `parse_runtime_config(...)` as the single schema/validation path; loader changes should only affect raw file decoding.
- Normalize prompt references on the runner prompt-registry path so compiled core workflows that still store prompts as plain strings behave the same as workflows using `Prompt` objects.
- Reconfirm that `full_auto=True` still hides the default provider-visible `question` route at execution time.

Acceptance notes:

- Repo/local and user/global config precedence must stay unchanged.
- Unsupported config constructs should still fail fast with `ConfigError`; the fallback should not silently widen the accepted config language.
- `run_workflow_package(...)` must stop assuming `CompiledStep.producer_prompt` / `verifier_prompt` are always `Prompt` instances.

### 3. Align runtime fixtures and revalidate

Implementation targets:

- temporary workflow-package writers in `tests/runtime/test_workspace_and_context.py`
- the audited regression slice from the request

Plan:

- Update temporary workflow packages in `tests/runtime/test_workspace_and_context.py` to use the canonical `python_step(ctx)` signature and mutate `ctx.state` directly.
- Leave `build_output(state, ctx)` unchanged; that remains the current output-builder contract.
- Re-run targeted workspace tests first, then the full audited regression slice.

Acceptance notes:

- Do not restore legacy `python_step(state, ctx)` compatibility in production code as part of this follow-up.
- Child-run metadata, artifact adoption, resume behavior, and typed child-output assertions must stay unchanged after the fixture rewrite.

## Interfaces And Compatibility

- Payload placeholder contract:
  - `{item.payload}` and `{item.payload.<path>}` remain valid on scoped prompt steps.
  - `{worklist.<name>.current.payload}` and `{worklist.<name>.current.payload.<path>}` remain valid with the same late-bound semantics.
  - Missing payload paths keep the current placeholder-specific `WorkflowExecutionError` format.

- Route-order contract:
  - `available_routes` is ordered as authored step-local routes, then authored global routes, then injected runtime-control routes.
  - `provider_visible_routes_interactive` and `provider_visible_routes_full_auto` preserve that relative order after filtering.
  - In `full_auto`, the default injected `question` route remains hidden from provider-visible routes unless explicitly authored/allowed by existing policy.

- Artifact ownership contract:
  - Workflow-level artifacts remain inputs/managed external artifacts.
  - Step `writes` remain produced artifacts.
  - Regression fixes should update stale tests rather than weaken the shipped dual-role validation.

- Handler-signature contract:
  - Canonical runtime package handlers are `python_step(ctx)`.
  - `build_output(state, ctx)` remains the supported two-argument builder surface.

- Config compatibility:
  - Typed runtime config filenames and merge precedence stay unchanged.
  - Any no-PyYAML fallback must stay intentionally narrow and feed the existing typed validation path.

## Regression Risks And Controls

| Risk | Surface | Control |
| --- | --- | --- |
| Payload-path fix breaks non-payload placeholder traversal | runtime prompt rendering and artifact template rendering | confine the fix to payload-root handoff logic and rerun prompt/artifact contract tests |
| Route-order fix changes legal-route membership instead of order only | compiler, provider contract builder, static graph, CLI inspection payloads | keep route visibility logic unchanged; only separate authored/global/runtime-control ordering |
| Config fallback silently accepts unsupported YAML features | runtime config loading | keep fallback limited to the documented mapping/scalar surface and raise `ConfigError` on unsupported constructs |
| Fixture rewrite changes runtime behavior instead of only authoring shape | child workflow invocation and resume tests | update only temporary package source strings, keep assertions and metadata expectations intact |

## Validation

Targeted before final slice:

- `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k "payload or control_contracts or pair_step_contract_logs_raw_output"`
- `./.venv/bin/python -m pytest -q tests/runtime/test_provider_backends.py -k "full_auto_runtime_policy"`
- `./.venv/bin/python -m pytest -q tests/runtime/test_workspace_and_context.py -k "full_auto or invoke_workflow"`

Final audited slice:

- `./.venv/bin/python -m pytest -q tests/runtime/test_runtime_static_graph.py tests/runtime/test_package_cli.py tests/test_architecture_baseline_docs.py tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py tests/contract/test_canonical_runtime_contracts.py tests/contract/test_engine_contracts.py tests/unit/test_simple_surface.py tests/unit/test_primitives_and_stores.py tests/unit/test_provider_boundary_core.py tests/unit/test_provider_retries.py tests/runtime/test_provider_backends.py tests/runtime/test_workspace_and_context.py`

## Rollback

- Revert the payload traversal change without touching placeholder error wording if unrelated runtime placeholders regress.
- Revert route-ordering changes independently from visibility-policy logic if downstream inspection payloads drift unexpectedly.
- Disable or remove any fallback config loader if it accepts broader syntax than intended; keep the typed validation path unchanged.
- Revert only the temporary test package source rewrites if workspace regressions are traced to fixture churn rather than runtime code.
