# Implement ↔ Code Reviewer Feedback

- Task ID: objective-implement-workflow-installation-and-di-c328695f
- Pair: implement
- Phase ID: catalog-root-refactor
- Phase Directory Key: catalog-root-refactor
- Phase Title: Refactor Workflow Search Roots And Catalog
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — `autoloop/core/workflow_catalog.py:read_workflow_manifest` returns early when `aliases` is missing or empty, so manifests that omit `title` and/or `description` are accepted instead of failing validation. Reproduction with `.venv_phase/bin/python`: a `workflow.toml` containing only `name = "demo"` returns `{'name': 'demo', 'aliases': ()}` instead of raising the required-fields error. This violates the manifest contract and AC-4. Minimal fix: normalize `aliases` without returning early, then run the required-field validation unconditionally in `read_workflow_manifest`.

- IMP-002 `blocking` — `autoloop/runtime/loader.py:_resolve_imported_class_reference` reconciles package classes back to catalog entries via `resolve_workflow_package(root, package_name)`, which only searches the effective catalog. When a workspace workflow shadows a package workflow of the same name, an imported class from `autoloop.workflows.<id>.flow` is mis-resolved against the workspace entry and fails with `WorkflowDiscoveryError workflow class 'DemoWorkflow' was not found in module '_autoloop_workspace_workflows....demo.flow'`. This breaks explicit package-backed imports under the required shadowing model. Minimal fix: when resolving an imported package class, search `discover_workflow_catalog(..., include_shadowed=True)` and match the package entry by concrete `source_path` / `manifest_path` (or `package_module`) instead of routing through bare-name precedence.

- Re-review disposition — `IMP-001` and `IMP-002` are resolved in the current implementation. I reran `tests/runtime/test_workflow_catalog_roots.py` (`14 passed`) and rechecked both concrete reproductions; no additional findings remain for this phase.
