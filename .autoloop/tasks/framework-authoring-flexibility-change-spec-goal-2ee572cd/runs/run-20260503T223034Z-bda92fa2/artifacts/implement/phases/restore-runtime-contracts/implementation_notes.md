# Implementation Notes

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: implement
- Phase ID: restore-runtime-contracts
- Phase Directory Key: restore-runtime-contracts
- Phase Title: Restore Runtime Contracts
- Scope: phase-local producer artifact

## Files Changed

- `autoloop/core/artifacts.py`
- `autoloop/core/lowering.py`
- `autoloop/runtime/config.py`
- `autoloop/runtime/runner.py`
- `docs/authoring.md`
- `tests/runtime/test_workspace_and_context.py`
- `tests/contract/test_engine_contracts.py`
- `tests/unit/test_validation.py`

## Symbols Touched

- `_resolve_work_item_path`, `_work_item_field`, `_work_item_payload_root`
- `step_available_route_tags`
- `load_runtime_config_file`, `_load_narrow_yaml_mapping`, `_strip_yaml_comment`, `_parse_narrow_yaml_scalar`
- `_prompt_registry_roots`

## Checklist Mapping

- Milestone 1 / AC-1: restored `{item.payload.<path>}` and `{worklist.<name>.current.payload.<path>}` runtime rendering against mapping-backed item payloads while preserving missing-path `WorkflowExecutionError` wording.
- Milestone 1 / AC-2 / AC-3: restored stable `available_routes` ordering and documented the authored-step, authored-global, runtime-control contract in `docs/authoring.md`.
- Milestone 1 / AC-4: aligned the stale pair-step contract fixture with the shipped dual-role artifact ownership rule instead of weakening validation.
- Milestone 2: made the file-backed runtime config path executable without PyYAML and let runner prompt-registry root discovery accept string-backed compiled prompts.
- Milestone 3: rewrote temporary workflow-package fixtures in `tests/runtime/test_workspace_and_context.py` to canonical `python_step(ctx)` handlers while leaving `build_output(state, ctx)` unchanged.

## Assumptions

- Mapping-backed worklist items produced from raw item envelopes should resolve `item.payload.*` against the nested authored payload object when the envelope still carries standard item fields.

## Preserved Invariants

- Placeholder-specific missing-payload-path errors remain unchanged.
- Dual-role artifact ownership validation remains strict.
- Runtime config precedence and typed validation stay unchanged.
- `build_output(state, ctx)` remains the supported output-builder contract.
- Full-auto provider-visible question-route hiding remains unchanged.

## Intended Behavior Changes

- `available_routes` now deterministically order authored step-local routes first, authored global routes next, runtime-control routes last.
- Runner prompt-registry path discovery now tolerates compiled prompt references that are still plain strings.
- YAML runtime config files can load in no-PyYAML environments only for the existing mapping/scalar config subset.

## Known Non-Changes

- No restoration of legacy `python_step(state, ctx)` compatibility in production code.
- No widening of accepted runtime-config syntax beyond the narrow fallback subset.
- No rollback of the artifact ownership diagnostic.

## Expected Side Effects

- Provider contract surfaces and static graph payloads now expose stable route ordering wherever authored global routes coexist with injected control routes.
- Temporary runtime workflow-package fixtures mutate `ctx.state` directly.

## Validation Performed

- `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k "payload or control_contracts or pair_step_contract_logs_raw_output"`
- `./.venv/bin/python -m pytest -q tests/runtime/test_provider_backends.py -k "full_auto_runtime_policy"`
- `./.venv/bin/python -m pytest -q tests/runtime/test_workspace_and_context.py -k "full_auto or invoke_workflow"`
- `./.venv/bin/python -m pytest -q tests/unit/test_validation.py -k "compilation_exposes_step_control_contracts"`
- `./.venv/bin/python -m pytest -q tests/runtime/test_runtime_static_graph.py tests/runtime/test_package_cli.py tests/test_architecture_baseline_docs.py tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py tests/contract/test_canonical_runtime_contracts.py tests/contract/test_engine_contracts.py tests/unit/test_simple_surface.py tests/unit/test_primitives_and_stores.py tests/unit/test_provider_boundary_core.py tests/unit/test_provider_retries.py tests/runtime/test_provider_backends.py tests/runtime/test_workspace_and_context.py`

## Deduplication / Centralization

- Route-order restoration is centralized in `step_available_route_tags(...)` so compiler, runtime, and provider surfaces share one contract source.
- Payload-root normalization is localized in artifact placeholder resolution instead of duplicating worklist-specific branches elsewhere.
