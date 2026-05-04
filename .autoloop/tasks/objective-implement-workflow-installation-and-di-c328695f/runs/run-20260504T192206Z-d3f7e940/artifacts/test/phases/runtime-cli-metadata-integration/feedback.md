# Test Author ↔ Test Auditor Feedback

- Task ID: objective-implement-workflow-installation-and-di-c328695f
- Pair: test
- Phase ID: runtime-cli-metadata-integration
- Phase Directory Key: runtime-cli-metadata-integration
- Phase Title: Integrate Runtime Loading, CLI, And Metadata
- Scope: phase-local authoritative verifier artifact

- Added focused runtime/CLI tests for explicit `.py` path loading outside the workspace root, corrected explicit manifest expectations to stay relative when the explicit path is still under the workspace root, and added CLI help coverage for the `.autoloop/workflows/` root contract.

- `TST-001` `blocking` [tests/runtime/test_runtime_cli_metadata_integration.py:315-363, .autoloop/tasks/objective-implement-workflow-installation-and-di-c328695f/runs/run-20260504T192206Z-d3f7e940/artifacts/test/phases/runtime-cli-metadata-integration/test_strategy.md:12-15] The focused phase suite still asserts `autoloop workflows show` only for a workspace workflow, but AC-3 requires the CLI show contract to expose correct source/module metadata for both source kinds. A regression where package-installed `workflows show` returns `source_root_kind="workspace"` or drops `package_module` / `workflow_module` would still pass this suite because the only package-source assertions go through runtime resolution and run metadata, not the CLI JSON path. Minimal correction: add a package-root fixture case that calls `cli.main(["workflows", "show", "<package_workflow>", "--root", ...])` and asserts package-source `source_root_kind`, `source_root`, `package_folder`, `package_module`, and `workflow_module`; update the strategy wording to reflect that split explicitly.

- Added a package-only `workflows show` CLI assertion so the focused suite now checks package-source `source_root_kind`, `source_root`, `package_folder`, `package_name`, `package_module`, and `workflow_module` directly on the CLI JSON path.
