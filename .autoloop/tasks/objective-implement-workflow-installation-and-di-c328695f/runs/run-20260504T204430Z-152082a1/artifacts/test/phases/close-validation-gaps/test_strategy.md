# Test Strategy

- Task ID: objective-implement-workflow-installation-and-di-c328695f
- Pair: test
- Phase ID: close-validation-gaps
- Phase Directory Key: close-validation-gaps
- Phase Title: Close Validation Gaps
- Scope: phase-local producer artifact

## Behavior To Coverage Map
- Bare-name discovery uses `{workspace}/.autoloop/workflows`: covered by `test_flow_package_directory_reference_supports_relative_specs_and_named_inference`, `test_bare_workflow_names_are_not_shadowed_by_unrelated_repo_paths`, and `test_simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection`.
- Alias discovery stays catalog-only and does not come from `{workspace}/workflows`: covered by `test_manifest_aliases_resolve_from_workspace_catalog_root_only`.
- `{workspace}/workflows` remains explicit-path-only: covered by `test_flow_package_directory_reference_supports_relative_specs_and_named_inference`, `test_simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection`, `test_explicit_class_references_use_workspace_isolated_module_namespace`, and parameter-resolution path tests.
- Explicit workspace-path imports use `_autoloop_workspace_workflows.<hash>...`: covered by single-file, explicit class-reference, and parameter-resolution namespace assertions.
- Wheel smoke builds without ambient `build`: covered by `test_built_wheel_installs_cli_and_packaged_workflow_assets` using `python -m pip wheel`.

## Preserved Invariants Checked
- No touched test expects implicit bare-name or alias resolution from `{workspace}/workflows`.
- Wheel smoke still verifies wheel creation, install into a fresh venv, CLI help, package-owned workflow listing, and packaged asset presence.

## Edge Cases
- Alias lookup fails before a catalog manifest exists, then resolves once the `.autoloop/workflows` manifest-backed workflow is present.
- Duplicate same-tier resolution keys still fail in adjacent catalog-root coverage rather than being normalized away.

## Failure Paths
- Unknown alias from explicit `{workspace}/workflows` raises `WorkflowDiscoveryError`.
- Ambiguous or duplicate name resolution remains covered by `test_named_references_fail_when_inferred_candidates_conflict` and adjacent catalog-root tests.

## Flake Risks / Stabilization
- Wheel build depends on pip’s isolated PEP 517 path; the smoke is stabilized by running only local wheel creation and installing the produced artifact into a fresh temporary venv.
- Workflow-loader module caching is stabilized with the autouse module-eviction fixture in `test_workflow_reference_resolution.py`.

## Known Gaps
- Package-root alias precedence remains covered in adjacent runtime catalog and CLI tests rather than re-duplicated in the touched reference-resolution file.
