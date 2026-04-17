# Test Strategy

- Task ID: you-are-a-principal-software-architect-and-imple-5867bc5e
- Pair: test
- Phase ID: decision-freeze-and-observer-core
- Phase Directory Key: decision-freeze-and-observer-core
- Phase Title: Freeze Book Architecture And Add Observer Core
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- AC-1 architectural record shape
  - Coverage: `autoloop_v3/tests/test_architecture_baseline_docs.py`
  - Checks: 17 decision sections, 3 candidates per section, required decision rationale markers
- AC-2 observer seam happy path
  - Coverage: `test_execution_observers_receive_provider_step_and_success_terminal_events`
  - Checks: zero-or-more observer support, provider-turn events for producer/verifier/llm, step-completion emission, success terminal emission, no Autoloop-specific engine leakage
- AC-2 observer seam edge and failure paths
  - Coverage: `test_execution_observers_receive_pause_fail_and_fatal_terminal_events`
  - Checks: pause/fail/fatal terminal events, checkpoint presence on pause/fail/fatal, fatal exception metadata
- AC-2 observer non-interference
  - Coverage: `test_observers_do_not_alter_execution_semantics`
  - Checks: copied state/outcome/session payloads, swallowed observer exceptions, no mutation of engine result or stored session metadata
- AC-3 preserved strict engine invariants
  - Coverage: `test_pair_and_llm_handlers_remain_optional`, `test_missing_session_binding_fails_instead_of_auto_opening`, `test_on_start_opens_sessions_before_execution`, `autoloop_v3/tests/unit/test_validation.py`
  - Checks: Pair/LLM optional handlers, SystemStep required handlers, explicit session opening, missing-session failure, strict validation boundaries

## Edge Cases And Failure Paths

- Pause flow with middleware-generated question and checkpoint persistence
- Fail flow with terminal `FAIL` routing and observer emission
- Fatal flow with handler exception, checkpoint save, and terminal exception metadata
- Observer mutation attempts against state, outcome payloads, and session metadata

## Stabilization / Flake Control

- Use `ScriptedLLMProvider` for deterministic provider turns
- Use in-memory session and checkpoint stores to avoid filesystem timing variance
- Use per-test temporary task/run workspaces
- No network, clock, or nondeterministic ordering dependencies

## Known Gaps

- No parity harness rewiring coverage in this phase; out of scope
- No store-helper migration coverage in this phase; out of scope
- No repo-root workflow cleanup coverage in this phase; out of scope
