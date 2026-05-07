# Implementation Notes

- Task ID: task-do-a-complete-cleanup-on-unneeded-stale-tes-48faefbd
- Pair: implement
- Phase ID: split-retained-monoliths
- Phase Directory Key: split-retained-monoliths
- Phase Title: Split Retained Monoliths
- Scope: phase-local producer artifact

## Files changed
- `tests/conftest.py`
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
- `tests/unit/extensions/test_git_and_session_paths.py`
- `tests/unit/optimizer/test_candidate_surfaces.py`
- `tests/unit/optimizer/test_portfolio_helpers.py`
- `tests/unit/optimizer/test_selected_workflow_helpers.py`
- `tests/unit/stdlib/test_authoring_helpers.py`
- `tests/unit/stdlib/test_composition_helpers.py`

## Symbols touched
- `collect_ignore` in `tests/conftest.py`
- Imported retained `test_*` symbols from `tests.contract.test_engine_contracts`
- Imported retained `test_*` symbols from `tests.unit.test_stdlib_and_extensions`

## Checklist mapping
- Milestone 3 / split `tests/unit/test_stdlib_and_extensions.py`: completed via `tests/unit/stdlib/`, `tests/unit/optimizer/`, and `tests/unit/extensions/` import-only split modules.
- Milestone 3 / split `tests/contract/test_engine_contracts.py`: completed via `tests/contract/engine/` import-only split modules.

## Assumptions
- A mechanical split is preferable to copying test bodies because the retained assertions already passed earlier cleanup and the phase scope forbids further semantic changes.

## Preserved invariants
- No retained test body, helper, fixture, or assertion logic changed.
- Shared tests still import from the same original module globals and helper functions.
- No repo-owned workflow/docs/recursive dependencies were reintroduced into shared tests.

## Intended behavior changes
- Pytest now collects the retained monolith coverage through smaller ownership-aligned module paths instead of directly collecting the two oversized source files.

## Known non-changes
- `tests/contract/test_engine_contracts.py` and `tests/unit/test_stdlib_and_extensions.py` remain on disk as import sources; they are no longer direct collection entrypoints.
- No product code, packaging config, or non-`tests/` files were changed for runtime behavior.

## Expected side effects
- Test node ids now point at `tests/contract/engine/*` and `tests/unit/{stdlib,optimizer,extensions}/*` for the moved coverage.

## Validation performed
- `.venv_phase/bin/pytest --collect-only tests/contract tests/unit -q` -> passed, `749 tests collected`

## Deduplication / centralization decisions
- Reused the original monolith modules as the single source of retained test function definitions to avoid helper drift, duplicated fixtures, and copy/paste maintenance debt during the split.
