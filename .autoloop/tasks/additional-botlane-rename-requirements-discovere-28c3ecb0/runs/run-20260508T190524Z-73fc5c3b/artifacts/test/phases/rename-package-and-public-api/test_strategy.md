# Test Strategy

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: test
- Phase ID: rename-package-and-public-api
- Phase Directory Key: rename-package-and-public-api
- Phase Title: Rename Package And Public API
- Scope: phase-local producer artifact

## Coverage Map

- Public package surface:
  `tests/unit/test_simple_surface.py` covers `botlane.__all__` and the renamed `Botlane` / `BotlaneSDKError` public exports.
- Packaged workflow identity:
  `tests/runtime/test_workflow_catalog_roots.py` now covers the live bundled package entry `botlane_v1`, its `botlane.workflows.botlane_v1` module path, the `botlane-v1` alias, and the failure path for `autoloop_v1`.
- CLI identity:
  `tests/runtime/test_runtime_cli_metadata_integration.py` covers the Botlane-only workspace help text and ensures public help no longer advertises `.autoloop/workflows/`.
- Installed artifact identity:
  `tests/runtime/test_wheel_packaging_smoke.py` covers wheel installation of the `botlane` CLI, absence of the `autoloop` CLI, top-level import failure for `autoloop` and `autoloop_optimizer`, `python -m autoloop` failure, and installed importability of `botlane.workflows.botlane_v1`.

## Preserved Invariants Checked

- Existing `.autoloop` workspace/runtime path behavior remains outside this phase and is not normalized by these tests.
- The bundled parity workflow may retain legacy artifact/header internals while its public import path and exported symbol are Botlane-branded.

## Edge Cases And Failure Paths

- Alias resolution succeeds for `botlane-v1` while the removed `autoloop_v1` name is rejected.
- Installed-wheel smoke asserts the old bundled module path `botlane.workflows.autoloop_v1` is absent.

## Flake Risk And Stabilization

- Package-surface checks use deterministic local imports and catalog resolution only; no network or timing dependency is introduced beyond the existing wheel build/install smoke.

## Known Gaps

- This phase does not add assertions for later-phase `.botlane` workspace path migration, `_botlane_workspace_workflows`, or `botlane.*` schema IDs because those behaviors remain intentionally deferred.
