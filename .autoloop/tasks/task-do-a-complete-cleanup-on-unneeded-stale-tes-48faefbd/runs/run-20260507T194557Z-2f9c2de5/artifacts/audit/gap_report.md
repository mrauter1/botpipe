# Original intent considered

- Clean up stale or out-of-scope tests under `tests/` only.
- Remove coverage for repo-owned docs, recursive wrapper assets, autoloop v1 parity, and repo-owned workflow-package suites from `tests/`.
- Keep shared framework/runtime/SDK/stdlib/optimizer coverage, including workflow-related tests that build synthetic fixtures under `tmp_path`.
- Split the retained monoliths `tests/contract/test_engine_contracts.py` and `tests/unit/test_stdlib_and_extensions.py` after stale coverage was removed.

# Clarifications / superseding decisions

- The human clarification in `decisions.txt` says the repo roots `autoloop/workflows`, `docs`, and `recursive_autoloop` may exist, but tests for those owned surfaces should not remain under `tests/`.
- The planner decision explicitly superseded the earlier “optional suite” idea: misowned workflow-package, recursive, and docs coverage should be removed from `tests/`, not preserved there behind markers.
- Later implementation decisions recorded that:
  - the 15 repo-owned workflow runtime suites were removed from `tests/runtime`,
  - strictness scanning was narrowed to maintained shared roots,
  - the retained monoliths were then split into `tests/contract/engine/` and `tests/unit/{stdlib,optimizer,extensions}/`.

# Implemented behavior

- The clearly stale files were removed from `tests/`:
  - `tests/runtime/test_workflow_integration_parity.py`
  - `tests/test_architecture_baseline_docs.py`
  - the 15 repo-owned workflow runtime suites listed in the request are no longer present under `tests/runtime/`
- `tests/runtime/test_wheel_packaging_smoke.py` was rewritten to check wheel build/install, CLI help, and public `autoloop` imports instead of packaged workflow assets.
- `tests/runtime/test_package_cli.py` no longer contains the recursive-wrapper coverage called out in the request.
- `tests/strictness/test_no_compat.py` was narrowed away from scanning `docs/`, `recursive_autoloop/`, and `autoloop/workflows/`.
- The retained monoliths were replaced by split modules plus helper files:
  - `tests/contract/engine/_shared.py` and `tests/contract/engine/test_*.py`
  - `tests/unit/_stdlib_and_extensions_shared.py` and `tests/unit/{stdlib,optimizer,extensions}/test_*.py`

# Unresolved gaps

- The final source-level split is materially broken and leaves the retained shared suite failing.
  - Evidence: `tests/contract/engine/test_artifacts.py:3` and `tests/unit/stdlib/test_authoring_helpers.py:3` use `from ... import *`.
  - Their needed helpers are underscore-prefixed in shared modules, e.g. `_chain_hooks` and `_workspace` in `tests/contract/engine/_shared.py:43` and `:56`, and `_build_lifecycle_context` in `tests/unit/_stdlib_and_extensions_shared.py:210`.
  - Python star imports do not import underscore-prefixed names by default, which matches the observed failures.
  - Validation on the current tree: `.venv/bin/python -m pytest tests/contract tests/unit -q` failed with `242 failed, 507 passed`. The first failures are `NameError` for `_workspace`, `_chain_hooks`, and `_build_lifecycle_context`.

- `tests/strictness/test_no_compat.py` was not fully updated for the split and now asserts a deleted path still exists.
  - Evidence: `tests/strictness/test_no_compat.py:155` still requires `"tests/contract/test_engine_contracts.py"` to be in the scanned path set even though that file was removed by the split.
  - Validation: `.venv/bin/python -m pytest tests/strictness/test_no_compat.py tests/unit/stdlib/test_authoring_helpers.py -q` fails on that assertion.

- One retained stdlib split file still depends directly on repo-owned workflow package modules, contrary to the clarified ownership boundary for surviving shared tests.
  - Evidence: `tests/unit/stdlib/test_authoring_helpers.py:235-239` imports
    - `autoloop.workflows.workflow_and_eval_to_refined_workflow_package.params`
    - `autoloop.workflows.workflow_package_to_composable_building_blocks.params`
  - The accepted direction for surviving shared tests was to use local/synthetic fixtures instead of repo-owned workflow-package modules.

# Differences justified by later clarification or analysis

- Removing the 15 workflow-package runtime suites from `tests/runtime` instead of moving them into an optional suite is justified by the later clarification that workflow-owned tests should not stay under `tests/` at all.
- Removing docs-owned and recursive-wrapper coverage from `tests/` is justified by the same ownership clarification.
- Rewriting `tests/runtime/test_wheel_packaging_smoke.py` to stop asserting packaged workflow assets is aligned with the original request and the later implementation decision to keep the wheel smoke focused on the shared public package/CLI contract.

# Recommended next run

- Repair the retained source split under `tests/contract/engine/` and `tests/unit/{stdlib,optimizer,extensions}/` so the moved tests import all required helpers without relying on star-import behavior for underscore-prefixed names.
- Update `tests/strictness/test_no_compat.py` to assert against the current split file layout rather than the removed monolith path.
- Remove the remaining direct imports of repo-owned `autoloop.workflows.*` modules from retained shared tests, starting with `tests/unit/stdlib/test_authoring_helpers.py`, and replace them with local/synthetic parameter models or fixtures.
- Re-run at least `.venv/bin/python -m pytest tests/strictness/test_no_compat.py tests/contract tests/unit -q` and keep the cleanup limited to `tests/`.
