# Implement ↔ Code Reviewer Feedback

- Task ID: objective-implement-workflow-installation-and-di-c328695f
- Pair: implement
- Phase ID: runtime-cli-metadata-integration
- Phase Directory Key: runtime-cli-metadata-integration
- Phase Title: Integrate Runtime Loading, CLI, And Metadata
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [autoloop/runtime/cli.py:196-208] `autoloop workflows list` now removes the existing `manifest_present` field instead of extending the JSON payload additively. The request required new list fields, but it did not authorize removing old ones, and the plan explicitly treats CLI JSON as a public contract. Any automation still reading `manifest_present` will break after this change even though the new metadata could have been added without loss of compatibility. Minimal fix: restore `manifest_present` in the list payload and keep the new `package_folder`, `source_root_kind`, `shadowed`, and `shadowed_by` fields as additive fields.

- `IMP-002` `blocking` [autoloop/runtime/workspace.py:1288-1294] `_serialize_path` was changed globally for all persisted runtime paths, not just workflow-origin metadata. That means unrelated fields such as `run_folder`, `request_file`, parent/child run paths, and top-level `package_folder` will now switch from repo-relative paths to absolute paths whenever runtime state lives outside the workspace root. This behavior change is broader than the phase scope, was not explicitly requested, and can break existing tooling or tests that consume the generic runtime metadata contract while only the workflow-origin fields needed out-of-root normalization. Minimal fix: revert `_serialize_path` to its prior generic behavior and introduce a dedicated serializer used only by workflow-origin fields that need absolute normalization for out-of-root package and explicit-path workflows.

- `IMP-003` `non-blocking` [tests/runtime/test_runtime_cli_metadata_integration.py:132-288] The new focused tests cover workspace metadata, explicit manifest normalization, CLI shadow reporting, and scaffold location, but they still do not exercise a package-installed `workflows show`/`run` path that imports through `autoloop.workflows.<workflow_id>`. The older package-root test suite may still cover that, but this phase’s new focused tests do not independently prove the package-loading half of AC-2/AC-3.
