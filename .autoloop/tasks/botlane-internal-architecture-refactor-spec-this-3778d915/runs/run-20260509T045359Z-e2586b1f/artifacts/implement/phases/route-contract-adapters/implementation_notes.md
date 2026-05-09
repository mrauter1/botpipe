# Implementation Notes

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: route-contract-adapters
- Phase Directory Key: route-contract-adapters
- Phase Title: Route Contract Adapters
- Scope: phase-local producer artifact

## Files Changed

- `botlane/core/route_contracts.py`
- `botlane/core/plan_adapters.py`
- `tests/unit/test_route_contracts.py`
- `tests/strictness/test_no_compat.py`

## Symbols Touched

- `RouteTarget`, `PayloadContract`, `RouteFieldsContract`, `ProviderRoutePolicy`
- `RequiredWriteContract`, `RouteContract`
- `Continue`, `Finish`, `AwaitInput`, `FailAction`, `RouteDecision`
- `route_action_for_contract`, `available_route_tags`, `runtime_control_route_tags`, `provider_visible_route_tags`
- `route_contract_from_compiled_route`, `compiled_route_from_route_contract`
- `COMPATIBILITY_TOKEN_ALLOWLIST`

## Checklist Mapping

- Plan milestone 3: added internal route contract/action values and route-view helpers.
- Plan milestone 3: replaced routing adapter stubs in `plan_adapters.py` with `CompiledRoute` round-trips.
- Phase acceptance AC-1: added unit coverage for target mapping, visibility, schema payloads, runtime-control flags, disabled routes, required-write inventory conversion, and missing-inventory failure.

## Assumptions

- `WorkflowPlan` is not introduced yet, so route-view helpers derive from any plan-like object exposing `routes[step_name]`.
- Route-action conversion for disabled routes remains an internal error path because disabled routes are not runtime-selectable.

## Preserved Invariants

- No public exports were changed; `RouteContract`/`RouteDecision` stay internal-module imports only.
- `CompiledRoute` remains the compatibility object consumed by existing runtime/compiler flows.
- Required-write identity conversion uses inventory resolution, not qualified-name dot splitting.
- Missing inventory only fails for non-empty `required_writes`, preserving the phase contract.

## Intended Behavior Changes

- Internal only: route metadata can now be represented as typed `RouteContract` / `RouteDecision` values and round-tripped back to `CompiledRoute`.

## Known Non-Changes

- Engine loop still consumes existing compiled/finalization shapes; no `RouteAction` execution migration yet.
- No changes to public route authoring (`FINISH`, `AWAIT_INPUT`, `FAIL`, `SELF`, `Route(...)`).
- No workflow-plan, step-plan, or provider-turn migration in this phase.

## Expected Side Effects

- `tests/strictness/test_no_compat.py` now explicitly allows the approved internal route-contract names only in the new internal module, adapter, and dedicated unit test.

## Validation Performed

- `./.venv/bin/python -m pytest tests/unit/test_route_contracts.py tests/unit/test_artifact_ids.py`
- `./.venv/bin/python -m pytest tests/unit/test_simple_surface.py tests/unit/test_sdk_facade.py tests/strictness/test_no_compat.py`

## Deduplication / Centralization

- Kept all compiled-route conversion logic centralized in `botlane/core/plan_adapters.py`.
- Kept derived route tag views centralized in `botlane/core/route_contracts.py` rather than duplicating them onto step metadata.
