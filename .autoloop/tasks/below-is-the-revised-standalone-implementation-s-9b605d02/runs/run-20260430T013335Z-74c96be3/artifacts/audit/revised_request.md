# Follow-up implementation request

Finish the remaining canonical cleanup that was left behind after the previous pass.

Required scope:

1. Remove the remaining active `produces` contract from maintained `core` code paths.
- `core/steps.py`, `core/compiler.py`, `core/validation.py`, `core/engine.py`, and any related maintained runtime/static-graph/provider helpers still use `produces` and related live vocabulary such as `review_produces` / `do_produces`.
- Migrate these active code paths to canonical write/output terminology.
- Keep legacy support only where a real persisted-run/session/checkpoint reader truly needs it.

2. Finish the active-suite migration for the same vocabulary.
- Migrate non-migration suites that still author active workflows with `produces`, especially `tests/unit/test_validation.py` and `tests/contract/test_engine_contracts.py`.
- Re-check runtime/provider suites and the current compatibility suite. If some coverage is intentionally persisted-payload/session/checkpoint compatibility only, quarantine it clearly as compatibility coverage instead of leaving live in-memory workflow declarations on the excluded surface.

3. Tighten strictness to catch the remaining banned vocabulary.
- Update `tests/strictness/test_no_compat.py` so the maintained-tree scan fails on remaining active `produces` usage outside explicit migration fixtures.
- Keep the scan focused on maintained code/tests and exclude only explicit migration fixtures.

4. Remove the redundant dual-package alias shim if it is no longer strictly required.
- `autoloop_v3/core/__init__.py` already provides the explicit compatibility bridge.
- Remove the additional dynamic aliasing from `core/__init__.py` unless there is a concrete remaining requirement that cannot be handled by the explicit bridge alone.

Acceptance criteria:

- Active `core` authoring/runtime/compiler/validation/engine code paths no longer depend on `produces` or closely related live legacy vocabulary except inside explicit persisted-run/session/checkpoint migration readers.
- Active non-migration suites no longer use `produces`; any intentionally legacy-only coverage is clearly quarantined as compatibility/migration coverage.
- Strictness fails on remaining banned `produces` usage outside explicit migration fixtures.
- The redundant `core` package alias shim is removed, or any remaining compatibility mechanism is reduced to one explicit, justified path.
- The canonical verification suite still passes after the remaining cleanup.
