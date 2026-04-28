# Test Strategy

- Task ID: standalone-implementation-plan-final-autoloop-v3-95d375e8
- Pair: test
- Phase ID: workflow-surface-removal-and-runtime-renames
- Phase Directory Key: workflow-surface-removal-and-runtime-renames
- Phase Title: Workflow Surface Removal And Runtime Renames
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Deleted `workflow/` surface:
  - `tests/strictness/test_no_compat.py` asserts `repo_root / "workflow"` does not exist, forbids deleted import forms by regex, and forbids the removed compatibility symbols.
  - `tests/unit/test_primitives_and_stores.py` now validates the public `autoloop` / `autoloop.simple` primitive surface instead of the deleted shim.
- Renamed runtime/public payload field:
  - `tests/runtime/test_package_cli.py` checks CLI `workflows show` exposes `workflow_py_path` and omits the removed field.
  - `tests/unit/test_stdlib_and_extensions.py` checks capability, authoring-surface, and decomposition-surface payloads for `workflow_py_path` and repo-relative variants.
- `ResolvedWorkflow.reference` as the only origin surface:
  - `tests/runtime/test_workflow_reference_resolution.py` asserts `ResolvedWorkflow` no longer exposes `package`.
  - `tests/runtime/test_compatibility_runtime.py`, `tests/runtime/test_workflow_integration_parity.py`, and `tests/runtime/test_workflow_package_to_composable_building_blocks.py` pin updated caller behavior through `reference`.
- Run-key helper rename with preserved behavior:
  - `tests/unit/test_primitives_and_stores.py` and `tests/runtime/test_compatibility_runtime.py` cover session-key normalization/resume behavior after the helper rename.
- Route-specific retry feedback after invalid provider payloads:
  - `tests/unit/test_provider_retries.py` covers direct formatter behavior for question/failed/generic invalid-payload cases.
  - `tests/contract/test_engine_contracts.py` covers end-to-end retries for `question`, `blocked`, `failed`, typed `done` payload validation, and provider-attributable after-hook invalid events.
- Active docs baseline:
  - `tests/test_architecture_baseline_docs.py` keeps `cleanup.md` authoritative and verifies the greenfield `autoloop` / `autoloop.simple` wording.

## Preserved Invariants Checked

- `workflow_package` authoring-shape stays valid while the obsolete top-level `workflow` package is removed.
- Parameter resolution order still falls through to `params.py`.
- No workflow-step generated-handler helper is reintroduced.

## Edge Cases / Failure Paths

- Missing `question` / `reason` fields on terminal routes produce specific retry guidance.
- Optional authoring-surface paths remain `None` when absent while still surfacing `workflow_py_path`.
- Strictness scanning excludes legacy docs and self-references while still catching active regressions.

## Validation

- Targeted suites:
  - `.venv/bin/python -m pytest tests/unit/test_provider_retries.py`
  - `.venv/bin/python -m pytest tests/unit/test_simple_surface.py`
  - `.venv/bin/python -m pytest tests/strictness/test_no_compat.py`
  - `.venv/bin/python -m pytest tests/runtime/test_package_cli.py`
  - `.venv/bin/python -m pytest tests/runtime/test_workflow_reference_resolution.py`
- Focused follow-up:
  - `.venv/bin/python -m pytest tests/unit/test_primitives_and_stores.py tests/unit/test_stdlib_and_extensions.py tests/runtime/test_compatibility_runtime.py tests/runtime/test_workflow_integration_parity.py tests/test_architecture_baseline_docs.py`
  - `.venv/bin/python -m pytest tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - `.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -k 'provider_invalid_question_retries_and_recovers or provider_invalid_terminal_route_retries_and_recovers or llm_step_retries_invalid_payload_twice_and_succeeds_on_third_attempt or provider_after_hook_route_string_invalid_event_retries_and_recovers'`
- Final proof:
  - `.venv/bin/python -m pytest`

## Known Gaps

- No known gaps for the scoped behavior after the passing full-suite proof run.
