# Implementation Notes

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: implement
- Phase ID: repair-full-auto-runner-plumbing
- Phase Directory Key: repair-full-auto-runner-plumbing
- Phase Title: Repair Full Auto Plumbing
- Scope: phase-local producer artifact

## Files Changed

- `autoloop/runtime/config.py`

## Symbols Touched

- `_load_narrow_yaml_mapping`

## Checklist Mapping

- Plan milestone 2 / AC-1: fixed the no-PyYAML config loader so nested `runtime` mappings such as `runtime.full_auto` plus `runtime.tracing.include_state_snapshots` parse successfully in the supported test environment.
- Plan milestone 2 / AC-2: verified no code change was required; the runner prompt-registry path already accepts plain-string prompt specs and the audited slice stayed green.
- Plan milestone 2 / AC-3: verified through the audited slice that `full_auto` still hides the default provider-visible `question` route at runtime.

## Assumptions

- The phase-local contract remains authoritative: preserve the current typed runtime config schema and precedence; do not broaden accepted YAML beyond the narrow mapping/scalar fallback.

## Preserved Invariants

- `parse_runtime_config(...)` remains the single validation path after file decoding.
- Unsupported YAML constructs still raise `ConfigError`.
- Global/local config discovery and merge precedence are unchanged.
- No provider-route visibility or prompt-registry behavior changed in this turn.

## Intended Behavior Changes

- The no-PyYAML fallback now treats sibling keys within an already-open mapping as valid, instead of rejecting them as an illegal indentation increase.

## Known Non-Changes

- No changes to `autoloop/runtime/runner.py`.
- No changes to test fixtures in `tests/runtime/test_workspace_and_context.py`.
- No changes to provider selection precedence or the public runtime config schema.

## Expected Side Effects

- File-backed configs using the supported indented mapping/scalar subset now work without optional PyYAML when nested runtime sections contain multiple sibling keys.

## Validation Performed

- `./.venv/bin/python -m pytest -q tests/runtime/test_provider_backends.py -k 'full_auto_runtime_policy or resolve_runtime_config_reads_valid_nested_runtime_policy_without_pyyaml or load_runtime_config_file_without_pyyaml or full_auto_hides_default_question_route'`
- `./.venv/bin/python -m pytest -q tests/runtime/test_runtime_static_graph.py tests/runtime/test_package_cli.py tests/test_architecture_baseline_docs.py tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py tests/contract/test_canonical_runtime_contracts.py tests/contract/test_engine_contracts.py tests/unit/test_simple_surface.py tests/unit/test_primitives_and_stores.py tests/unit/test_provider_boundary_core.py tests/unit/test_provider_retries.py tests/runtime/test_provider_backends.py tests/runtime/test_workspace_and_context.py`

## Deduplication / Centralization

- Kept the fix inside `_load_narrow_yaml_mapping` so all config-file call sites continue to share one narrow decoding path before typed validation.
