Finish the workflow-installation/discovery migration by closing the remaining validation gaps.

Required follow-up:

- Update `tests/runtime/test_workflow_reference_resolution.py` so it matches the shipped workflow contract:
  - bare names and aliases resolve only from `autoloop/workflows/` and `{workspace}/.autoloop/workflows/`
  - `{workspace}/workflows/` is covered only through explicit filesystem-path references, not implicit bare-name discovery
  - workspace-isolated module assertions use the `_autoloop_workspace_workflows.<hash>...` namespace
- Make `tests/runtime/test_wheel_packaging_smoke.py` runnable in the standard project validation environment. It currently fails because `python -m build` cannot import the `build` module.
- Rerun the affected runtime and packaging suites and confirm they pass:
  - `tests/runtime/test_workflow_reference_resolution.py`
  - `tests/runtime/test_workflow_catalog_roots.py`
  - `tests/runtime/test_runtime_cli_metadata_integration.py`
  - `tests/runtime/test_package_cli.py`
  - `tests/runtime/test_wheel_packaging_smoke.py`

Acceptance for the follow-up:

- No test still expects implicit bare-name discovery from `{workspace}/workflows/`.
- Wheel-build smoke verification passes in the normal validation environment.
- The affected suite is green without relying on legacy discovery behavior.
