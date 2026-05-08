# Implementation Notes

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: implement
- Phase ID: rename-package-and-public-api
- Phase Directory Key: rename-package-and-public-api
- Phase Title: Rename Package And Public API
- Scope: phase-local producer artifact

## Files Changed
- Renamed package roots: `autoloop/` -> `botlane/`, `autoloop_optimizer/` -> `botlane_optimizer/`.
- Updated packaging metadata in `pyproject.toml`.
- Updated package-coupled runtime/import code in `botlane/core/workflow_catalog.py`, `botlane/runtime/loader.py`, `botlane/runtime/cli.py`, `botlane/core/discovery.py`, `botlane/core/descriptors.py`, `botlane/core/workflow_capabilities.py`, `botlane/core/context.py`, `botlane/core/branch_groups/outcomes.py`, `botlane_optimizer/candidate_surfaces.py`, and `botlane_optimizer/optimization.py`.
- Updated focused public-surface/package tests in `tests/unit/test_simple_surface.py`, `tests/unit/test_sdk_facade.py`, `tests/runtime/test_sdk_policy.py`, `tests/runtime/test_workflow_catalog_roots.py`, `tests/runtime/test_runtime_cli_metadata_integration.py`, `tests/runtime/test_workflow_reference_resolution.py`, `tests/runtime/test_golden_workflow.py`, `tests/runtime/test_optional_extensions.py`, `tests/runtime/test_package_cli.py`, `tests/runtime/test_wheel_packaging_smoke.py`, `tests/unit/_stdlib_and_extensions_shared.py`, `tests/unit/stdlib/test_authoring_helpers.py`, `tests/contract/engine/test_core_contracts.py`, and `tests/strictness/test_no_compat.py`.
- Removed stale generated packaging artifacts: `autoloop_v3_surface.egg-info/` and `build/`.

## Symbols Touched
- Public facade/class rename: `Autoloop` -> `Botlane`.
- Public SDK exception rename: `AutoloopSDKError` -> `BotlaneSDKError`.
- Canonical package names/imports: `autoloop` -> `botlane`, `autoloop_optimizer` -> `botlane_optimizer`.
- Package workflow namespace strings required for importability: `autoloop.workflows` -> `botlane.workflows`.

## Checklist Mapping
- Plan milestone 1 / P1-AC1: completed.
  Renamed package roots, updated maintained imports that depended on those roots, and removed `Autoloop`-branded exported public symbols.
- Plan milestone 1 / P1-AC2: completed.
  Updated project name/entry point/package discovery to Botlane and removed the legacy wheel metadata that still emitted `autoloop`.
- Later milestones intentionally deferred in this phase: workspace `.autoloop` path migration, generated module namespace migration, and broader `autoloop.*` schema/artifact rewrites.

## Assumptions
- Existing `.autoloop` workspace/state/config readers remain supported during transition per the authoritative clarification.

## Preserved Invariants
- Runtime state still writes/reads `.autoloop` paths in this phase.
- SDK task sentinel filename remains `.autoloop-sdk-task.json` in this phase.
- Existing schema/artifact identifiers outside the package/public API slice were not renamed here.

## Intended Behavior Changes
- Canonical public imports are now `botlane` / `botlane_optimizer`.
- Public SDK facade exports are now `Botlane` and `BotlaneSDKError`; no `Autoloop` compatibility export remains.
- Built wheels now install the `botlane` console script and no `autoloop` console script.
- Built-wheel smoke now proves `botlane` imports work while `autoloop`, `autoloop_optimizer`, and `python -m autoloop` fail.

## Known Non-Changes
- `.autoloop` workspace directories, workspace help-path text, and `_autoloop_workspace_workflows` remain for later phases.
- Product-branded schema IDs such as `autoloop.*` outside the SDK cleanup fixture updates remain for later phases.

## Expected Side Effects
- Package-installed workflow discovery now resolves through `botlane.workflows`.
- Stale local packaging outputs from the old Autoloop name no longer contaminate new wheel builds.

## Validation Performed
- `.venv/bin/pytest tests/unit/test_simple_surface.py tests/unit/test_sdk_facade.py tests/runtime/test_sdk_policy.py tests/runtime/test_workflow_catalog_roots.py tests/runtime/test_runtime_cli_metadata_integration.py tests/runtime/test_workflow_reference_resolution.py tests/strictness/test_no_compat.py tests/runtime/test_wheel_packaging_smoke.py -q`
- Result: `230 passed`.

## Centralization / Deduplication
- Reused the existing package-workflow discovery/loading seams; only the canonical package roots/prefix strings were updated instead of introducing compatibility shims or alias layers.
