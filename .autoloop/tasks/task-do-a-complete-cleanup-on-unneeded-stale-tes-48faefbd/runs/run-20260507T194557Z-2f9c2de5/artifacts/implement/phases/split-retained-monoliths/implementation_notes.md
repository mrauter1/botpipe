# Implementation Notes

- Task ID: task-do-a-complete-cleanup-on-unneeded-stale-tes-48faefbd
- Pair: implement
- Phase ID: split-retained-monoliths
- Phase Directory Key: split-retained-monoliths
- Phase Title: Split Retained Monoliths
- Scope: phase-local producer artifact

## Files changed
- `tests/conftest.py`
- `tests/contract/engine/_shared.py`
- `tests/contract/engine/test_artifacts.py`
- `tests/contract/engine/test_child_workflows.py`
- `tests/contract/engine/test_core_contracts.py`
- `tests/contract/engine/test_errors_and_retries.py`
- `tests/contract/engine/test_hooks.py`
- `tests/contract/engine/test_prompt_context.py`
- `tests/contract/engine/test_routes.py`
- `tests/contract/engine/test_runtime_controls.py`
- `tests/contract/engine/test_sessions.py`
- `tests/contract/engine/test_worklists.py`
- `tests/contract/test_engine_contracts.py` (removed)
- `tests/unit/_stdlib_and_extensions_shared.py`
- `tests/unit/extensions/test_git_and_session_paths.py`
- `tests/unit/optimizer/test_candidate_surfaces.py`
- `tests/unit/optimizer/test_portfolio_helpers.py`
- `tests/unit/optimizer/test_selected_workflow_helpers.py`
- `tests/unit/stdlib/test_authoring_helpers.py`
- `tests/unit/stdlib/test_composition_helpers.py`
- `tests/unit/test_stdlib_and_extensions.py` (removed)

## Symbols touched
- Shared helper modules `tests.contract.engine._shared` and `tests.unit._stdlib_and_extensions_shared`
- Retained `test_*` definitions moved into the split modules under `tests/contract/engine/` and `tests/unit/{stdlib,optimizer,extensions}/`

## Checklist mapping
- Milestone 3 / split `tests/unit/test_stdlib_and_extensions.py`: completed via source-level moves into `tests/unit/stdlib/`, `tests/unit/optimizer/`, and `tests/unit/extensions/`.
- Milestone 3 / split `tests/contract/test_engine_contracts.py`: completed via source-level moves into `tests/contract/engine/`.

## Assumptions
- A mechanical source split remains safest when the moved tests continue to share the original non-test imports and helper definitions from dedicated `_shared.py` modules.

## Preserved invariants
- No retained test body, helper semantics, fixture semantics, or assertion logic changed intentionally.
- Shared tests still use the same non-test imports, constants, classes, and helper functions, now centralized in `_shared.py` modules instead of hidden collected monoliths.
- No repo-owned workflow/docs/recursive dependencies were reintroduced into shared tests.

## Intended behavior changes
- Pytest now collects the retained coverage from real smaller ownership-aligned source modules, not wrapper modules or ignored monolith entrypoints.

## Known non-changes
- The moved tests still preserve their original names and assertions; only file ownership changed.
- No product code, packaging config, or non-`tests/` files were changed for runtime behavior.

## Expected side effects
- Test node ids point at `tests/contract/engine/*` and `tests/unit/{stdlib,optimizer,extensions}/*`.
- Future retained tests added in the split areas are collected directly from their owned files without relying on `collect_ignore`.

## Validation performed
- `.venv_phase/bin/pytest --collect-only tests/contract tests/unit -q` -> passed, `749 tests collected`

## Deduplication / centralization decisions
- Centralized only shared non-test module scaffolding into `_shared.py` modules and moved every retained `test_*` definition into its owned split file to avoid hidden collection gaps while keeping helper sharing mechanical.
