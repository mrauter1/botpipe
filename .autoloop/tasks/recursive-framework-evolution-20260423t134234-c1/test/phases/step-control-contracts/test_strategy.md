# Test Strategy

- Task ID: recursive-framework-evolution-20260423t134234-c1
- Pair: test
- Phase ID: step-control-contracts
- Phase Directory Key: step-control-contracts
- Phase Title: Add Step Control Contracts
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Step declaration and compilation
  - `tests/unit/test_validation.py`
  - Covers optional step-owned `expected_output_schema` / `route_contracts`, compiled `available_routes`, `SystemStep` rejection, unknown route-contract routes, missing application-route contracts, and dependency-gated raw JSON schema mappings.
- Engine and provider request plumbing
  - `tests/contract/test_engine_contracts.py`
  - Covers LLM and pair request propagation of `expected_output_schema`, `available_routes`, and `route_contracts`, plus runtime failures for illegal route tags and invalid payloads.
- Preserved runtime behavior
  - `tests/runtime/test_workflow_integration_parity.py`
  - `tests/runtime/test_workspace_and_context.py`
  - `tests/runtime/test_optional_extensions.py`
  - `tests/runtime/test_compatibility_runtime.py`
  - Covers unchanged `autoloop_v1` parity, workspace/context flows, optional extensions, and compatibility runtime behavior after the engine changes.

## Preserved invariants checked

- `Outcome.tag` remains the route carrier.
- `available_routes` are derived mechanically from step-local transitions plus legal global routes.
- Workflows without control contracts still execute under the existing runtime and parity surfaces.

## Edge cases and failure paths

- `SystemStep` cannot declare provider-owned control contracts.
- Partially declared `route_contracts` fail validation when non-reserved application routes are missing.
- Invalid provider route tags fail fast and checkpoint.
- Invalid payloads against declared schemas fail fast and checkpoint.
- Raw JSON schema mappings fail deterministically with a clear validation error when `jsonschema` is unavailable.

## Flake risks and stabilization

- All coverage uses temp directories, in-memory stores, scripted providers, and deterministic route ordering.
- The raw-schema dependency-gate test monkeypatches `__import__` so it does not depend on the ambient environment.
- No timing, network, or external service dependencies are involved.

## Known gaps

- There is no happy-path runtime test for raw JSON schema mappings because the project venv does not currently provide `jsonschema`; if that dependency becomes first-class, add an execute-time success test for that branch.
