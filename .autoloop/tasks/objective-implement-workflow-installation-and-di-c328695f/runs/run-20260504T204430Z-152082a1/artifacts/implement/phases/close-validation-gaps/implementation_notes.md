# Implementation Notes

- Task ID: objective-implement-workflow-installation-and-di-c328695f
- Pair: implement
- Phase ID: close-validation-gaps
- Phase Directory Key: close-validation-gaps
- Phase Title: Close Validation Gaps
- Scope: phase-local producer artifact

## Files Changed
- `tests/runtime/test_workflow_reference_resolution.py`
- `tests/runtime/test_wheel_packaging_smoke.py`
- `decisions.txt`

## Symbols Touched
- `_clear_generated_modules`
- `_workspace_catalog_root`
- `_write_workspace_flow`
- `_write_workspace_single_file`
- `test_flow_package_directory_reference_supports_relative_specs_and_named_inference`
- `test_bare_workflow_names_are_not_shadowed_by_unrelated_repo_paths`
- `test_simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection`
- `test_explicit_class_references_use_workspace_isolated_module_namespace`
- `test_named_references_fail_when_inferred_candidates_conflict`
- `test_parameter_resolution_follows_class_module_package_legacy_then_none`
- `test_built_wheel_installs_cli_and_packaged_workflow_assets`

## Checklist Mapping
- Milestone 1: Updated reference-resolution tests so implicit bare-name coverage uses `.autoloop/workflows`, explicit `{workspace}/workflows` stays path-only, and workspace-path module assertions use `_autoloop_workspace_workflows.<hash>...`.
- Milestone 2: Replaced `python -m build` in the wheel smoke with `python -m pip wheel --no-deps --wheel-dir <dist> .` so the validation interpreter does not need an ambient `build` module.
- Milestone 3: Re-ran the required five-suite runtime/package validation slice.

## Assumptions
- Pip's standard isolated PEP 517 wheel build path is available in the project validation environment even when `build` and `setuptools` are not preinstalled into the active interpreter.

## Preserved Invariants
- No implicit bare-name or alias expectation remains tied to `{workspace}/workflows`.
- `{workspace}/workflows` coverage remains only through explicit filesystem-path references.
- Runtime discovery implementation was not expanded or relaxed.
- Wheel smoke still verifies wheel creation, clean-venv installation, CLI availability, package-owned workflow listing, and packaged asset presence.

## Intended Behavior Changes
- Test expectations now treat `.autoloop/workflows` as the workspace discovery root for bare names.
- Explicit workspace-path loads now assert the hashed isolated namespace emitted by the loader.
- Wheel smoke uses pip's built-in wheel frontend instead of the optional `build` module.

## Known Non-Changes
- No runtime loader behavior changed.
- No packaging metadata or dependency declarations changed.
- No broader packaging workflow refactor was introduced.

## Expected Side Effects
- Reference-resolution tests better distinguish catalog discovery from explicit path loading, reducing future false positives around legacy discovery roots.

## Validation Performed
- `.venv_phase/bin/python -m pytest -q tests/runtime/test_workflow_reference_resolution.py tests/runtime/test_wheel_packaging_smoke.py`
- `.venv_phase/bin/python -m pytest -q tests/runtime/test_workflow_reference_resolution.py tests/runtime/test_workflow_catalog_roots.py tests/runtime/test_runtime_cli_metadata_integration.py tests/runtime/test_package_cli.py tests/runtime/test_wheel_packaging_smoke.py`

## Deduplication / Centralization
- Added small local helpers for `.autoloop/workflows` fixture creation to keep the discovery-root split explicit inside `test_workflow_reference_resolution.py`.
