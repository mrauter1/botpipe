# Original intent considered

- Rename branded public API symbols from `Autoloop*` to `Botlane*` with no compatibility alias.
- Rename runtime, CLI, package-loading, workspace-loading, generated module, schema, docs, examples, fixtures, and packaged workflow identity from Autoloop to Botlane.
- Remove legacy import modules and legacy CLI identity, and prove the negative strictness conditions including no installed `autoloop` CLI and no importable `autoloop` packages.

# Clarifications / superseding decisions

- The raw log clarification answered `NO` to intentionally breaking old input readability: existing `.autoloop` workspaces, `autoloop.yaml` / `autoloop.config`, and persisted `autoloop.*` artifacts must remain readable or migratable, while all new writes become Botlane-only.
- The decisions ledger explicitly forbids `autoloop` or `autoloop_optimizer` import aliases and forbids an `autoloop` CLI alias.
- The final grep proof may exclude automation-owned generated state such as `.autoloop/tasks/**`, and within maintained docs the only retained legacy text allowed is an explicit `legacy_docs/*.md` history allowlist.

# Implemented behavior

- Packaging and public exports were renamed in source: [pyproject.toml](/home/rauter/autoloop_v3_bkp/autoloop_v3/pyproject.toml), [botlane/__init__.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/__init__.py), and the renamed `botlane/` plus `botlane_optimizer/` package roots now define the maintained API.
- Runtime identity is Botlane-first in maintained code: [botlane/runtime/cli.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/runtime/cli.py) uses `prog="botlane"` and Botlane help text; [botlane/runtime/workspace.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/runtime/workspace.py) writes `.botlane` while retaining a legacy reader; [botlane/runtime/loader.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/runtime/loader.py) uses `_botlane_workspace_workflows` and `botlane.workflows`.
- Canonical schemas now emit `botlane.*` in [botlane/core/schema_registry.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/schema_registry.py), with centralized legacy-read aliases for persisted `autoloop.*` payloads.
- Maintained strictness coverage was widened to the repo root in [tests/strictness/test_no_compat.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/strictness/test_no_compat.py), with only generated state and the explicit `legacy_docs/*.md` history allowlist excluded.
- Independent audit checks passed for maintained-tree branding proof and import/module removal:
  - `.venv/bin/python -m pytest -q tests/strictness/test_no_compat.py` -> `41 passed`
  - `.venv/bin/python -m autoloop` -> `No module named autoloop`
  - `.venv/bin/python` import checks for `autoloop` and `autoloop_optimizer` both raised `ModuleNotFoundError`

# Unresolved gaps

- The active run-local editable install is still Autoloop-branded, so the request’s installed-CLI outcome is not fully satisfied in the shared `.venv`.
  Evidence:
  - `.venv/bin/autoloop` exists and still imports `from autoloop.runtime.cli import main`.
  - `.venv/bin/autoloop --help` fails only because the `autoloop` module is gone, not because the executable was removed.
  - `.venv/bin/botlane` is missing.
  - `.venv/bin/pip show autoloop-v3-surface` succeeds, while `.venv/bin/pip show botlane-v3-surface` reports package not found.
  - `.venv/lib/python3.12/site-packages/autoloop_v3_surface-0.0.0.dist-info/entry_points.txt` still registers `autoloop = autoloop.runtime.cli:main`.
- This is material because the request explicitly required removing any installed `autoloop` executable and proving that the `botlane` CLI is installed instead.

# Differences justified by later clarification or analysis

- Legacy `.autoloop`, legacy config names, and legacy `autoloop.*` persisted schemas remain readable by design. That behavior is explicitly required by the raw-log clarification and is not a gap.
- Remaining raw `autoloop` text under `legacy_docs/*.md` is justified by the explicit history-file allowlist enforced in `tests/strictness/test_no_compat.py`.
- Automation-owned state under `.autoloop/tasks/**` remains out of scope for the live product rename per the decisions ledger.

# Recommended next run

- Update the run-local editable installation state so this repository’s active `.venv` installs `botlane-v3-surface` and exposes only the `botlane` console script.
- Add or strengthen validation so the active repo environment is checked alongside fresh-wheel smoke, preventing a stale editable `autoloop` install from surviving future rename work.
