# Workflow Installation / Discovery Follow-up Plan

## Objective
Close the remaining validation gaps in the workflow-installation/discovery migration without reintroducing legacy implicit discovery from `{workspace}/workflows/`.

## Scope And Invariants
- Keep implicit bare-name and alias discovery limited to `autoloop/workflows/` and `{workspace}/.autoloop/workflows/`.
- Preserve `{workspace}/workflows/` coverage only for explicit filesystem-path or explicit Python-module references; do not let any bare-name expectation depend on that root.
- Keep workspace-isolated import assertions aligned with the loader’s `_autoloop_workspace_workflows.<12-char-sha1>...` namespace for explicit workspace-path loading.
- Keep the packaging smoke focused on building one wheel, installing it into a clean venv, and proving the CLI plus packaged workflow assets ship correctly.

## Implementation Milestones
1. Align `tests/runtime/test_workflow_reference_resolution.py` to the shipped contract.
   - Rework fixtures/helpers so bare-name and alias discovery cases create workflows under `{workspace}/.autoloop/workflows/` or the package-installed `autoloop/workflows/` root, not `{workspace}/workflows/`.
   - Keep explicit path and explicit module/path cases that intentionally exercise `{workspace}/workflows/`, but assert them through explicit references only.
   - Update module-name expectations for isolated workspace imports to `_autoloop_workspace_workflows.<hash>...` where the loader now synthesizes hashed namespace packages.
2. Make `tests/runtime/test_wheel_packaging_smoke.py` self-sufficient in the standard validation environment.
   - Replace the direct dependency on an already-installed `build` frontend with a wheel-build path the baseline validation interpreter can execute without extra global packages.
   - Preserve the current post-build checks: wheel exists, installs into a fresh venv, CLI help works, packaged workflows list as package-owned, and packaged prompt/asset files are present.
3. Re-run the affected validation slice in the normal project test environment.
   - `tests/runtime/test_workflow_reference_resolution.py`
   - `tests/runtime/test_workflow_catalog_roots.py`
   - `tests/runtime/test_runtime_cli_metadata_integration.py`
   - `tests/runtime/test_package_cli.py`
   - `tests/runtime/test_wheel_packaging_smoke.py`

## Interfaces / Behavior Notes
- Public workflow discovery contract:
  - implicit discovery roots: `autoloop/workflows/`, `{workspace}/.autoloop/workflows/`
  - explicit-only root: `{workspace}/workflows/`
- Isolated workspace package imports:
  - package/directory loads use `_autoloop_workspace_workflows.<package-path-hash>.<workflow_id>[.<module>]`
  - single-file loads use `_autoloop_workspace_workflows.<file-path-hash>.<workflow_id>`
- Packaging smoke contract:
  - the test must not assume the host validation interpreter already has the `build` frontend installed
  - the wheel artifact and install/runtime assertions remain unchanged in coverage

## Regression Risks And Controls
- Risk: a rewritten resolution test accidentally reintroduces bare-name coverage from `{workspace}/workflows/`.
  - Control: separate bare-name fixtures from explicit-path fixtures and keep assertions on `source_root_kind`, `source_root`, and resolved source paths.
- Risk: changing the wheel-build command weakens the smoke semantics.
  - Control: keep the rest of the test intact so only the wheel-construction mechanism changes, not the install/assertion coverage.
- Risk: module namespace assertions become brittle if they still depend on old `workflows.*` or `_autoloop_dynamic_*` names for workspace package loads.
  - Control: assert the stable namespace prefix and hashed package pattern the loader currently generates.

## Validation And Rollback
- Validation target: the five named runtime/package suites above in the standard project validation environment.
- Expected outcome: no failing test still expects implicit discovery from `{workspace}/workflows/`, and the wheel smoke passes without an ambient `build` install.
- Rollback if needed: revert only the follow-up test changes and wheel-smoke build-path change; do not relax the runtime discovery implementation back to legacy roots.
