## Original intent considered

- Implement workflow discovery from exactly two first-class roots: `autoloop/workflows/` and `{workspace}/.autoloop/workflows/`.
- Give workspace workflows precedence over package workflows for bare names and aliases.
- Remove implicit bare-name discovery from `{workspace}/workflows/` while still allowing explicit filesystem path references.
- Persist normalized workflow-origin metadata with `source_root_kind` limited to `"workspace"` or `"package"`.
- Update CLI/help/scaffolding, package data, docs, and tests so the migrated behavior is the default shipped contract.
- Satisfy the explicit acceptance criterion that all tests pass, including wheel-build verification.

## Clarifications / superseding decisions

- `decisions.txt` block 1 explicitly removed compatibility with implicit bare-name discovery from `{workspace}/workflows/` and required package imports under `autoloop.workflows.*`.
- `decisions.txt` block 2 explicitly required explicit `.py` and `.toml` path handling plus normalized origin metadata for out-of-root workflows.
- `decisions.txt` blocks 6 and 19 document that focused phase-local tests were added instead of rewriting the broader legacy workflow-path suites during implementation. That explains the implementation path, but it does not supersede the original acceptance criterion that all tests pass.
- No later clarification removed the requested wheel-build verification or authorized leaving legacy test suites contradictory to the new discovery contract.

## Implemented behavior

- Built-in workflows now live under `autoloop/workflows/`, and there is no top-level repository `workflows/` directory anymore.
- `autoloop/core/workflow_catalog.py` now defines `WorkflowSearchRoot`, `workspace_workflows_root()`, `package_workflows_root()`, and `workflow_search_roots()`, and `discover_workflow_catalog()` scans only `.autoloop/workflows` plus `autoloop/workflows`.
- `autoloop/runtime/loader.py` resolves bare names through the effective catalog, preserves workspace-over-package precedence, supports explicit `.py` and `.toml` path references, and loads workspace packages under isolated `_autoloop_workspace_workflows.<hash>...` module names.
- `autoloop/runtime/cli.py` help text, workflow scaffolding, `workflows list`, and `workflows show` all reflect the new roots and origin metadata fields.
- `pyproject.toml`, `MANIFEST.in`, `autoloop/workflows/__init__.py`, and the built-in workflow packages were updated to ship package-installed workflows and assets through `autoloop.workflows`.
- Focused migrated suites are substantially green. Running `.venv_phase/bin/python -m pytest tests/runtime/test_workflow_catalog_roots.py tests/runtime/test_runtime_cli_metadata_integration.py tests/runtime/test_package_cli.py tests/runtime/test_wheel_packaging_smoke.py -q` produced 47 passing tests before one wheel-smoke failure.

## Unresolved gaps

1. The legacy runtime reference-resolution suite still contradicts the new no-legacy-discovery contract, so the repo does not meet the requested "all tests pass" finish line.
   Evidence:
   - `.venv_phase/bin/python -m pytest tests/runtime/test_workflow_reference_resolution.py -q` failed with 6 failures and 5 passes.
   - `tests/runtime/test_workflow_reference_resolution.py:164-166`, `:235-238`, and `:260-263` still expect bare-name discovery from `{workspace}/workflows/`, which the request explicitly forbids.
   - `tests/runtime/test_workflow_reference_resolution.py:111` and `:578` still expect the old `_autoloop_dynamic_` isolated-module prefix instead of the requested `_autoloop_workspace_workflows.<hash>...` namespace.
   - `tests/runtime/test_workflow_reference_resolution.py:421-422` still expects duplicate-name behavior rooted in the removed legacy bare-discovery path rather than the new catalog roots.

2. Wheel-build validation is still not reproducible in the run validation environment, so the wheel-install acceptance criterion is not actually closed.
   Evidence:
   - `.venv_phase/bin/python -m pytest tests/runtime/test_wheel_packaging_smoke.py -q` failed in `tests/runtime/test_wheel_packaging_smoke.py:30` with `No module named build`.
   - The smoke test requires `python -m build`, but the repo's validation environment used for this run does not provision the `build` module, so the requested wheel-build verification cannot complete there.

## Differences justified by later clarification or analysis

- The runtime now treats explicit `.py` and `.toml` references outside the canonical roots as filesystem workflows with `source_root_kind="workspace"` and null package/workflow module metadata. That matches the original request and `decisions.txt` block 2.
- Workspace package loading now uses isolated `_autoloop_workspace_workflows.<hash>...` module names rather than the older `_autoloop_dynamic_...` naming. That is consistent with the original request's workspace import behavior and is therefore a justified behavior change; the stale legacy tests are the part that remains wrong.
- Package-installed workflows still use `workflow.py` in many built-ins. That is acceptable because the request allowed `workflow.py` as an alternative to `flow.py`, while only requiring scaffolds and docs to prefer `flow.py`.

## Recommended next run

- Update the remaining legacy runtime tests so they match the shipped contract: no bare-name discovery from `{workspace}/workflows/`, explicit-path-only coverage for arbitrary filesystem workflows, and `_autoloop_workspace_workflows...` namespace assertions.
- Make wheel-build smoke verification reproducible in the standard project validation environment by ensuring the `build` tool is available when `tests/runtime/test_wheel_packaging_smoke.py` runs, then rerun that smoke test.
- Rerun the affected suites at minimum:
  - `tests/runtime/test_workflow_reference_resolution.py`
  - `tests/runtime/test_workflow_catalog_roots.py`
  - `tests/runtime/test_runtime_cli_metadata_integration.py`
  - `tests/runtime/test_package_cli.py`
  - `tests/runtime/test_wheel_packaging_smoke.py`
