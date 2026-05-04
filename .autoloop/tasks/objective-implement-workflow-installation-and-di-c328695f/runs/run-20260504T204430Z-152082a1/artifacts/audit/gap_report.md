# Gap Report

## Original intent considered

- Finish the workflow-installation/discovery migration by closing the remaining validation gaps from `request.md`.
- Update `tests/runtime/test_workflow_reference_resolution.py` so bare names and aliases resolve only from `autoloop/workflows/` and `{workspace}/.autoloop/workflows/`, while `{workspace}/workflows/` is exercised only through explicit filesystem-path references.
- Ensure workspace-isolated module assertions use `_autoloop_workspace_workflows.<hash>...`.
- Make `tests/runtime/test_wheel_packaging_smoke.py` runnable in the standard validation environment without relying on `python -m build`.
- Re-run:
  - `tests/runtime/test_workflow_reference_resolution.py`
  - `tests/runtime/test_workflow_catalog_roots.py`
  - `tests/runtime/test_runtime_cli_metadata_integration.py`
  - `tests/runtime/test_package_cli.py`
  - `tests/runtime/test_wheel_packaging_smoke.py`

## Clarifications / superseding decisions

- `decisions.txt` block 1 narrowed discovery to `autoloop/workflows/` and `{workspace}/.autoloop/workflows/`, with `{workspace}/workflows/` explicit-path-only.
- `decisions.txt` block 2 superseded the earlier wording to make `{workspace}/workflows/` strictly filesystem-path-only, including removal or relocation of `workflows.*` workspace-module expectations.
- `decisions.txt` block 3 recorded the accepted wheel-smoke fix: use `python -m pip wheel --no-deps --wheel-dir <dist> .` instead of depending on an ambient `build` module.

## Implemented behavior

- The shipped discovery roots remain only workspace catalog and package roots in [autoloop/core/workflow_catalog.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/workflow_catalog.py:78) and [autoloop/core/workflow_catalog.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/workflow_catalog.py:86).
- Explicit workspace-path imports continue to synthesize hashed `_autoloop_workspace_workflows.<hash>...` namespaces in [autoloop/runtime/loader.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/loader.py:1143) and [autoloop/runtime/loader.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/loader.py:1179).
- `test_workflow_reference_resolution.py` now resolves bare names from the workspace catalog root and explicit path references from `{workspace}/workflows/` separately:
  - named discovery comes from `.autoloop/workflows` in [tests/runtime/test_workflow_reference_resolution.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_workflow_reference_resolution.py:193) and [tests/runtime/test_workflow_reference_resolution.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_workflow_reference_resolution.py:294)
  - alias coverage now proves `{workspace}/workflows/` does not provide implicit alias discovery in [tests/runtime/test_workflow_reference_resolution.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_workflow_reference_resolution.py:322)
  - explicit workspace-path references still work and assert hashed isolated namespaces in [tests/runtime/test_workflow_reference_resolution.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_workflow_reference_resolution.py:426) and [tests/runtime/test_workflow_reference_resolution.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_workflow_reference_resolution.py:574)
- The wheel smoke now builds through `pip wheel` in [tests/runtime/test_wheel_packaging_smoke.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_wheel_packaging_smoke.py:27) and still verifies wheel creation, clean-venv install, CLI help, workflow listing, and packaged assets through line 82.
- Independent audit validation passed:
  - `.venv_phase/bin/python -m pytest -q tests/runtime/test_workflow_reference_resolution.py tests/runtime/test_workflow_catalog_roots.py tests/runtime/test_runtime_cli_metadata_integration.py tests/runtime/test_package_cli.py tests/runtime/test_wheel_packaging_smoke.py`
  - result: `60 passed in 13.53s`

## Unresolved gaps

- No material unresolved gaps found in the requested scope.

## Differences justified by later clarification or analysis

- The wheel-build smoke uses `python -m pip wheel` rather than `python -m build`. This is a justified implementation difference because the request explicitly called out failure from a missing `build` module, and the later decisions recorded that the fix should remove the dependency on an ambient build frontend rather than expand runtime or packaging dependencies.
- No runtime loader or catalog behavior was broadened. The work stayed in validation/tests, which matches the request to close validation gaps without restoring legacy discovery behavior.

## Recommended next run

- No follow-up implementation run is required for this request.
