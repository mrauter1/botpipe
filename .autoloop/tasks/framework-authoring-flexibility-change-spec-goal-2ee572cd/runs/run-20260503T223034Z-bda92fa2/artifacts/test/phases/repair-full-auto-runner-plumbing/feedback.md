# Test Author ↔ Test Auditor Feedback

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: test
- Phase ID: repair-full-auto-runner-plumbing
- Phase Directory Key: repair-full-auto-runner-plumbing
- Phase Title: Repair Full Auto Plumbing
- Scope: phase-local authoritative verifier artifact

## Test Additions Summary

- Added `tests/unit/test_primitives_and_stores.py::test_prompt_registry_roots_include_plain_string_prompt_spec_dirs` to pin AC-2 directly on the runner prompt-root discovery path for compiled string prompt specs.
- Revalidated existing AC-1 and AC-3 coverage through the focused runtime tests and the full audited slice.
- Final validation status: audited slice green (`574 passed, 14 warnings`).

## Audit Result

- No blocking findings.
- No non-blocking findings.
- Audit evidence:
  - `./.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py tests/runtime/test_provider_backends.py tests/runtime/test_workspace_and_context.py -k 'prompt_registry_roots or full_auto or pyyaml or nested_runtime_policy or load_runtime_config_file_without_pyyaml'`
  - `./.venv/bin/python -m pytest -q tests/runtime/test_runtime_static_graph.py tests/runtime/test_package_cli.py tests/test_architecture_baseline_docs.py tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py tests/contract/test_canonical_runtime_contracts.py tests/contract/test_engine_contracts.py tests/unit/test_simple_surface.py tests/unit/test_primitives_and_stores.py tests/unit/test_provider_boundary_core.py tests/unit/test_provider_retries.py tests/runtime/test_provider_backends.py tests/runtime/test_workspace_and_context.py`
