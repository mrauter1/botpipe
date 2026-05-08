# Implementation Notes

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: implement
- Phase ID: editable-install-refresh-and-proof
- Phase Directory Key: editable-install-refresh-and-proof
- Phase Title: Refresh Editable Install And Prove It
- Scope: phase-local producer artifact

## Files Changed
- `tests/runtime/test_wheel_packaging_smoke.py`
- `.autoloop/tasks/additional-botlane-rename-requirements-discovere-28c3ecb0/runs/run-20260508T205237Z-432ec7b1/decisions.txt`
- `.autoloop/tasks/additional-botlane-rename-requirements-discovere-28c3ecb0/runs/run-20260508T205237Z-432ec7b1/artifacts/implement/phases/editable-install-refresh-and-proof/implementation_notes.md`

## Symbols Touched
- `_run`
- `_repo_venv_bin`
- `test_built_wheel_installs_public_botlane_package_and_cli`
- `test_repo_local_editable_install_exposes_only_botlane_cli_identity`

## Checklist Mapping
- Milestone 1 / AC-1 / AC-2: refreshed `.venv` with `./.venv/bin/pip uninstall -y autoloop-v3-surface` then `./.venv/bin/pip install -e .`
- Milestone 2 / AC-2 / AC-3: added repo-local `.venv` packaging proof for distribution identity, console script presence/absence, and entry-point metadata
- Milestone 3 / AC-3: reran focused packaging smoke and direct shell validation against the shared repo `.venv`

## Assumptions
- Repo-local proof should target `REPO_ROOT/.venv` directly, but skip when that local virtualenv is absent in another execution context.

## Preserved Invariants
- No `autoloop` import alias, package alias, or CLI alias was added.
- Legacy `.autoloop`, legacy config names, and persisted `autoloop.*` readability policy was left untouched.

## Intended Behavior Changes
- Packaging smoke now validates installed wheel/editable metadata from an isolated working directory instead of the repo root.
- The active shared `.venv` now exposes only the Botlane editable distribution and `botlane` console script.

## Known Non-Changes
- No runtime, compatibility-reader, or source-tree rename logic changed.
- No new install/bootstrap wrapper scripts were introduced.

## Expected Side Effects
- `.venv/bin/botlane` exists and resolves to `botlane.runtime.cli:main`.
- `.venv/bin/autoloop` and `autoloop-v3-surface` editable metadata are removed from the shared repo virtualenv.

## Validation Performed
- `./.venv/bin/pip uninstall -y autoloop-v3-surface`
- `./.venv/bin/pip install -e .`
- `./.venv/bin/pytest -q tests/runtime/test_wheel_packaging_smoke.py`
- `./.venv/bin/pip show botlane-v3-surface`
- `./.venv/bin/pip show autoloop-v3-surface` (expected failure)
- `./.venv/bin/botlane --help`
- inspected `.venv/lib/python3.12/site-packages/botlane_v3_surface-0.0.0.dist-info/entry_points.txt`

## Deduplication / Centralization Decisions
- Reused the existing packaging smoke test file and helper instead of adding a new install harness or wrapper script.
