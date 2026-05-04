# Test Strategy

- Task ID: objective-implement-workflow-installation-and-di-c328695f
- Pair: test
- Phase ID: catalog-root-refactor
- Phase Directory Key: catalog-root-refactor
- Phase Title: Refactor Workflow Search Roots And Catalog
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- AC-1 roots and effective catalog: `test_workflow_search_roots_use_only_workspace_and_package_roots`, `test_discover_workflow_catalog_allows_missing_search_roots`, `test_discover_workflow_catalog_rejects_non_directory_search_root`, `test_discover_workflow_catalog_returns_workspace_and_package_source_kinds`.
- AC-2 precedence and bare resolution: `test_workspace_catalog_keys_shadow_package_catalog_keys`, `test_same_tier_resolution_key_collisions_fail_with_paths`, `test_unknown_bare_name_lists_searched_roots`, `test_imported_package_class_resolves_shadowed_package_entry`.
- AC-3 source-kind and explicit-path behavior: `test_discover_workflow_catalog_returns_workspace_and_package_source_kinds`, `test_explicit_manifest_path_resolves_outside_catalog_roots`, `test_workspace_relative_imports_use_isolated_module_namespace`.
- AC-4 manifest semantics and loader routing: `test_manifest_requires_title_and_description_even_without_aliases`, `test_manifest_class_field_selects_specific_workflow_class`, `test_manifest_module_field_selects_declared_module`, `test_manifest_without_module_falls_back_to_workflow_py_when_flow_missing`, `test_manifest_without_class_rejects_multiple_workflow_classes`.

## Preserved invariants checked
- `{workspace}/workflows` is never treated as a catalog root.
- Workspace workflows keep precedence over package workflows for bare names and aliases.
- Explicit `.toml` references outside the canonical roots still load with `source_root_kind == "workspace"` and null module metadata.
- Workspace package loading continues to use isolated module namespaces for relative imports.
- Explicit imported package classes continue to resolve to package entries even when a workspace workflow shadows the same bare key.

## Edge cases and failure paths
- Both missing search roots and existing non-directory roots are covered.
- Same-tier duplicate alias collisions fail with concrete paths.
- Unknown bare names report the requested name plus searched roots.
- Manifest validation covers missing required fields, explicit class selection, explicit module selection, fallback to `workflow.py`, and ambiguous-class rejection.

## Stability notes
- Package-root scenarios use injected temporary `autoloop/workflows` fixtures instead of built-in workflows so the suite stays deterministic before built-in workflow relocation lands in a later phase.
- Module cache cleanup is handled by the autouse fixture to avoid cross-test pollution from `autoloop.workflows.*` and `_autoloop_workspace_workflows.*`.

## Known gaps
- Later phases still need CLI/help/json, runtime metadata persistence, built-in workflow relocation, and wheel-packaging validation coverage.
