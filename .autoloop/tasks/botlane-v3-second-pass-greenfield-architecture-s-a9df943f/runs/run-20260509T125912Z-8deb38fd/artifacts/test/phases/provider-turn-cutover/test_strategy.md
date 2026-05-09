# Test Strategy

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: test
- Phase ID: provider-turn-cutover
- Phase Directory Key: provider-turn-cutover
- Phase Title: Provider Turn Cutover
- Scope: phase-local producer artifact
- Behaviors covered: provider-backed prompt steps compile to `PromptStepPlan` and pair steps compile to `ProduceVerifyStepPlan`
- Behaviors covered: prompt and pair execution still cross the rendered transport boundary as `RenderedProviderTurn -> ProviderTurnResult`
- Behaviors covered: prompt rendered-provider retries still succeed and reuse the pre-step session baseline across attempts
- Behaviors covered: pair rendered-provider execution still preserves producer raw output, verifier raw output, aggregated `StepProviderUsage`, and final persisted session binding
- Preserved invariants checked: `ProviderTurnKind` used by step plans excludes `"operation"`; route finalization still surfaces `route_decision` and canonical `action`
- Edge cases: rendered prompt retry after an illegal route; pair verifier receiving the producer-attempt session chain
- Failure paths: retry path on rendered prompt execution is exercised through an initial illegal route before success
- Stabilization: custom async transports return queued deterministic `ProviderTurnResult` values with no timing, network, filesystem race, or ordering dependency
- Validation run: `.venv/bin/python -m compileall tests/contract/test_provider_turn_plan.py`
- Validation run: `.venv/bin/pytest tests/contract/test_provider_turn_plan.py tests/contract/engine/test_core_contracts.py tests/contract/engine/test_sessions.py -q`
- Known gaps: this slice does not add operation-turn tests because operation migration remains explicitly out of scope for the phase
