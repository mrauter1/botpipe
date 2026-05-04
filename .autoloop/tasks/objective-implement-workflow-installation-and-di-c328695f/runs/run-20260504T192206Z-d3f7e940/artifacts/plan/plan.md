# Workflow Installation And Discovery Plan

## Target Outcome
- Make workflow discovery authoritative from exactly two roots: `autoloop/workflows/` and `{workspace}/.autoloop/workflows/`.
- Give workspace-local workflows precedence over package-installed workflows for bare names and aliases.
- Stop implicit discovery from `{workspace}/workflows/` without adding compatibility shims.
- Persist exact source metadata using only `"workspace"` and `"package"` source kinds.
- Ship built-in workflows through the installed package so `autoloop workflows list --root <empty-workspace>` works after wheel install.

## Current Change Surface
- Discovery and metadata are anchored to `<root>/workflows` in [autoloop/core/workflow_catalog.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/workflow_catalog.py), [autoloop/runtime/loader.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/loader.py), [autoloop/core/workflow_capabilities.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/workflow_capabilities.py), and [autoloop/runtime/inspection.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/inspection.py).
- CLI help, scaffold output, and JSON payloads still describe or emit repo-root `workflows/` paths in [autoloop/runtime/cli.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/cli.py).
- Runtime workspace metadata and context root inference assume package folders live directly under `workflows/` in [autoloop/runtime/workspace.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/workspace.py) and [autoloop/core/context.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/context.py).
- Built-in workflows currently live in top-level [workflows](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows) and some of them use depth-sensitive `package_folder` paths to repo docs.
- Packaging metadata is incomplete in [pyproject.toml](/home/rauter/autoloop_v3_bkp/autoloop_v3/pyproject.toml); `MANIFEST.in` is absent.
- Tests and docs widely encode the old layout and import namespace.

## Interface Contract
- Add `WorkflowSearchRoot` exactly as specified, plus `workspace_workflows_root`, `package_workflows_root`, and `workflow_search_roots(workspace_root)`.
- Expand `WorkflowCatalogEntry` to carry root kind, root path, precedence, import metadata, support-file paths, and shadowing markers exactly as requested.
- Expand `ResolvedWorkflow` and runtime workflow origin metadata with `source_root_kind`, `source_root`, `package_name`, `package_module`, and `workflow_module`.
- Implement `discover_workflow_catalog(workspace_root, *, include_shadowed=False)` as the single source of truth for effective catalog assembly, duplicate detection, tier precedence, and shadowed-entry reporting.
- Keep explicit filesystem path resolution as a separate path that bypasses catalog precedence but still produces normalized origin metadata.

## Milestones
### 1. Discovery And Catalog Refactor
- Replace single-root catalog scanning with ordered search roots from `workflow_search_roots`.
- Support three discovery shapes only: package directory, workspace directory, workspace single-file.
- Enforce same-tier duplicate detection across names and aliases before resolution.
- Mark cross-tier collisions as workspace-shadowing instead of errors.
- Preserve explicit path references, but remove bare-name probing against `{workspace}/workflows`.

### 2. Runtime, Import, CLI, And Metadata Integration
- Update runtime resolution to load package workflows by normal import under `autoloop.workflows.*`.
- Load workspace workflows by deterministic isolated module namespaces that preserve relative imports without adding `.autoloop` to `sys.path`.
- Remove repo-root `workflows` assumptions from cache eviction, pycache cleanup, capability inspection, context root inference, and workflow workspace metadata.
- Update CLI help, `workflows list`, `workflows show`, and `init workflow` scaffold output to reflect package-vs-workspace roots and `--all` shadowed visibility.
- Persist the new workflow origin payload in workflow/run metadata without copying sources into runtime state.

### 3. Built-In Workflow Relocation, Packaging, Docs, And Verification
- Add `autoloop/workflows/__init__.py` and relocate built-in workflow packages under `autoloop/workflows/<workflow_id>/`.
- Make each built-in package export its workflow class from package `__init__.py`, with `__all__` containing the workflow class and `"Params"` when exported.
- Normalize built-in repo-asset references that currently depend on the old package depth so source-in-place execution still works after relocation.
- Add package script and package-data metadata, add `MANIFEST.in`, and exclude runtime/cache/build outputs from packaging inputs.
- Update docs and tests to describe only `autoloop/workflows/` and `{workspace}/.autoloop/workflows/`, then add wheel build/install validation.

## Compatibility And Intentional Behavior Changes
- Intentional break: bare workflow names and aliases will no longer discover `{workspace}/workflows/*`; only explicit paths may reference arbitrary filesystem locations there.
- Intentional narrowing: package-installed workflows are directory packages only; single-file package-installed workflows are not supported.
- Persisted and API-exposed source-kind values must be exactly `"workspace"` or `"package"`; no mixed terminology remains in returned metadata.
- Explicit path references remain supported and bypass catalog precedence, including paths outside the two canonical roots.

## Regression Controls
- Update root inference away from `package_folder.parent.name == "workflows"` so package-installed workflows under `autoloop/workflows` still resolve repository root correctly in source checkout usage.
- Replace broad top-level `workflows` cache assumptions with source-kind-aware invalidation so package imports stay stable and workspace reload only clears the isolated namespace for the addressed workflow.
- Treat non-directory existing search roots as hard errors with concrete paths, but allow missing roots silently.
- Validate package exports during catalog/capability loading so wheel-installed failures surface as clear errors rather than runtime mis-resolution.
- Keep runtime metadata source paths pointing at original sources; do not copy workflow packages into `.autoloop/tasks/...`.

## Risk Register
- Built-in workflows contain `package_folder`-relative references to repo docs and instructions. Control: switch those references to root-aware paths during relocation and cover with runtime tests.
- A large test/doc footprint still assumes repo-root `workflows/`. Control: update only discovery/install expectations, while preserving explicit path-resolution coverage where intended.
- Package data may still pass in editable source runs but fail from wheels. Control: add `python -m build`, clean install, CLI smoke, catalog smoke, and asset-access verification.
- Same-tier alias/name collision handling is broader than current duplicate-name checks. Control: add focused discovery and resolution tests before changing CLI/runtime callers.

## Validation Matrix
- Unit tests for search roots, catalog shapes, precedence, duplicate detection, shadow reporting, and explicit-path bypass.
- Runtime/import tests for workspace relative imports, package export validation, module namespace isolation, and persisted origin metadata.
- CLI tests for help text, scaffold target location, effective-vs-all catalog listing, and show/list JSON payloads.
- Packaging tests for wheel build, clean install, global `autoloop` entry point, empty-workspace package discovery, and packaged asset accessibility.
