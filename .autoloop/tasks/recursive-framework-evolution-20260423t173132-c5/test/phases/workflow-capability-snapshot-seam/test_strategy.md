# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c5
- Pair: test
- Phase ID: workflow-capability-snapshot-seam
- Phase Directory Key: workflow-capability-snapshot-seam
- Phase Title: Workflow Capability Snapshot Seam
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Lightweight discovery remains metadata-only and non-importing.
  Covered by `tests/runtime/test_compatibility_runtime.py::test_discover_workflow_catalog_collects_linked_paths_without_importing_workflow_modules`.

- Rich capability inspection imports workflows and exposes normalized parameter and compiled step-contract detail.
  Covered by `tests/runtime/test_compatibility_runtime.py::test_inspect_workflow_capabilities_adds_importing_parameter_and_step_contract_detail`.

- Runtime package re-export exposes the new inspection seam without changing runtime-facing manifest/discovery error behavior.
  Covered by `tests/runtime/test_compatibility_runtime.py::test_runtime_package_reexports_workflow_capability_inspection_happy_path` and `::test_runtime_package_reexported_catalog_discovery_preserves_runtime_error_types`.

- Workflow-local lightweight portfolio snapshot helper keeps its existing narrow payload contract.
  Covered by `tests/unit/test_stdlib_and_extensions.py::test_portfolio_helper_writes_workflow_local_catalog_snapshot`.

- Workflow-local capability snapshot helper writes richer artifacts while leaving the lightweight snapshot narrow.
  Covered by `tests/unit/test_stdlib_and_extensions.py::test_portfolio_helpers_keep_catalog_snapshot_lightweight_and_capability_snapshot_rich`.

## Preserved invariants checked

- `workflow.toml` stays metadata-only; no execution metadata is required for lightweight discovery.
- `write_workflow_portfolio_snapshot(...)` remains usable without importing workflow modules.
- Existing front-door workflow behavior still passes via `tests/runtime/test_task_to_workflow_strategy.py`.
- Baseline architecture/authoring docs still pass via `tests/test_architecture_baseline_docs.py`.

## Edge cases and failure paths

- Invalid manifest handling for the new inspection seam still maps to runtime error types.
- Path escape and non-`.json` rejection for `write_workflow_capability_snapshot(...)`.
- Broken workflow-import path proves the boundary: `write_workflow_portfolio_snapshot(...)` still succeeds, while `write_workflow_capability_snapshot(...)` fails because it intentionally imports workflow modules.

## Reliability notes

- All added tests use tmp-path-local workflow packages and deterministic filesystem assertions only.
- No network, timing, subprocess ordering, or non-deterministic ranking assumptions were introduced.

## Known gaps

- No CLI-specific test was added for the new inspection seam because this phase does not change CLI syntax or add a new CLI command.
