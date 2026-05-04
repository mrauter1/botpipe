# Test Strategy

- Task ID: objective-implement-workflow-installation-and-di-c328695f
- Pair: test
- Phase ID: runtime-cli-metadata-integration
- Phase Directory Key: runtime-cli-metadata-integration
- Phase Title: Integrate Runtime Loading, CLI, And Metadata
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map
- AC-1 runtime metadata:
  workspace workflow run metadata asserts `source_root_kind`, `source_root`, `package_name`, `package_module`, `workflow_module`, `source_path`, and `manifest_path` in both `workflow.json` and `run.json`.
- AC-2 loader routing and imports:
  explicit manifest path coverage exercises `.toml` loading; explicit single-file path coverage exercises `.py` loading; package workflow coverage asserts `autoloop.workflows.<workflow_id>` and `.flow` module metadata on resolved and persisted package runs.
- AC-3 CLI contract:
  `workflows list` asserts additive JSON fields including `manifest_present`, `source_root_kind`, and shadow metadata; `workflows show` asserts source/module fields for both workspace and package workflows; `init workflow` asserts scaffold location under `.autoloop/workflows`; `workflows list --help` asserts the package-vs-`.autoloop/workflows/` root description.
- AC-4 explicit-path normalization:
  in-workspace explicit manifest paths remain workspace-relative in nested workflow-origin metadata; out-of-workspace explicit `.py` paths serialize absolute workflow-origin paths while keeping `source_root_kind="workspace"` and null package/workflow modules.

## Preserved Invariants Checked
- Generic top-level `run.json` `package_folder` remains relative for explicit workflows still under the workspace root.
- Workspace workflows remain filesystem-loaded with null package/workflow module names.
- Package workflows keep package-root coverage on injected `autoloop/workflows` fixtures rather than built-in workflows.

## Edge Cases
- Workspace workflow shadows package workflow in CLI list/show coverage.
- Explicit workflow reference outside canonical roots but inside workspace root.
- Explicit workflow reference outside workspace root entirely.

## Failure Paths / Stabilization
- Help-text assertions use `SystemExit(0)` from argparse and capture stdout only; no shelling out.
- Workflow-module isolation fixture clears both `autoloop.workflows.*` and isolated workspace module namespaces between tests.
- Environment gap: phase-local validation here is limited to syntax checks because `pytest` is unavailable in this container.

## Known Gaps
- The focused phase suite does not perform wheel install verification; that remains out of scope for this phase.
