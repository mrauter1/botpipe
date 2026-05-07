# Implementation Notes

- Task ID: task-do-a-complete-cleanup-on-unneeded-stale-tes-48faefbd
- Pair: implement
- Phase ID: unblock-shared-suite
- Phase Directory Key: unblock-shared-suite
- Phase Title: Unblock Shared Suite
- Scope: phase-local producer artifact

## Files changed
- Deleted `tests/runtime/test_workflow_integration_parity.py`
- Deleted `tests/test_architecture_baseline_docs.py`
- Updated `tests/runtime/test_wheel_packaging_smoke.py`
- Updated `tests/runtime/test_package_cli.py`
- Updated `tests/contract/test_engine_contracts.py`
- Updated `tests/unit/test_simple_surface.py`
- Updated `tests/unit/test_stdlib_and_extensions.py`
- Updated `tests/unit/test_optimization_helpers.py`

## Symbols touched
- `test_built_wheel_installs_public_autoloop_package_and_cli`
- removed recursive-wrapper assertions from `tests/runtime/test_package_cli.py`
- removed `test_ctx_runtime_prompt_docs_describe_preferred_bindings_and_snapshot_semantics`
- removed bundled-workflow export/discovery assertions from `tests/unit/test_simple_surface.py`
- local `JsonArtifactSpec` fixtures and helper models in `tests/unit/test_stdlib_and_extensions.py`
- `_install_selected_workflow()` in `tests/unit/test_optimization_helpers.py`

## Checklist mapping
- Milestone 1: completed for parity/docs file deletion, wheel smoke rewrite, recursive-wrapper assertion removal, docs-text assertion removal, bundled-workflow export assertion removal, and top-level workflow contract import replacement.
- Milestone 2+: intentionally not started here for workflow-package suite removal, strictness narrowing, or monolith splitting.

## Assumptions
- Repo-owned workflow, recursive, and docs coverage may exist in the checkout but should not remain under `tests/` when it is clearly misowned for the shared suite.
- Shared tests may still use canonical `autoloop/workflows/...` labels when those labels come from synthetic fixtures under `tmp_path`.

## Preserved invariants
- No product code or non-test repo paths were changed.
- Shared runtime/catalog/workspace behavior remains covered through generated fixtures.
- Wheel smoke coverage still exercises build/install plus public CLI/import behavior.

## Intended behavior changes
- Shared test collection no longer depends on importing repo-owned workflow contract modules from `autoloop.workflows.*`.
- Shared tests no longer assert parity-v1, repo-doc baseline, or recursive-wrapper coverage from `tests/`.
- Shared optimizer fixture setup no longer copies repo workflow/docs trees and instead creates a local synthetic selected workflow package.

## Known non-changes
- Workflow-owned runtime package suites were not moved or deleted in this phase.
- `tests/strictness/test_no_compat.py` was not narrowed in this phase.
- Large-file splits for `test_engine_contracts.py` and `test_stdlib_and_extensions.py` were deferred.

## Expected side effects
- `pytest --collect-only tests` should no longer fail on missing `autoloop.workflows.*.contracts` imports.
- The touched shared tests now reflect current route snapshots that expose `question` without the older implicit `blocked`/`failed` expectation in those helper-generated fixtures.

## Validation performed
- `python3 -m py_compile tests/runtime/test_wheel_packaging_smoke.py tests/runtime/test_package_cli.py tests/contract/test_engine_contracts.py tests/unit/test_simple_surface.py tests/unit/test_stdlib_and_extensions.py tests/unit/test_optimization_helpers.py`
- `.venv/bin/python -m pytest --collect-only tests`
- `.venv/bin/python -m pytest tests/runtime/test_wheel_packaging_smoke.py tests/runtime/test_package_cli.py tests/contract/test_engine_contracts.py tests/unit/test_simple_surface.py tests/unit/test_stdlib_and_extensions.py tests/unit/test_optimization_helpers.py -q`

## Deduplication / centralization
- Kept the local shared artifact-spec replacements in one file instead of importing workflow-owned contracts from repo packages.
