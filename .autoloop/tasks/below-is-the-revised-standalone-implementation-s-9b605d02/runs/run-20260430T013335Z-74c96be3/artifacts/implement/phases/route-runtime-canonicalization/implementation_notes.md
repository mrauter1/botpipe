# Implementation Notes

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: route-runtime-canonicalization
- Phase Directory Key: route-runtime-canonicalization
- Phase Title: Canonicalize Route And Runtime Internals
- Scope: phase-local producer artifact

## Files changed

- `core/routes.py`
- `core/steps.py`
- `core/_compat.py`
- `core/compiler.py`
- `core/validation.py`
- `core/primitives.py`
- `core/engine.py`
- `runtime/static_graph.py`
- `runtime/runner.py`
- `runtime/git_tracking.py`
- `stdlib/__init__.py`
- `stdlib/composition.py`
- deleted `stdlib/steps.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/runtime/test_provider_backends.py`
- `tests/contract/test_engine_contracts.py`
- `tests/contract/test_canonical_runtime_contracts.py`
- `tests/strictness/test_no_compat.py`
- `decisions.txt`

## Symbols touched

- `Route.to`, `Route.finish`, `Route.pause`, `Route.fail`
- `Step.route_metadata`
- `core._compat.RouteInfo`, `core._compat.LLMStep`, `core._compat.PairStep`, `core._compat.SystemStep`, `core._compat.WorkflowStep`
- `normalize_step_route_metadata`, `_valid_route_destinations`
- `_compile_route`
- `require_child_workflow_result`

## Checklist mapping

- Public/canonical route metadata: completed by replacing active `route_infos` handling with `Route`-based metadata and keyword-only route effects.
- Runtime/compiler/static-graph canonicalization: completed for active code paths; compiled targets and static-graph payloads no longer rewrite legacy terminals on the live surface.
- Stdlib legacy helper cleanup: completed by removing `stdlib.pair_step` and the `required_outputs` alias from composition helpers.
- Active suite migration / strictness: completed for touched active suites and strictness scan roots; explicit compatibility files remain excluded.

## Assumptions

- Legacy in-memory authoring remains allowed only through `core._compat` wrappers and the explicit compatibility suite.
- `pytest` is not available in this environment, so source validation had to stop at static compilation and text scans.

## Preserved invariants

- `core` and `autoloop_v3.core` still share module identity through the explicit bridge.
- Compatibility-only fixtures continue importing legacy names from `core._compat`.
- Active provider/runtime payloads continue exposing canonical `routes` and `route_required_writes`.

## Intended behavior changes

- Active route helpers reject positional effect DSL and require `effects=` or canonical `handoff=...`.
- Active `core.steps` no longer store/read legacy `route_infos`; legacy route metadata is normalized only by `core._compat`.
- Active stdlib no longer exposes `pair_step(...)` or `required_outputs=...`.

## Known non-changes

- Compatibility-only files were not migrated off `SUCCESS` / `RouteInfo`; they remain the quarantine boundary.
- Internal strict step class names (`LLMStep`, `PairStep`, `SystemStep`, `WorkflowStep`) still exist as implementation types.

## Expected side effects

- Active tests and strictness now reference `route_metadata`, `routes`, and `required_writes`.
- Any caller still using `stdlib.pair_step` or `require_child_workflow_result(..., required_outputs=...)` will fail immediately and must migrate.

## Validation performed

- `rg` scans for banned active tokens outside explicit compatibility files.
- `python3 -m py_compile` over the touched source and test modules.
- `python3 -m pytest ...` attempted but unavailable because `pytest` is not installed in this environment.

## Deduplication / centralization

- Centralized legacy route metadata and terminal handling in `core._compat` instead of leaving it spread across `core.routes`, `core.steps`, `core.compiler`, and `core.validation`.
