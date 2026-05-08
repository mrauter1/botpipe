# Test Strategy

- Task ID: final-standalone-implementation-spec-shared-inhe-c4aa316d
- Pair: test
- Phase ID: regression-cleanup
- Phase Directory Key: regression-cleanup
- Phase Title: Regression Cleanup And Validation
- Scope: phase-local producer artifact

## Behavior-to-Test Coverage Map

- Export matrix and public facade contract:
  - `tests/unit/test_policy.py::test_public_policy_imports_and_all`
  - `tests/unit/test_simple_policy.py::test_policy_surface_exports_shared_policy_symbols`
  - `tests/unit/test_simple_policy.py::test_policy_input_export_matrix_matches_phase_contract`
  - `tests/unit/test_sdk_facade.py::test_sdk_public_exports_include_revised_sdk_surface`
- Enum validation and sparse inheriting `Policy(...)` semantics:
  - `tests/unit/test_policy.py::test_policy_rejects_raw_strings_for_enum_backed_fields`
  - `tests/unit/test_policy.py::test_policy_resolve_defaults_and_inheritance`
  - `tests/unit/test_policy.py::test_policy_same_layer_validation_and_dangerous_access`
  - `tests/unit/test_policy.py::test_resolve_policy_layer_accepts_policy_inputs_and_detects_cycles`
- Dangerous access and preserved core compatibility:
  - `tests/unit/test_policy.py::test_compile_and_resolve_dangerous_manual_workflow_policy`
  - `tests/unit/test_policy.py::test_dangerous_manual_policy_preserves_non_full_auto_base_permissions`
  - `tests/runtime/test_provider_policy_steps.py`
  - `tests/runtime/test_provider_policy_emitters.py`
- Workspace-vs-state-root path semantics and SDK policy precedence:
  - `tests/runtime/test_sdk_policy.py::test_sdk_run_policy_overrides_sdk_default_policy_for_workflow_steps`
  - `tests/runtime/test_sdk_policy.py::test_sdk_direct_operations_inherit_sdk_default_policy_and_apply_explicit_overrides`
  - `tests/runtime/test_sdk_policy.py::test_sdk_step_invocation_policy_is_local_and_does_not_mutate_reused_step`
  - `tests/runtime/test_sdk_policy.py::test_sdk_inline_operations_apply_runtime_sdk_workflow_run_step_and_explicit_layers`
  - `tests/runtime/test_sdk_policy.py::test_sdk_workspace_root_stays_distinct_from_state_root_for_policy_relative_paths`
- Removed SDK compatibility paths:
  - `tests/unit/test_sdk_facade.py::test_sdk_constructor_uses_workspace_and_rejects_root_keyword`
  - `tests/unit/test_sdk_facade.py::test_sdk_run_rejects_removed_typed_input_and_parameters_keywords`
- Docstrings and public-surface wording:
  - `tests/unit/test_policy.py::test_policy_docstring_describes_sparse_inheriting_public_contract`
  - `tests/unit/test_sdk_facade.py::test_sdk_public_docstrings_encode_workspace_policy_and_runtime_behavior_contract`
  - Direct operation docstrings for `Autoloop.llm()` and `Autoloop.classify()` are pinned in the same SDK facade docstring test.

## Preserved Invariants Checked

- No public `PolicyOverride` re-export or import path is restored.
- `workspace` remains the public project root while `.autoloop` remains state storage.
- `input` and `params` remain the only public SDK names for typed input and workflow parameters.
- Simple-style `writes=(Md(...), Json(...), Text(...), Raw(...))` remains the public helper vocabulary.

## Edge Cases / Failure Paths

- Raw strings passed to enum-backed `Policy(...)` fields raise `TypeError`.
- Invalid same-layer dangerous or read-only/write combinations raise `ValueError`.
- `client.step(..., policy=...)` does not mutate reused step objects.
- Removed public keywords `root=`, `typed_input=`, and `parameters=` fail fast.

## Stabilization / Flake Controls

- All added coverage is deterministic and uses existing fake/scripted providers.
- No timing, network, or nondeterministic ordering assertions were introduced.

## Validation Performed

- `.venv/bin/pytest tests/unit/test_sdk_facade.py tests/unit/test_policy.py tests/runtime/test_sdk_policy.py tests/unit/test_simple_surface.py -q`
- `.venv/bin/pytest tests/unit/test_provider_policy.py tests/runtime/test_provider_policy_steps.py tests/runtime/test_provider_policy_emitters.py tests/runtime/test_provider_policy_config.py tests/unit/test_simple_surface.py tests/unit/test_sdk_facade.py tests/unit/test_policy.py tests/runtime/test_sdk_policy.py -q`

## Validation Results

- Focused rerun after the direct-operation docstring assertions: `155 passed`
- Required targeted suites: `212 passed`

## Known Gaps

- None in phase scope; broader CLI/config documentation migration remains intentionally out of scope for this phase.
