# Test Strategy

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: test
- Phase ID: provider-turn-and-route-finalization
- Phase Directory Key: provider-turn-and-route-finalization
- Phase Title: Provider Turn Adapters
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Prompt-step `ProviderTurnPlan` happy path:
  - `test_prompt_provider_turn_plan_keeps_rendered_transport_boundary`
  - Confirms the step still reaches transport as `RenderedProviderTurn` and keeps `outcome_json` response shaping.
- Produce/verify `ProviderTurnPlan` happy path:
  - `test_produce_verify_provider_turn_plan_keeps_rendered_transport_boundary`
  - Confirms producer/verifier still reach transport as `RenderedProviderTurn` values with the expected two-turn contract split.
- Known parity-gap fallback, prompt path:
  - `test_prompt_provider_turn_plan_falls_back_for_known_parity_gap`
  - Confirms the explicit allowlisted `ValueError` still falls back to the legacy compiled-step contract path without breaking execution.
- Known parity-gap fallback, produce/verify path:
  - `test_produce_verify_provider_turn_plan_falls_back_for_known_parity_gap`
  - Confirms the dual-turn produce/verify path also preserves the transport boundary when the same allowlisted fallback is triggered.
- Unexpected adapter failure path:
  - `test_prompt_provider_turn_plan_surfaces_unexpected_adapter_errors`
  - Confirms non-allowlisted adapter failures now surface instead of silently reverting to the legacy path.
- RouteDecision bridge, finish route:
  - `test_route_finalization_exposes_route_decision_for_finish_routes`
  - Confirms finalization exposes a typed decision with the expected route tag and finish action.
- RouteDecision bridge, await-input route:
  - `test_route_finalization_exposes_route_decision_for_await_input_routes`
  - Confirms pending input is materialized during finalization and reused by the exposed route decision.

## Preserved invariants checked

- Provider transports still receive `RenderedProviderTurn`.
- Provider transports still return `ProviderTurnResult`.
- Route finalization still exposes legacy behavior while adding `decision` as an additive field.

## Edge cases and failure paths

- Allowlisted parity-gap fallback is tested for both prompt and produce/verify paths.
- Unexpected adapter exceptions are tested through the shared adapter bridge.

## Flake risks and stabilization

- No network or timing dependency.
- Provider behavior is deterministic via scripted fake/rendered transports.
- Monkeypatch usage is scoped per test to avoid cross-test state leakage.

## Known gaps

- Operation execution remains intentionally out of scope for this phase.
- The unexpected-adapter-error assertion is exercised on the prompt path only because the surfaced exception behavior comes from the shared adapter bridge helper.
