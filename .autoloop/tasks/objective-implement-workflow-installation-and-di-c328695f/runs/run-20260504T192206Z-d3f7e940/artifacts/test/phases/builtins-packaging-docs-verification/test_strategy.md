# Test Strategy

- Task ID: objective-implement-workflow-installation-and-di-c328695f
- Pair: test
- Phase ID: builtins-packaging-docs-verification
- Phase Directory Key: builtins-packaging-docs-verification
- Phase Title: Relocate Built-Ins, Package Assets, And Close Verification
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- AC-1 package workflow namespace and catalog behavior:
  `tests/runtime/test_package_cli.py`, `tests/runtime/test_runtime_cli_metadata_integration.py`, `tests/runtime/test_workflow_catalog_roots.py`
- AC-2 wheel build/install/package-asset smoke:
  `tests/runtime/test_wheel_packaging_smoke.py`
- AC-3 documentation and repo-layout guidance:
  `tests/test_architecture_baseline_docs.py`

## Behaviors Covered

- Built-in workflows remain discoverable from `autoloop/workflows/` and list correctly in an empty workspace
- Workspace workflows remain rooted under `.autoloop/workflows/` with no implicit `{workspace}/workflows/` discovery
- Public docs and recursive guidance reference `autoloop/workflows/` and `.autoloop/workflows/` instead of the removed legacy root
- Public docs do not contain malformed `docs/autoloop/workflows/...` citations after bulk path rewrites

## Preserved Invariants Checked

- Package-installed workflows still expose package metadata and assets after wheel installation
- Documentation keeps the package/workspace root split explicit and does not regress to the removed repo-root workflow namespace

## Edge Cases / Failure Paths

- Empty-workspace catalog listing still returns package workflows only
- Doc-sweep regression case: a stale literal `` `workflows/` `` in `docs/authoring.md`
- Bulk-rewrite regression case: malformed workflow doc path under `docs/autoloop/workflows/...`

## Validation Notes

- Added one focused doc-regression test in `tests/test_architecture_baseline_docs.py`
- Local shell did not provide `pytest`; validated the new doc assertions with a deterministic `python3` script that reads the docs directly

## Known Gaps

- This pass did not rerun the full packaging test matrix because `pytest` is unavailable in the base shell; it only added and locally validated the doc-regression guard
