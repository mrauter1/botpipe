# Gap Report

## Original intent considered

- Repair the active repository `.venv` so the editable install is `botlane-v3-surface`, not `autoloop-v3-surface`.
- Ensure the active repo virtualenv installs `botlane`, does not install `autoloop`, and proves that state in the run-local environment rather than only in a throwaway wheel install.
- Avoid reintroducing `autoloop` import aliases or CLI aliases.
- Preserve the earlier transition clarification that legacy `.autoloop` workspaces, legacy config names, and persisted `autoloop.*` artifacts remain readable while new writes stay Botlane-only.

## Clarifications / superseding decisions

- `decisions.txt` block 1 requires fixing the active repo `.venv` itself and says wheel-only proof is insufficient.
- `decisions.txt` block 1 also preserves the no-alias rule and limits legacy compatibility to persisted-state readers.
- `decisions.txt` block 2 records that packaging smoke subprocesses must run from an isolated working directory so repo-root source metadata cannot shadow the installed distribution under test.
- `decisions.txt` block 3 records that the fresh-wheel smoke path should also assert installed distribution identity, not only CLI/import behavior.

## Implemented behavior

- `pyproject.toml` publishes only `botlane-v3-surface` and only the `botlane` console script.
- `tests/runtime/test_wheel_packaging_smoke.py:36-158` now proves a built wheel installs `botlane-v3-surface`, exposes only `botlane`, and leaves no `autoloop-v3-surface` distribution behind.
- `tests/runtime/test_wheel_packaging_smoke.py:161-214` adds a repo-local editable-install proof against `REPO_ROOT/.venv`, including `pip show botlane-v3-surface`, `pip show autoloop-v3-surface` failure, `botlane` script presence, `autoloop` script absence, and installed entry-point metadata checks.
- Final run-local environment evidence from this audit:
  - `./.venv/bin/pip show botlane-v3-surface` succeeds and reports `Editable project location: /home/rauter/autoloop_v3_bkp/autoloop_v3`.
  - `./.venv/bin/pip show autoloop-v3-surface` fails with `Package(s) not found`.
  - `.venv/bin/botlane` exists and `.venv/bin/autoloop` is absent.
  - `.venv/lib/python3.12/site-packages/botlane_v3_surface-0.0.0.dist-info/entry_points.txt` contains only `botlane = botlane.runtime.cli:main`.
  - `./.venv/bin/pytest -q tests/runtime/test_wheel_packaging_smoke.py` passes with `2 passed`.

## Unresolved gaps

- No material unresolved gaps found in the requested run-local scope.

## Differences justified by later clarification or analysis

- No runtime compatibility-reader code was changed. That is consistent with the request because the stale state was in the active `.venv`, not in maintained source metadata or persisted-artifact readers.
- The repo-local editable-install proof skips when `REPO_ROOT/.venv` is absent. That is acceptable because this task is explicitly run-local and the request required validating the active repository virtualenv, not inventing a new environment bootstrap path.
- The added isolated-working-directory behavior in packaging smoke is a justified tightening, not a scope change: it prevents false positives caused by repo-root source metadata shadowing the installed distribution being validated.

## Recommended next run

- No follow-up implementation run is required for this request.
- The next step is audit verification / closeout only.
