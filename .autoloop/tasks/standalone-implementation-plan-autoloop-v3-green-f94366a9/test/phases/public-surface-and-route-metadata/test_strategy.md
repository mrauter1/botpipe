# Test Strategy

- Task ID: standalone-implementation-plan-autoloop-v3-green-f94366a9
- Pair: test
- Phase ID: public-surface-and-route-metadata
- Phase Directory Key: public-surface-and-route-metadata
- Phase Title: Public surface and route metadata
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Public additive surface:
  `tests/unit/test_simple_surface.py`
  Covers `autoloop` re-exports, explicit `autoloop.simple` helper signatures, `AfterHookResult`, absence of `RouteContract`, `system_step(fn)` lowering, the documented `system_step(fn)` signature/return normalization matrix, and core `WorkflowStep` lowering.
- Legacy `workflow` shim behavior:
  `tests/unit/test_primitives_and_stores.py`
  Covers the post-cleanup shim contract: no authoring exports on `workflow`, primitives remain importable via `workflow.primitives`, and hidden internal submodules stay unavailable.
- Route metadata normalization:
  `tests/unit/test_validation.py`
  Covers `route_infos` on core steps, explicit rejection of legacy `route_contracts=` on core step constructors, normalized `route_required_outputs`, unknown-route rejection, unknown/invalid required-output rejection, handoff conflict rejection, and `Route.complete(required_outputs=...)` precedence over step defaults.
- Stdlib helper and inspection payload compatibility:
  `tests/unit/test_stdlib_and_extensions.py`
  Covers `review_gate_contracts` / `publication_gate_contracts` returning `RouteInfo`, selected-workflow capability/decomposition payloads emitting `route_infos` and `route_required_outputs`, generated strict sample workflows importing from `autoloop_v3.core`, and authoring-doc assertions using the current route-metadata wording.

## Preserved Invariants Checked

- `RouteContract` is not part of the active simple public surface.
- The root `workflow` package is no longer a second authoring API.
- Capability inspection payloads describe route metadata without legacy `route_contracts`.
- Strict/core authoring remains available for generated workflow fixtures.

## Edge And Failure Paths

- Unknown route metadata keys fail validation.
- Unknown route required outputs fail validation.
- Route required outputs that are not produced by the step fail validation.
- Conflicting route handoff metadata fails validation.
- Legacy `route_contracts=` constructor usage fails immediately on core steps.
- `system_step(fn)` normalizes `None`, `BaseModel`, route strings, `Event`, `(state, route)`, and `(state, Event)` returns without depending on runtime hooks.

## Validation Performed

- `python3 -m py_compile tests/unit/test_primitives_and_stores.py tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py`
- Attempted targeted `pytest` execution, but `/usr/bin/python3` in this shell does not have `pytest` installed.

## Known Gaps

- No runtime pytest execution in this environment, so these updates are syntax-checked but not executed here.
