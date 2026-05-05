# Test Strategy

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: test
- Phase ID: restore-workflow-resolution-contract
- Phase Directory Key: restore-workflow-resolution-contract
- Phase Title: Restore Workflow Resolution Contract
- Scope: phase-local producer artifact

## Behavior to coverage map

- Mixed-root named authority:
  - `tests/runtime/test_workflow_catalog_roots.py::test_workspace_catalog_keys_shadow_package_catalog_keys`
  - `tests/runtime/test_workflow_reference_resolution.py::test_bare_workflow_names_are_not_shadowed_by_unrelated_repo_paths`
  - Confirms `.autoloop/workflows` stays authoritative for bare names and workspace aliases.
- Repo-local named fallback by unclaimed key:
  - `tests/runtime/test_workflow_catalog_roots.py::test_repo_local_unique_alias_remains_resolvable_when_workspace_claims_workflow_name`
  - Confirms a shadowed repo-local workflow still resolves through a unique alias.
- Named repo-local class round-trip:
  - `tests/runtime/test_workflow_catalog_roots.py::test_named_repo_local_class_round_trip_preserves_repo_module_namespace_when_name_is_shadowed`
  - Confirms a workflow first resolved through a repo-only alias stays on the `workflows.*` namespace when re-resolved from its class object.
- Explicit repo-local file and class isolation:
  - `tests/runtime/test_workflow_reference_resolution.py::test_explicit_class_references_use_workspace_isolated_module_namespace`
  - `tests/runtime/test_workflow_reference_resolution.py::test_imported_repo_local_class_references_use_workspace_isolated_module_namespace`
  - Confirms explicit path and direct imported class-object references load through `_autoloop_workspace_workflows...`.
- Repo-local package-module support without incidental leakage:
  - `tests/runtime/test_workflow_catalog_roots.py::test_repo_local_module_resolution_evicts_stale_workflows_namespace_between_roots`
  - Confirms named repo-local imports do not leak stale `workflows.*` modules across roots.

## Preserved invariants checked

- `.autoloop/workflows` remains the authority surface for mixed-root bare names.
- Repo-local `workflows/` remains available as a named fallback only when the workspace catalog does not claim the key.
- Explicit repo-local references preserve isolated Params/spec loading parity.
- Package-installed workflows keep their package-module contract.

## Edge cases and failure paths

- Shadowed repo-local canonical name with unique surviving alias.
- Class-object resolution after a named fallback load where the canonical workflow name is still shadowed.
- Repeated named repo-local imports across different workspace roots.

## Flake risk and stabilization

- Tests isolate `sys.modules` for `workflows.*`, `autoloop.workflows.*`, and `_autoloop_workspace_workflows.*` between cases.
- All coverage uses temporary workspaces and local filesystem fixtures only; no timing or network dependencies.

## Known gaps

- This phase does not extend into optimizer source-manifest normalization or packaged-workflow runtime suites.
