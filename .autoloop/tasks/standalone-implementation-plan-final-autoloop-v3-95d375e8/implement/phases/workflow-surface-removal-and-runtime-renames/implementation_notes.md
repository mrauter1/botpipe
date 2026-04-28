# Implementation Notes

- Task ID: standalone-implementation-plan-final-autoloop-v3-95d375e8
- Pair: implement
- Phase ID: workflow-surface-removal-and-runtime-renames
- Phase Directory Key: workflow-surface-removal-and-runtime-renames
- Phase Title: Workflow Surface Removal And Runtime Renames
- Scope: phase-local producer artifact

## Files Changed

- Runtime/core surfaces: `core/workflow_catalog.py`, `core/workflow_capabilities.py`, `core/stores/protocols.py`, `core/context.py`, `core/validation.py`, `runtime/loader.py`, `runtime/cli.py`
- Stdlib callers: `stdlib/_selected_workflow.py`, `stdlib/company.py`, `stdlib/evaluation.py`, `stdlib/portfolio.py`
- Deleted surface: `workflow/` package removed
- Tests/docs: `tests/strictness/test_no_compat.py`, `tests/runtime/test_package_cli.py`, `tests/runtime/test_workflow_reference_resolution.py`, `tests/runtime/test_compatibility_runtime.py`, `tests/runtime/test_workflow_integration_parity.py`, `tests/runtime/test_workflow_package_to_composable_building_blocks.py`, `tests/unit/test_primitives_and_stores.py`, `tests/unit/test_stdlib_and_extensions.py`, `tests/contract/test_engine_contracts.py`, `tests/test_architecture_baseline_docs.py`, `cleanup.md`

## Symbols Touched

- `WorkflowCatalogEntry.workflow_py_path`
- `WorkflowCapabilityEntry.workflow_py_path`
- `_load_parameters_from_params_py(...)`
- `is_run_key_bound_to_slot(...)`
- `ResolvedWorkflow.reference` as the only origin surface

## Checklist Mapping

- Phase AC-1: ported active imports/callers away from `workflow`, deleted `workflow/`, rewrote strictness guards to path/regex scanning
- Phase AC-2: renamed payload/dataclass field to `workflow_py_path`, removed `ResolvedWorkflow.package`, updated CLI/capability/authoring/decomposition payload tests
- Phase AC-3: renamed run-key helper to `is_run_key_bound_to_slot` without changing normalization behavior

## Intended Behavior Changes

- Provider/runtime retry feedback assertions in contract tests now expect route-specific invalid-payload details when failure context supplies `route` and `error`
- Selected-workflow authoring/decomposition payloads now surface `workflow_py_path` alongside `workflow_path`
- Root `cleanup.md` is restored as the active docs note so the maintained docs baseline matches the requested greenfield surface

## Preserved Invariants

- `workflow_package` authoring-shape value remains unchanged
- Parameter resolution order remains class -> module -> package export -> `params.py` -> none
- Workflow-step execution behavior was not refactored; only strictness now guards against `_install_simple_workflow_step_handler`

## Known Non-Changes

- No compatibility shim was left behind for `workflow` or `ResolvedWorkflow.package`
- No `autoloop eject` or source-expansion command was added

## Validation Performed

- Targeted:
  - `.venv/bin/python -m pytest tests/unit/test_provider_retries.py`
  - `.venv/bin/python -m pytest tests/unit/test_simple_surface.py`
  - `.venv/bin/python -m pytest tests/strictness/test_no_compat.py`
  - `.venv/bin/python -m pytest tests/runtime/test_package_cli.py`
  - `.venv/bin/python -m pytest tests/runtime/test_workflow_reference_resolution.py`
- Additional focused proof:
  - `.venv/bin/python -m pytest tests/unit/test_primitives_and_stores.py tests/unit/test_stdlib_and_extensions.py tests/runtime/test_compatibility_runtime.py tests/runtime/test_workflow_integration_parity.py tests/test_architecture_baseline_docs.py`
  - `.venv/bin/python -m pytest tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - `.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -k 'provider_invalid_question_retries_and_recovers or provider_invalid_terminal_route_retries_and_recovers or llm_step_retries_invalid_payload_twice_and_succeeds_on_third_attempt or provider_after_hook_route_string_invalid_event_retries_and_recovers'`
- Final:
  - `.venv/bin/python -m pytest`
