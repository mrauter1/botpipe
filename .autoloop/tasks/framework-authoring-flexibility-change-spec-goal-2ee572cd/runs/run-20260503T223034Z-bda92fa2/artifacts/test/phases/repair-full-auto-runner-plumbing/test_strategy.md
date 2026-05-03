# Test Strategy

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: test
- Phase ID: repair-full-auto-runner-plumbing
- Phase Directory Key: repair-full-auto-runner-plumbing
- Phase Title: Repair Full Auto Plumbing
- Scope: phase-local producer artifact

## Behavior-To-Coverage Map

- AC-1 no-PyYAML config happy path:
  - `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_reads_valid_nested_runtime_policy_without_pyyaml`
  - Confirms nested `runtime.full_auto` plus `runtime.tracing.include_state_snapshots` loads through the narrow fallback and the typed config path.
- AC-1 failure paths:
  - `tests/runtime/test_provider_backends.py::test_load_runtime_config_file_without_pyyaml_rejects_indented_child_under_scalar`
  - `tests/runtime/test_provider_backends.py::test_load_runtime_config_file_without_pyyaml_rejects_overindented_sibling_mapping`
  - Confirms malformed indentation still fails with `ConfigError` rather than widening the accepted config language.
- AC-2 plain-string prompt spec runner path:
  - `tests/unit/test_primitives_and_stores.py::test_prompt_registry_roots_include_plain_string_prompt_spec_dirs`
  - Directly pins the root-collection behavior `run_workflow_package(...)` relies on when compiled steps carry string prompt specs instead of `Prompt` objects.
- AC-2 preserved adjacent behavior:
  - `tests/unit/test_primitives_and_stores.py::test_prompt_registry_roots_include_capability_prompt_dirs_outside_workflow_parent`
  - Confirms the new AC-2 test does not displace capability prompt-root coverage.
- AC-3 full-auto provider-visible route contract:
  - `tests/runtime/test_workspace_and_context.py::test_runner_full_auto_hides_default_question_route_from_provider_contract`
  - Confirms the default `question` route remains hidden from provider-visible routes in `full_auto`.

## Validation Run

- Focused:
  - `./.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py tests/runtime/test_provider_backends.py tests/runtime/test_workspace_and_context.py -k 'prompt_registry_roots or full_auto or pyyaml or nested_runtime_policy or load_runtime_config_file_without_pyyaml'`
- Audited slice:
  - `./.venv/bin/python -m pytest -q tests/runtime/test_runtime_static_graph.py tests/runtime/test_package_cli.py tests/test_architecture_baseline_docs.py tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py tests/contract/test_canonical_runtime_contracts.py tests/contract/test_engine_contracts.py tests/unit/test_simple_surface.py tests/unit/test_primitives_and_stores.py tests/unit/test_provider_boundary_core.py tests/unit/test_provider_retries.py tests/runtime/test_provider_backends.py tests/runtime/test_workspace_and_context.py`

## Preserved Invariants Checked

- The narrow config fallback still rejects malformed indentation.
- Prompt-root discovery still includes capability prompt directories outside the workflow package.
- `full_auto` route visibility remains unchanged while adding AC-2 coverage.

## Edge Cases / Failure Paths

- Nested runtime config with sibling mapping entries under no-PyYAML execution.
- Indented child under scalar config entry.
- Over-indented sibling mapping entry.
- Compiled step prompt specs represented as plain strings for both producer and verifier prompt paths.

## Flake Risk / Stabilization

- No timing or network dependencies.
- All coverage uses temporary filesystem paths and in-process providers only.

## Known Gaps

- No new end-to-end runner invocation test was added for plain-string prompt specs because the audited slice already exercises `run_workflow_package(...)`, and the direct regression risk in this phase is the prompt-root normalization helper the runner calls.
