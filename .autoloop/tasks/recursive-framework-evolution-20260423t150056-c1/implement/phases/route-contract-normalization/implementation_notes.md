# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t150056-c1
- Pair: implement
- Phase ID: route-contract-normalization
- Phase Directory Key: route-contract-normalization
- Phase Title: Normalize Route Contracts
- Scope: phase-local producer artifact

## Files changed

- `core/route_contracts.py`
- `core/__init__.py`
- `core/steps.py`
- `core/compiler.py`
- `core/validation.py`
- `workflow/__init__.py`
- `docs/authoring.md`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_workflow_builder_package.py`
- `tests/test_architecture_baseline_docs.py`
- `../workflow/__init__.py` (workspace-level strict shim required by the active test import path)
- `.autoloop/tasks/recursive-framework-evolution-20260423t150056-c1/decisions.txt`

## Symbols touched

- `RouteContract`
- `normalize_route_contract`
- `normalize_route_contracts`
- `infer_work_item_effect`
- `validate_workflow_definition`
- `_validate_control_contracts`
- `_compile_steps`

## Checklist mapping

- Milestone 1 / Add a framework-owned `RouteContract` helper on the strict authoring surface: completed via `core/route_contracts.py`, `core/__init__.py`, `workflow/__init__.py`, and the sibling workspace shim.
- Milestone 1 / Normalize route-contract inputs in validation/compiler paths: completed via `core/validation.py` and `core/compiler.py`.
- Milestone 1 / Validate required artifact names while keeping mapping-style declarations additive: completed via centralized normalization plus new unit/runtime coverage.

## Assumptions

- Existing repo-owned workflow packages remain the backward-compatibility target for legacy mapping-style route contracts.
- The current test/runtime environment resolves `workflow` from the sibling workspace shim before the repo-local shim, so both surfaces must export `RouteContract`.

## Preserved invariants

- Runtime-injected provider control data remains limited to `expected_output_schema`, `available_routes`, and `route_contracts`.
- `SystemStep` still rejects step control contracts.
- Existing mapping-style route contracts continue to compile for repo-owned packages such as `workflow_idea_to_workflow_package`.

## Intended behavior changes

- Provider-owned steps may now declare typed `RouteContract` helpers instead of raw dicts.
- Compiled/runtime route contracts now normalize to canonical keys: `summary`, `required_artifacts`, and `work_item_effect`.
- Validation now rejects route contracts that reference artifact names outside the known workflow artifact inventory.

## Known non-changes

- No CLI syntax changes.
- No release-workflow package work in this phase.
- No recursive memory file updates in this phase.
- No refactor of existing workflow package route-contract declarations; the builder package stays on legacy mapping input to prove backward compatibility.

## Expected side effects

- Provider request payloads now include canonical `work_item_effect` values even when authors used legacy `state_effect` keys.
- Legacy `evidence` summary text is accepted as an authoring-time alias during normalization for backward compatibility tests.

## Validation performed

- `.venv/bin/pytest -q tests/unit/test_validation.py`
- `.venv/bin/pytest -q tests/contract/test_engine_contracts.py`
- `.venv/bin/pytest -q tests/runtime/test_workflow_builder_package.py`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py -k 'freezes_the_root_workflow_import_surface or explains_step_control_contract_boundaries'`

## Known residuals

- `tests/test_architecture_baseline_docs.py::test_recursive_memory_files_record_cycle_one_closeout_baseline` is already failing in the workspace because the current `.autoloop_recursive/` baseline content does not match that test's expectations; it is unrelated to this phase-local seam and was not pulled into scope.

## Deduplication / centralization decisions

- Route-contract coercion and artifact-name validation are centralized in `core/route_contracts.py` and reused by both validation and compilation to avoid drift between author-time checks and runtime payloads.
