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
- `tests/conftest.py`
- `tests/strictness/test_no_compat.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_workflow_builder_package.py`
- `tests/test_architecture_baseline_docs.py`
- `.autoloop/tasks/recursive-framework-evolution-20260423t150056-c1/decisions.txt`

## Symbols touched

- `RouteContract`
- `normalize_route_contract`
- `normalize_route_contracts`
- `infer_work_item_effect`
- `validate_workflow_definition`
- `_validate_control_contracts`
- `_compile_steps`
- `PACKAGE_ROOT` / `REPO_PARENT` path ordering in `tests/conftest.py`

## Checklist mapping

- Milestone 1 / Add a framework-owned `RouteContract` helper on the strict authoring surface: completed via `core/route_contracts.py`, `core/__init__.py`, and `workflow/__init__.py`.
- Milestone 1 / Normalize route-contract inputs in validation/compiler paths: completed via `core/validation.py` and `core/compiler.py`.
- Milestone 1 / Validate required artifact names while keeping mapping-style declarations additive: completed via centralized normalization plus new unit/runtime/strictness coverage.

## Assumptions

- Existing repo-owned workflow packages remain the backward-compatibility target for legacy mapping-style route contracts.
- The repo test harness should resolve the repo-local `workflow` shim before any parent-level workspace shim so the phase remains self-contained inside the repository root.

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
- No repo-owned behavior now depends on `../workflow/__init__.py`.

## Expected side effects

- Provider request payloads now include canonical `work_item_effect` values even when authors used legacy `state_effect` keys.
- Legacy `evidence` summary text is accepted as an authoring-time alias during normalization for backward compatibility tests.

## Validation performed

- `.venv/bin/python - <<'PY' ... import workflow; print(workflow.__file__) ... PY` -> resolves to repo-local `workflow/__init__.py`
- `.venv/bin/pytest -q tests/unit/test_validation.py tests/contract/test_engine_contracts.py tests/runtime/test_workflow_builder_package.py tests/unit/test_primitives_and_stores.py`
- `.venv/bin/pytest -q tests/strictness/test_no_compat.py -k 'workflow_shim_exports_only_the_strict_authoring_surface'`
- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py -k 'freezes_the_root_workflow_import_surface or explains_step_control_contract_boundaries'`

## Known residuals

- `tests/test_architecture_baseline_docs.py::test_recursive_memory_files_record_cycle_one_closeout_baseline` is already failing in the workspace because the current `.autoloop_recursive/` baseline content does not match that test's expectations; it is unrelated to this phase-local seam and was not pulled into scope.
- `tests/strictness/test_no_compat.py::test_active_tree_does_not_reintroduce_removed_compatibility_surfaces` is already failing in the workspace because the maintained tree currently contains legacy-token matches under `runtime/providers/_common.py` and template files; it is unrelated to this phase-local seam and was not pulled into scope.

## Deduplication / centralization decisions

- Route-contract coercion and artifact-name validation are centralized in `core/route_contracts.py` and reused by both validation and compilation to avoid drift between author-time checks and runtime payloads.
