Fix the run-local editable installation state for the Botlane rename.

The maintained source tree is renamed correctly, but the active repository virtualenv is still installed as `autoloop-v3-surface` and still exposes a stale `autoloop` console script:

- `.venv/bin/autoloop` exists and imports `autoloop.runtime.cli`.
- `.venv/bin/botlane` is missing.
- `.venv/bin/pip show autoloop-v3-surface` succeeds.
- `.venv/bin/pip show botlane-v3-surface` fails.
- `.venv/lib/python3.12/site-packages/autoloop_v3_surface-0.0.0.dist-info/entry_points.txt` still registers `autoloop = autoloop.runtime.cli:main`.

Required outcome:

- The active editable install for this repository is `botlane-v3-surface`, not `autoloop-v3-surface`.
- The active repo virtualenv installs `botlane` and does not install `autoloop`.
- Validation proves the run-local environment satisfies the CLI rename, not only a freshly built wheel.
- Do not reintroduce `autoloop` import aliases or CLI aliases.
- Preserve the existing clarification that legacy `.autoloop` workspaces, legacy config names, and persisted `autoloop.*` artifacts remain readable during transition while new writes stay Botlane-only.
