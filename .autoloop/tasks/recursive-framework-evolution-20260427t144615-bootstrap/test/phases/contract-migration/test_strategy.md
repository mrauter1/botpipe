# Test Strategy

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: test
- Phase ID: contract-migration
- Phase Directory Key: contract-migration
- Phase Title: Compiler And Contract Migration
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- `reads` vs `requires` compilation and validation:
  - Covered by `tests/unit/test_validation.py`.
  - Checks optional readable inputs compile separately from required inputs.
  - Checks impossible future `reads` / `requires` dependencies fail validation.
- Route metadata normalization and compatibility:
  - Covered by `tests/unit/test_validation.py`.
  - Checks legacy `route_contracts` still normalize into compiled `route_infos` / `route_required_outputs`.
  - Checks explicit `Route.complete(summary=..., required_outputs=...)` works without legacy contracts.
  - Checks route-required outputs must be produced by the source step for both explicit and legacy paths.
- Provider payload and rendering vocabulary:
  - Covered by `tests/unit/test_provider_boundary_core.py` and `tests/contract/test_engine_contracts.py`.
  - Checks readable inputs, required inputs, route infos, route-required outputs, and legacy aliases are all present.
  - Checks required-input rows render as required even when artifact declarations are optional.
  - Checks `route_infos` summaries win over legacy `route_contracts` summaries during rendering.
- Non-exclusive writable-artifact invariant:
  - Covered by `tests/unit/test_provider_boundary_core.py`.
  - Checks rendering language says declared writable artifacts are governed surfaces, not an exclusive allow-list.
- Static metadata surfaces:
  - Covered by `tests/runtime/test_runtime_static_graph.py`.
  - Checks static graph payload includes `reads`, `route_infos`, and `route_required_outputs` alongside legacy fields.

## Preserved invariants checked
- Legacy `route_contracts` remain available to existing callers.
- `route_required_artifacts` stays as the narrow compatibility alias while `route_required_outputs` carries the fuller migrated view.
- Runtime missing-artifact failure semantics remain owned by `requires`, not `reads`.

## Edge cases and failure paths
- Missing prompt text still fails provider rendering deterministically.
- Explicit and legacy route-required outputs that point at non-produced artifacts fail validation.
- Optional artifacts used as required inputs still render as required runtime preconditions.

## Flake risks and stabilization
- No timing, network, or nondeterministic ordering dependencies were added.
- Coverage uses in-process unit/runtime tests with fixed fixtures and `.venv/bin/python -m pytest ... -q` commands.

## Known gaps
- This phase does not add bundled-workflow source migration coverage because source migration is explicitly out of scope.
- Full docs/baseline text assertions for the new rendering vocabulary remain outside this phase-local test slice.
