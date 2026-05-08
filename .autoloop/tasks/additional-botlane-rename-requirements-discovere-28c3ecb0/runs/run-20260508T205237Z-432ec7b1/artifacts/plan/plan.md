# Botlane Editable Install Plan

## Scope
- Repair the active repository `.venv` so its editable install matches the already-renamed Botlane source tree.
- Add durable proof for the active repo virtualenv, not only for a freshly built wheel in a temporary venv.
- Preserve the existing transition rule: legacy `.autoloop` workspaces, legacy config names, and persisted `autoloop.*` artifacts stay readable, while new writes stay Botlane-only.

## Repo Findings
- [pyproject.toml](/home/rauter/autoloop_v3_bkp/autoloop_v3/pyproject.toml) already publishes `botlane-v3-surface`, installs `botlane`, and discovers `botlane*` packages only.
- The active repo `.venv` is stale: `pip show autoloop-v3-surface` succeeds, `pip show botlane-v3-surface` fails, `.venv/bin/autoloop` still imports `autoloop.runtime.cli`, `.venv/bin/botlane` is absent, and `.venv/lib/python3.12/site-packages/autoloop_v3_surface-0.0.0.dist-info/entry_points.txt` still registers the old console script.
- [tests/runtime/test_wheel_packaging_smoke.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_wheel_packaging_smoke.py) already proves Botlane-only behavior for a built wheel installed into a throwaway venv, but it does not inspect the shared repo-local editable install.
- [tests/strictness/test_no_compat.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/strictness/test_no_compat.py) intentionally ignores `.venv`, so it cannot catch stale editable-install residue and should remain separate from the run-local proof.

## Interface Contract
- Active editable distribution name must be `botlane-v3-surface`; `autoloop-v3-surface` must not remain installed in the repo `.venv`.
- Active repo CLI surface must include `.venv/bin/botlane` and must not include `.venv/bin/autoloop`.
- No `autoloop` import alias, package alias, or CLI alias may be added to satisfy the migration.
- Legacy-read compatibility remains limited to persisted state and config/workspace readers; this task must not broaden compatibility back into public package or CLI surfaces.

## Milestones
1. Refresh the active repo editable install.
   - Remove the stale `autoloop-v3-surface` editable install from `.venv`.
   - Reinstall the current repository into `.venv` with editable metadata that resolves to `botlane-v3-surface` and generates the `botlane` console script.
   - Verify the reinstall replaced the old dist-info / `.pth` / script state instead of leaving mixed-brand residue behind.
2. Add run-local validation for the shared `.venv`.
   - Extend the existing packaging smoke coverage, or add a tightly scoped sibling smoke test, so the suite inspects the active repo virtualenv directly.
   - Reuse the current packaging-smoke style helpers where practical; do not add new bootstrap wrappers or one-off install abstractions unless an existing maintained install entrypoint must be updated.
   - Assert installed-distribution identity, console-script presence/absence, and entry-point metadata using the active repo environment rather than wheel contents alone.
3. Re-run focused proof and capture final state.
   - Re-run packaging smoke and direct shell checks against `.venv`.
   - Confirm the final environment still honors the earlier rename clarification: legacy reads remain supported, but new public CLI/package identity is Botlane-only.

## Validation Plan
- Direct environment checks:
  - `.venv/bin/pip show botlane-v3-surface`
  - `.venv/bin/pip show autoloop-v3-surface` expecting failure
  - presence of `.venv/bin/botlane`
  - absence of `.venv/bin/autoloop`
  - active editable metadata / entry-point inspection through `importlib.metadata` or the installed dist-info files
- Automated proof:
  - `./.venv/bin/pytest -q tests/runtime/test_wheel_packaging_smoke.py`
  - if the editable-install proof is split out, run that focused test file or `-k` slice explicitly
- Regression guard:
  - keep the existing strictness and compatibility suites unchanged unless the implementation needs a narrow assertion update tied directly to editable-install proof

## Compatibility Notes
- This is a run-local repair of the active editable install, not a reopening of the rename scope.
- Legacy `.autoloop` / legacy config / persisted `autoloop.*` readability remains required and should only be regression-checked if the editable reinstall path touches those readers indirectly.
- Fresh-wheel proof remains valuable, but it is no longer sufficient on its own; the task is complete only when the shared repo `.venv` proves the rename too.

## Regression Risks
- Reinstalling without first removing the stale editable dist can leave mixed-brand dist-info or wrapper scripts behind.
- A repo-local smoke test can become brittle if it assumes the wrong interpreter or path layout instead of the active repo virtualenv.
- Fixing only the local shell state without adding proof allows the stale editable install to recur silently.
- Treating `build/` or `*.egg-info` as proof would miss the actual failure surface, which lives in `.venv/site-packages` and `.venv/bin`.

## Risk Register
- Mixed editable residue after reinstall.
  Control: explicitly check installed distribution names, entry points, and script files after the reinstall instead of assuming `pip install -e .` replaced everything cleanly.
- Over-engineered install automation for a one-off local repair.
  Control: prefer direct reuse of existing `pip`-based workflow and focused tests rather than inventing new wrapper scripts or setup layers.
- False confidence from wheel-only coverage.
  Control: keep wheel smoke for packaging integrity, but add a separate active-`.venv` assertion path so both install modes are proven.
- Accidental compatibility regression while touching adjacent runtime code.
  Control: keep implementation scope centered on editable-install state and proof; if any reader path is touched, rerun the narrow compatibility checks that already cover legacy-read behavior.

## Rollback
- If the editable reinstall leaves mixed-brand state, remove the conflicting editable install artifacts and recreate the repo `.venv` cleanly rather than shipping a partially repaired environment.
- If the new proof is noisy or path-fragile, simplify it to direct active-`.venv` assertions instead of adding broader infrastructure.
- Do not roll back by reintroducing `autoloop` import or CLI aliases.
