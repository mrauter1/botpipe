# Test Strategy

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: test
- Phase ID: editable-install-refresh-and-proof
- Phase Directory Key: editable-install-refresh-and-proof
- Phase Title: Refresh Editable Install And Prove It
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- AC-1 active editable distribution identity:
  `test_repo_local_editable_install_exposes_only_botlane_cli_identity` checks `pip show botlane-v3-surface` succeeds, `pip show autoloop-v3-surface` fails, and the active repo `.venv` points back to the repo root as an editable install.
- AC-2 active CLI and entry-point identity:
  the same repo-local test checks `.venv/bin/botlane` exists, `.venv/bin/autoloop` is absent, `botlane --help` stays Botlane-branded, and installed distribution metadata exposes only `botlane = botlane.runtime.cli:main`.
- AC-3 fresh-wheel proof remains intact:
  `test_built_wheel_installs_public_botlane_package_and_cli` still builds a wheel, installs it into a throwaway venv, validates the public package/workflow contents, and now also asserts installed distribution metadata is `botlane-v3-surface` with no `autoloop-v3-surface` residue.

## Preserved Invariants Checked

- No `autoloop` console script is installed in either the throwaway wheel venv or the shared repo `.venv`.
- No `autoloop` top-level import or legacy distribution remains available through the validated install surfaces.
- Packaging smoke subprocesses run from an isolated working directory so repo-root source metadata cannot mask installed-state regressions.

## Edge Cases / Failure Paths

- Missing repo-local `.venv` causes the shared-env proof to skip rather than produce a misleading pass in another execution context.
- Metadata assertions fail if either install mode leaves mixed-brand residue, wrong console entry points, or the old distribution name behind.

## Flake Risks / Stabilization

- The tests depend on local wheel build and virtualenv creation only; no network or time-based behavior is exercised.
- Isolation is stabilized by using `tmp_path` as the subprocess working directory for both the throwaway wheel venv and the shared `.venv` metadata checks.

## Known Gaps

- The repo-local proof assumes the shared `.venv` already exists; creating that environment remains out of scope for this phase.
