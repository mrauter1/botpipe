# Follow-up implementation request

Finish the cleanup that remains after the canonical public-surface pass.

Required scope:

1. Make the active public authoring surface fully canonical.
- `autoloop.simple` is documented as the active public authoring API, so trim it to the intended canonical exports only.
- Do not publicly re-export `AfterHookResult`, `Checkpoint`, `ChildWorkflowResult`, `ResolvedArtifacts`, `WorkflowStep`, or other non-canonical helpers from `autoloop.simple`.

2. Remove or quarantine the remaining legacy low-level contract from active `core` modules.
- `core/__init__.py`, `core/routes.py`, `core/primitives.py`, `core/steps.py`, `core/compiler.py`, and `core/validation.py` still retain `SUCCESS`, `RouteInfo`, `Param`, `StateVar`, `AfterHookResult`, `LLMStep`, `PairStep`, `SystemStep`, `produces`, `route_infos`, and `required_outputs`.
- Keep legacy support only where a real persisted-run reader needs it.
- If any compatibility surface must remain, move it behind an explicit internal compatibility module instead of leaving it on active top-level imports.
- Remove the dual package alias shim between `core` and `autoloop_v3.core` if it is no longer strictly required.

3. Finish route/runtime canonicalization internally.
- `Route.to(...)` should not keep positional effect DSL on the active surface.
- Active runtime/compiler/static-graph code should not carry `SUCCESS` or `required_outputs` handling except in private old-run migration readers.
- `stdlib` helpers that still expose `required_outputs`, `PairStep`, or `produces` vocabulary should be migrated or removed.

4. Finish the tests/strictness migration.
- Update strictness so it scans active code/tests and excludes only explicit migration fixtures.
- Migrate non-migration suites that still use legacy names, especially `tests/contract/test_engine_contracts.py`, `tests/unit/test_validation.py`, and any active runtime/unit/provider suites that still encode `SUCCESS`, `RouteInfo`, `PairStep`, `LLMStep`, `SystemStep`, `produces`, `route_infos`, or `required_outputs`.
- If some coverage is intentionally legacy-compat only, quarantine it clearly as compatibility/migration coverage rather than leaving it in the main active suites.

Acceptance criteria:

- `autoloop.simple` exports only the intended canonical authoring surface.
- Active top-level `core` imports no longer expose the removed legacy names.
- Active compiler/runtime/static-graph/provider code paths no longer depend on `RouteInfo`, `SUCCESS`, `produces`, `route_infos`, or `required_outputs`, except inside explicit persisted-run migration readers.
- Strictness tests scan the active implementation/test surface and fail on remaining banned names outside explicit migration fixtures.
- The canonical verification suite still passes after the deeper cleanup.
