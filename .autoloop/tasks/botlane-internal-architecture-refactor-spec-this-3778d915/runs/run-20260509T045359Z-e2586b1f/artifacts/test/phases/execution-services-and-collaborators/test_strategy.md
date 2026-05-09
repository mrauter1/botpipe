# Test Strategy

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: test
- Phase ID: execution-services-and-collaborators
- Phase Directory Key: execution-services-and-collaborators
- Phase Title: Execution Services
- Scope: phase-local producer artifact

## Behaviors Covered

- `ArtifactGuard` delegates artifact enforcement through `ExecutionServices.artifacts`
- `ArtifactGuard` rejects missing artifact service with a clear constructor error
- `RouteFinalizer.capture(...)` executes against injected artifact/route/hook/state services and still produces a `Finish` route decision
- `RouteFinalizer` rejects missing required services (`artifacts`, `routes`, `hooks`, `state`) with clear constructor errors

## Preserved Invariants Checked

- Engine route/runtime-control behavior remains covered by existing contract suites after the seam migration
- No strictness regression from the new internal module/test names
- The service-backed seam does not require widening public or semi-public APIs

## Edge Cases

- Empty `ExecutionServices()` bundle for `ArtifactGuard`
- Partially populated `ExecutionServices` bundles for `RouteFinalizer`

## Failure Paths

- Constructor validation for missing service dependencies
- Strictness scan for forbidden internal compatibility tokens after adding new phase tests

## Validation Runs

- `.venv/bin/python -m pytest tests/contract/engine/test_execution_services.py tests/contract/engine/test_runtime_controls.py tests/contract/engine/test_routes.py tests/strictness/test_no_compat.py`

## Flake Risks / Stabilization

- No timing or network dependency
- Service seam tests use local stubs and in-memory stores only
- Route/runtime behavior relies on existing deterministic engine contract suites instead of new async timing-sensitive cases

## Known Gaps

- This phase does not add new stub-heavy tests for `RouteFinalizer.finalize(...)` runtime-control branches because existing engine route/runtime-control suites already exercise those behaviors after wiring.
