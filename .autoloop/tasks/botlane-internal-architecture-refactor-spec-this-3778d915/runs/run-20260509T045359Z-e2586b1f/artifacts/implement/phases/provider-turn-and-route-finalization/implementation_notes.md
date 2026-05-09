# Implementation Notes

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: provider-turn-and-route-finalization
- Phase Directory Key: provider-turn-and-route-finalization
- Phase Title: Provider Turn Adapters
- Scope: phase-local producer artifact

## Files changed

- `botlane/core/engine_collaborators.py`
- `tests/contract/test_provider_turn_plan_adapter.py`
- `tests/strictness/test_no_compat.py`

## Symbols touched

- `ProviderContractBuilder.control_contract`
- `ProviderContractBuilder.pair_producer_contract`
- `ProviderContractBuilder.pair_verifier_contract`
- `ProviderContractBuilder._provider_turn_contract`
- `StepDispatcher._execute_llm_step_async`
- `StepDispatcher._run_llm_step_async`
- `StepDispatcher._execute_pair_step_async`
- `StepDispatcher._run_pair_step_async`
- `RouteFinalizationResult.decision`
- `RouteFinalizer.capture`
- `RouteFinalizer.finalize`

## Checklist mapping

- Phase 6 / provider-turn adapter: prompt and produce/verify execution now attempts a `ProviderTurnPlan` bridge before building the existing `LLMRequest` / `ProducerRequest` / `VerifierRequest` payloads.
- Phase 5 / route finalization adapter: `RouteFinalizationResult` now carries a typed `RouteDecision` bridge while the engine still consumes the legacy fields.
- Deliverable: added `tests/contract/test_provider_turn_plan_adapter.py`.

## Assumptions

- Existing compiled steps can still contain non-canonical short-name required refs in some parity paths, so the new turn-plan bridge must fall back cleanly to the compiled-step contract builder when plan adaptation cannot preserve behavior.

## Preserved invariants

- `RenderedProviderTurn` remains the transport input type.
- Provider transports still return `ProviderTurnResult`.
- Prompt and produce/verify engine execution still use the current request/render/result machinery.
- Engine loop control still reads `RouteFinalizationResult` legacy fields; `RouteDecision` is additive only.

## Intended behavior changes

- `RouteFinalizationResult` now exposes `decision` with internal typed route action data.
- Finalized `AWAIT_INPUT` routes now materialize `pending_input` directly in route finalization instead of relying on a later engine fallback.

## Known non-changes

- Operation execution was not migrated to `ProviderTurnPlan`.
- The engine was not switched to `WorkflowPlan`.
- `RouteFinalizationResult` was not replaced across the engine loop.

## Expected side effects

- Prompt/pair provider-turn planning is opportunistic: when typed plan adaptation succeeds and required refs are artifact-backed, provider contract payloads come from `ProviderTurnPlan`; otherwise the old compiled-step contract path is used unchanged.
- `tests/strictness/test_no_compat.py` now explicitly allows the focused `route_contracts` import in `engine_collaborators.py` required for the route-decision bridge.

## Validation performed

- `python3 -m compileall botlane/core/engine_collaborators.py tests/contract/test_provider_turn_plan_adapter.py tests/strictness/test_no_compat.py`
- `/home/rauter/autoloop_v3/.venv/bin/pytest tests/contract/test_provider_turn_plan_adapter.py`
- `/home/rauter/autoloop_v3/.venv/bin/pytest tests/contract/engine/test_runtime_controls.py`
- `/home/rauter/autoloop_v3/.venv/bin/pytest tests/contract/engine/test_routes.py`
- `/home/rauter/autoloop_v3/.venv/bin/pytest tests/contract/test_async_step_dispatcher.py tests/unit/test_route_contracts.py tests/unit/test_step_plans.py`
- `/home/rauter/autoloop_v3/.venv/bin/pytest tests/strictness/test_no_compat.py`
  - Fails due pre-existing environment leak: importable site-package `autoloop` in `/home/rauter/autoloop_v3/.venv/lib/python3.12/site-packages/autoloop`.

## Deduplication / centralization

- Centralized provider-turn bridging inside `ProviderContractBuilder` and the step dispatcher rather than creating a second provider request/result stack.
