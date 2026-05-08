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
- `Review15.md`
- `review16.md`
- `rebrand.md`
- `recursive_botlane/run_recursive_botlane.sh`
- `recursive_botlane/run_recursive_botlane_templates/architecture_improvement_examples.md.tmpl`
- `recursive_botlane/run_recursive_botlane_templates/bootstrap_task.md.tmpl`
- `recursive_botlane/run_recursive_botlane_templates/cycle_task.md.tmpl`
- `recursive_botlane/run_recursive_botlane_templates/framework_evolution_charter.md.tmpl`
- `recursive_botlane/run_recursive_botlane_templates/framework_gap_ledger.md.tmpl`
- `recursive_botlane/run_recursive_botlane_templates/framework_roadmap.md.tmpl`
- `recursive_botlane/run_recursive_botlane_templates/validation_debt_ledger.md.tmpl`
- `recursive_botlane/run_recursive_botlane_templates/workflow_authoring_doctrine.md.tmpl`
- `recursive_botlane/run_recursive_botlane_templates/workflow_candidate_ledger.md.tmpl`
- `recursive_botlane/run_recursive_botlane_templates/workflow_examples.md.tmpl`
- `tests/strictness/test_no_compat.py`
- `tests/runtime/test_wheel_packaging_smoke.py`
- `tests/runtime/test_workspace_and_context.py`

## Symbols touched
- Strictness scan roots: `ACTIVE_SCAN_ROOTS`, `OPTIONAL_SCAN_FILES`, `BRANDING_SCAN_ROOTS`, `_iter_branding_scan_files()`
- Wheel smoke: `test_built_wheel_installs_public_botlane_package_and_cli`
- Workspace/runtime proof: `test_run_creates_task_workflow_run_layout_and_immutable_request_snapshots`, `test_run_metadata_records_topology_hashes_and_artifact_contract_paths`
- Recursive wrapper surfaces: `recursive_botlane/run_recursive_botlane.sh` and its template set

## Checklist mapping
- Milestone 4 / P4-AC1: strengthened wheel smoke to inspect built wheel contents, verify only the `botlane` console script is installed, and assert legacy imports/module execution stay unavailable.
- Milestone 4 / P4-AC2: widened maintained-tree branding proof to root packaging/spec docs and the maintained recursive wrapper/template surfaces, then renamed those surfaces to Botlane-only text.
- Milestone 4 / P4-AC3: added explicit `.botlane`-only and `botlane.*` schema assertions to runtime workspace emission tests while leaving legacy read-compat coverage intact.

## Assumptions
- `legacy_docs/*.md` remains unchanged in this phase, but only as an explicit historical-file allowlist enumerated in the strictness test; broad `legacy_docs/**` exclusions are no longer treated as acceptable proof scope.

## Preserved invariants
- Legacy `.autoloop` workspaces, config names, and persisted schema aliases remain readable through existing compatibility readers/tests.
- No `autoloop` import alias, module entrypoint, or console-script alias was reintroduced.

## Intended behavior changes
- Packaging metadata now points at `botlane/workflows` and prunes `.botlane` state directly.
- Built-wheel proof now fails if the wheel ships legacy package paths, exposes an `autoloop` console script, or prints legacy branding in CLI help.
- Runtime proof now fails if new workspace creation writes legacy state roots or emits legacy schema prefixes in run/topology payloads.
- Recursive wrapper docs/templates/shell surfaces now use `botlane`, `.botlane`, `.botlane_recursive`, and Botlane-only examples.
- Branding strictness now walks the repo root, skips only generated state and explicitly listed historical files, and inventory-checks the `legacy_docs/*.md` allowlist so new retained history files cannot be hidden behind a directory carveout.

## Known non-changes
- No runtime compatibility logic was changed in this phase.
- Historical scratch docs under `legacy_docs/` were not renamed here; they remain unchanged historical text and are now enumerated explicitly in the proof allowlist.

## Expected side effects
- Source-distribution manifests will stop advertising `autoloop/workflows` and will exclude both current `.botlane` state and legacy `.autoloop` state from package archives.
- The recursive wrapper entry path is now `recursive_botlane/run_recursive_botlane.sh`, and its templates now emit Botlane-only workspace/CLI guidance.
- Adding a new historical file under `legacy_docs/` now fails strictness until the file is either rewritten to Botlane-only text or added deliberately to the explicit history allowlist.

## Validation performed
- `.venv/bin/python -m pytest -q tests/strictness/test_no_compat.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_wheel_packaging_smoke.py tests/runtime/test_workspace_and_context.py -k 'test_built_wheel_installs_public_botlane_package_and_cli or run_creates_task_workflow_run_layout_and_immutable_request_snapshots or run_metadata_records_topology_hashes_and_artifact_contract_paths'`
- Repo-wide `rg` scan for `autoloop|Autoloop|AUTOLOOP|\.autoloop|autoloop_optimizer|_autoloop_workspace_workflows` with only generated-state globs and the explicit `legacy_docs/*.md` history-file allowlist excluded.

## Deduplication / centralization
- Reused the existing strictness scan helpers instead of adding a second repo-grep test; the branding proof now centralizes its only retained historical exceptions in `EXPLICIT_HISTORY_FILE_ALLOWLIST` and walks the repo root directly.
