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
- `tests/runtime/test_compatibility_runtime.py`
- `tests/fixtures/toy_runtime_workflow.py`
- `tests/contract/test_engine_contracts.py`
- `tests/contract/test_canonical_runtime_contracts.py`
- `tests/strictness/test_no_compat.py`
- `decisions.txt`

## Symbols touched

- `Route.to`, `Route.finish`, `Route.pause`, `Route.fail`
- `Step.route_metadata`
- `core._compat.__all__`
- `normalize_step_route_metadata`, `_valid_route_destinations`
- `_compile_route`
- `require_child_workflow_result`
- `tests/runtime/test_compatibility_runtime.py::_write_workflow_package`

## Checklist mapping

- Public/canonical route metadata: completed by replacing active `route_infos` handling with `Route`-based metadata and keyword-only route effects.
- Runtime/compiler/static-graph canonicalization: completed for active code paths; compiled targets and static-graph payloads no longer rewrite legacy terminals on the live surface.
- Stdlib legacy helper cleanup: completed by removing `stdlib.pair_step` and the `required_outputs` alias from composition helpers.
- Active suite migration / strictness: completed for touched active suites and strictness scan roots; explicit compatibility files remain excluded.

## Assumptions

- Persisted session/checkpoint readers remain the only legitimate legacy compatibility seam in this checkout.
- `pytest` is not available in this environment, so source validation had to stop at static compilation and text scans.

## Preserved invariants

- `core` and `autoloop_v3.core` still share module identity through the explicit bridge.
- Persisted session/checkpoint payload readers continue normalizing legacy on-disk session key shapes.
- Active provider/runtime payloads continue exposing canonical `routes` and `required_writes`.

## Intended behavior changes

- Active route helpers reject positional effect DSL and require `effects=` or canonical `handoff=...`.
- Active compiler and validation no longer accept `SUCCESS` or legacy compat markers from `core._compat`.
- `core._compat` no longer exposes live step wrappers, `SUCCESS`, or `RouteInfo`.
- Active stdlib no longer exposes `pair_step(...)` or `required_outputs=...`.

## Known non-changes

- Internal strict step class names (`LLMStep`, `PairStep`, `SystemStep`, `WorkflowStep`) still exist as implementation types.
- The `core` to `autoloop_v3.core` bridge remains unchanged in this phase.

## Expected side effects

- Active tests and strictness now reference `route_metadata`, `routes`, and `required_writes`.
- Runtime discovery/inspection fixtures that only needed ordinary in-memory workflows now compile through canonical `core.steps` imports and `FINISH`.
- Any caller still using `stdlib.pair_step` or `require_child_workflow_result(..., required_outputs=...)` will fail immediately and must migrate.

## Validation performed

- `rg` scans for banned active tokens outside explicit compatibility files.
- `python3 -m py_compile` over the touched source and test modules.
- `python3 -m pytest ...` attempted but unavailable because `pytest` is not installed in this environment.

## Deduplication / centralization

- Removed the residual `core._compat` dependency from active compiler/validation instead of keeping a split legacy path in both the quarantine module and live route compilation.
