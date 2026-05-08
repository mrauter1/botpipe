# Implementation Notes

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: implement
- Phase ID: prove-botlane-only-surface
- Phase Directory Key: prove-botlane-only-surface
- Phase Title: Prove Botlane Only Surface
- Scope: phase-local producer artifact

## Files changed
- `MANIFEST.in`
- `__init__.py`
- `tests/strictness/test_no_compat.py`
- `tests/runtime/test_wheel_packaging_smoke.py`
- `tests/runtime/test_workspace_and_context.py`

## Symbols touched
- Strictness scan roots: `OPTIONAL_SCAN_FILES`, `BRANDING_SCAN_ROOTS`, `_iter_branding_scan_files()`
- Wheel smoke: `test_built_wheel_installs_public_botlane_package_and_cli`
- Workspace/runtime proof: `test_run_creates_task_workflow_run_layout_and_immutable_request_snapshots`, `test_run_metadata_records_topology_hashes_and_artifact_contract_paths`

## Checklist mapping
- Milestone 4 / P4-AC1: strengthened wheel smoke to inspect built wheel contents, verify only the `botlane` console script is installed, and assert legacy imports/module execution stay unavailable.
- Milestone 4 / P4-AC2: widened maintained-tree branding proof to additional root packaging files and removed stale root/package metadata branding.
- Milestone 4 / P4-AC3: added explicit `.botlane`-only and `botlane.*` schema assertions to runtime workspace emission tests while leaving legacy read-compat coverage intact.

## Assumptions
- Root review/spec markdown files (`Review15.md`, `review16.md`, `rebrand.md`) remain out of maintained product scan scope for this phase; the widened grep proof targets product code, tests, docs, fixtures, and live packaging metadata.

## Preserved invariants
- Legacy `.autoloop` workspaces, config names, and persisted schema aliases remain readable through existing compatibility readers/tests.
- No `autoloop` import alias, module entrypoint, or console-script alias was reintroduced.

## Intended behavior changes
- Packaging metadata now points at `botlane/workflows` and prunes `.botlane` state directly.
- Built-wheel proof now fails if the wheel ships legacy package paths, exposes an `autoloop` console script, or prints legacy branding in CLI help.
- Runtime proof now fails if new workspace creation writes legacy state roots or emits legacy schema prefixes in run/topology payloads.

## Known non-changes
- No runtime compatibility logic was changed in this phase.
- Legacy review/spec artifacts outside the maintained scan roots were not renamed here.

## Expected side effects
- Source-distribution manifests will stop advertising `autoloop/workflows` and will exclude both current `.botlane` state and legacy `.autoloop` state from package archives.

## Validation performed
- `.venv/bin/python -m pytest -q tests/strictness/test_no_compat.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_wheel_packaging_smoke.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_workspace_and_context.py -k 'run_creates_task_workflow_run_layout_and_immutable_request_snapshots or run_metadata_records_topology_hashes_and_artifact_contract_paths'`

## Deduplication / centralization
- Reused the existing strictness scan helpers instead of adding a second repo-grep test; only the maintained-file allowlist and root packaging coverage changed.
