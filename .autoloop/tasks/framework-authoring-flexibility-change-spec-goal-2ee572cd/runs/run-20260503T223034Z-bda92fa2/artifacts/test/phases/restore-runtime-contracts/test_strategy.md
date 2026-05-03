# Test Strategy

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: test
- Phase ID: restore-runtime-contracts
- Phase Directory Key: restore-runtime-contracts
- Phase Title: Restore Runtime Contracts
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- AC-1 payload placeholder happy path:
  - `tests/contract/test_engine_contracts.py::test_prompt_runtime_lazily_renders_item_and_worklist_placeholders`
  - Covers `{item.payload.foo}` and `{worklist.gate.current.payload.foo}` rendering from the same scoped item.
- AC-1 payload placeholder failure path:
  - `tests/contract/test_engine_contracts.py::test_prompt_runtime_reports_missing_payload_path_with_placeholder_context`
  - `tests/contract/test_engine_contracts.py::test_prompt_runtime_reports_missing_worklist_current_payload_path_with_placeholder_context`
  - Preserves placeholder-specific missing-path `WorkflowExecutionError` wording.
- AC-2 stable route ordering:
  - Existing route-order assertions remain in `tests/contract/test_engine_contracts.py` and `tests/unit/test_validation.py`.
  - No new ordering fixture was added in this turn because the shipped assertions already pin the authored-step, authored-global, runtime-control order.
- Runtime config fallback failure paths:
  - `tests/runtime/test_provider_backends.py::test_load_runtime_config_file_without_pyyaml_rejects_indented_child_under_scalar`
  - `tests/runtime/test_provider_backends.py::test_load_runtime_config_file_without_pyyaml_rejects_overindented_sibling_mapping`
  - These stabilize the reviewer-found malformed-indentation regressions.
- Runtime config fallback happy path:
  - `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_reads_valid_nested_runtime_policy_without_pyyaml`
  - Intentionally asserts that valid nested sibling mappings under `runtime` still load without PyYAML.

## Preserved Invariants Checked

- `worklist.<name>.current.payload.<path>` keeps the same late-bound semantics as `item.payload.<path>`.
- Missing payload-path failures stay placeholder-specific instead of degrading to generic lookup errors.
- `{item.payload.<path>}` and `{worklist.<name>.current.payload.<path>}` now each have direct failure-path assertions, so worklist-current placeholder regressions cannot hide behind the item-scoped path.
- The no-PyYAML fallback must reject malformed indentation without narrowing the supported mapping/scalar config surface.

## Edge Cases / Failure Paths

- Malformed nested keys under scalar parents
- Over-indented sibling mappings
- Scoped prompt rendering from mapping-backed worklist item envelopes
- Missing nested payload paths on both item-scoped and worklist-current placeholder forms

## Flake Risk / Stabilization

- Tests are deterministic and filesystem-local only.
- No timing, network, subprocess capability probing, or nondeterministic ordering was introduced beyond existing stable fixtures.

## Known Gaps

- `test_resolve_runtime_config_reads_valid_nested_runtime_policy_without_pyyaml` currently fails against the present implementation, which indicates the fallback parser still rejects a valid nested sibling mapping shape under `runtime`. This is an implementation gap, not an accepted contract change, so the test intentionally preserves the expected happy path.
