# Implementation Notes

- Task ID: objective-implement-workflow-installation-and-di-c328695f
- Pair: implement
- Phase ID: runtime-cli-metadata-integration
- Phase Directory Key: runtime-cli-metadata-integration
- Phase Title: Integrate Runtime Loading, CLI, And Metadata
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/runtime/loader.py`
- `autoloop/runtime/workspace.py`
- `autoloop/runtime/runner.py`
- `autoloop/runtime/cli.py`
- `autoloop/core/context.py`
- `tests/runtime/test_runtime_cli_metadata_integration.py`

## Symbols Touched
- `ResolvedWorkflow`
- `WorkflowWorkspace`
- `ensure_workflow_workspace`
- `resolve_workflow_workspace`
- `update_run_metadata`
- `update_workflow_metadata`
- `_workflow_origin_payload`
- `_serialize_path`
- `_serialize_origin_path`
- `_assert_workflow_identity_consistency`
- `build_arg_parser`
- `_handle_workflows_list`
- `_handle_workflows_show`
- `_handle_init_workflow`
- `_resolve_context_root`

## Checklist Mapping
- Milestone 2 / runtime, import, CLI, and metadata integration:
  runtime origin metadata now carries `source_root_kind`, `source_root`, `package_name`, `package_module`, and `workflow_module`.
- Milestone 2 / CLI:
  `--root` help text, `workflows list`, `workflows show`, `--all`, and `init workflow` were updated to the `.autoloop/workflows` contract while preserving the existing `manifest_present` list field.
- Milestone 2 / explicit-path metadata:
  out-of-root workflow-origin paths now serialize absolutely instead of via brittle relative `..` segments, without changing generic runtime path serialization.
- Milestone 2 / tests:
  added focused CLI/runtime metadata coverage in `tests/runtime/test_runtime_cli_metadata_integration.py`, including package-source module metadata.

## Assumptions
- Existing relative task/workflow/run folder metadata remains acceptable for in-workspace runtime state in this phase.
- Built-in workflow relocation under `autoloop/workflows/` remains deferred to later phases, so package-root coverage continues to rely on injected temporary package fixtures in focused tests.

## Preserved Invariants
- Bare-name resolution still goes only through the authoritative workflow catalog.
- Workspace workflows still load from isolated filesystem module namespaces.
- Package workflows still expose their origin through normal package import metadata when discovered from package roots.

## Intended Behavior Changes
- Runtime workflow metadata now persists source-root and module-origin fields.
- CLI list/show now exposes explicit source metadata and shadowing status.
- `autoloop init workflow` now scaffolds under `{workspace}/.autoloop/workflows/` and defaults to the manifest-backed package shape.
- Context root inference now recognizes both `autoloop/workflows` and `.autoloop/workflows` layouts.

## Known Non-Changes
- No built-in workflow packages were relocated in this phase.
- No wheel-build or clean-install verification was performed in this environment.
- Large legacy runtime tests that still assume repo-root `workflows/` were not rewritten in this phase.

## Expected Side Effects
- Nested workflow-origin metadata now persists package-installed and explicit external workflow roots as absolute paths rather than relative escape paths.
- Existing consumers of CLI `workflows list` JSON keep `manifest_present` and also see `package_folder`, `source_root_kind`, `shadowed`, and `shadowed_by`.

## Validation Performed
- `python3 -m py_compile autoloop/runtime/loader.py autoloop/runtime/workspace.py autoloop/runtime/runner.py autoloop/runtime/cli.py autoloop/core/context.py tests/runtime/test_runtime_cli_metadata_integration.py`
- `python3 -m py_compile autoloop/runtime/cli.py autoloop/runtime/workspace.py tests/runtime/test_runtime_cli_metadata_integration.py`
- Attempted `python3 -m pytest -q tests/runtime/test_workflow_catalog_roots.py`, but `pytest` is not installed in this environment.
- Attempted direct Python smoke execution, but runtime dependencies are incomplete here (`pydantic` missing).

## Deduplication / Centralization
- Workflow-origin persistence is centralized through the expanded `_workflow_origin_payload`.
- Absolute out-of-root normalization is centralized in `_serialize_origin_path` so generic runtime metadata serialization keeps its prior relative-path behavior.
- CLI shadowed-entry lookup is centralized through `_catalog_entry_for_resolved_reference` for show output.
