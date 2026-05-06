# Test Author ↔ Test Auditor Feedback

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: test
- Phase ID: provider-contract-cutover
- Phase Directory Key: provider-contract-cutover
- Phase Title: Provider contract cutover
- Scope: phase-local authoritative verifier artifact

- Added contract coverage for the clarified failure path where a rendered provider without `operation_executor=...` is used by `llm()` / `classify()` inside a synchronous Python step under the async engine; the test asserts the explicit runtime error and that no transport turn is executed.
- Recorded the behavior-to-test map for async-only provider/transport contracts, explicit helper compatibility, the narrowed active-loop sync exception, backend-builder isolation, and async subprocess transport stubs in `test_strategy.md`.

- TST-001 `non-blocking` — audit complete with no blocking coverage gaps. The added contract test closes the active-loop failure-path hole for rendered providers without `operation_executor=...`, the existing unit test preserves the outside-loop async-transport preference, and the strategy artifact now maps the clarified compatibility exception plus async subprocess transport coverage explicitly. The documented environment gap is execution-only (`pytest` unavailable here), not a test design flaw in the phase artifacts.
