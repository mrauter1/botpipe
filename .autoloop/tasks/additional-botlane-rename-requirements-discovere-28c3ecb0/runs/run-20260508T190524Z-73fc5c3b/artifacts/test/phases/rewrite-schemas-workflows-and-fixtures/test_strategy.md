# Test Strategy

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: test
- Phase ID: rewrite-schemas-workflows-and-fixtures
- Phase Directory Key: rewrite-schemas-workflows-and-fixtures
- Phase Title: Rewrite Schemas Workflows And Fixtures
- Scope: phase-local producer artifact

## Behavior Coverage Map

- P3-AC1 new Botlane-only schema/output writes:
  `tests/contract/test_branch_group_runtime.py`, `tests/unit/test_optimization_helpers.py`, `tests/runtime/test_runtime_static_graph.py`, `tests/runtime/test_runtime_tracing.py`
- P3-AC2 live workflow/docs/example/fixture identity is Botlane-only:
  `tests/strictness/test_no_compat.py`, `tests/runtime/test_package_cli.py`, `tests/runtime/test_runtime_cli_metadata_integration.py`, `tests/runtime/test_wheel_packaging_smoke.py`, `tests/runtime/test_workflow_catalog_roots.py`
- P3-AC3 persisted legacy `autoloop.*` artifacts remain readable:
  `tests/contract/engine/test_prompt_context.py` for legacy operation replay payloads,
  `tests/runtime/test_workspace_and_context.py` for legacy state-root reads/resume,
  `tests/runtime/test_provider_policy_config.py` for legacy config filenames,
  `tests/unit/test_sdk_facade.py` for legacy SDK sentinels,
  `tests/runtime/test_history.py` for legacy runtime-trace schema aliases

## Preserved Invariants Checked

- No installed `autoloop` CLI or importable `autoloop` / `autoloop_optimizer` package surface remains.
- Maintained-tree grep proof covers `botlane`, `botlane_optimizer`, `docs`, `tests`, and `pyproject.toml`.
- Current emitted paths and fixtures use `.botlane`, while legacy reads still work where the transition policy requires them.

## Edge Cases / Failure Paths

- Unsupported legacy schema versions still fail (`tests/contract/engine/test_prompt_context.py`).
- Catalog precedence still prefers current `.botlane/workflows` over legacy `.autoloop/workflows`.
- Help text and built-wheel smoke tests catch stale product naming in shipped interfaces.

## Flake Risk / Stabilization

- Coverage is filesystem-local and deterministic; no network or time-sensitive assertions were added.
- Legacy-name checks use constructed strings in maintained tests so strictness grep remains stable without weakening compatibility assertions.

## Known Gaps

- Full repository-wide historical text allowlisting remains outside this phase; coverage intentionally targets the maintained product tree only.
