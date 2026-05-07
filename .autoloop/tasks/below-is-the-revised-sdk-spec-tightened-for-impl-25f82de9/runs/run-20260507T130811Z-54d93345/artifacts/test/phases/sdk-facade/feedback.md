# Test Author ↔ Test Auditor Feedback

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: test
- Phase ID: sdk-facade
- Phase Directory Key: sdk-facade
- Phase Title: Add SDK Facade
- Scope: phase-local authoritative verifier artifact

- Added tracked SDK facade coverage for explicit `provider_questions=True` / `False` overrides, keeping direct `RequestInput(...)` pauses distinct from provider-visible question suppression.
- Kept active-event-loop normalization coverage on bridge-backed sync SDK entrypoints (`run`, `step`) and documented why `llm` / `classify` are intentionally excluded in the current runtime.
- Re-ran the focused cross-module regression slice:
  `tests/unit/test_sdk_facade.py tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/runtime/test_workspace_and_context.py::test_resume_context_preserves_run_message_and_raw_input_fields tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_bare_input_message_and_fields tests/contract/test_engine_contracts.py::test_runtime_templates_reject_unknown_bare_input_field tests/contract/test_engine_contracts.py::test_runtime_templates_reject_undeclared_ctx_input_message_without_typed_input tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_declared_ctx_input_message_separately_from_request`
  Result: `217 passed`, `14 warnings`.
- Replaced the stale `ctx.input.message` contract expectations with:
  `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_ctx_input_message_without_typed_input`
  `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_ctx_input_message_separately_from_request`
- Re-ran the corrected focused cross-module regression slice:
  `tests/unit/test_sdk_facade.py tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/runtime/test_workspace_and_context.py::test_resume_context_preserves_run_message_and_raw_input_fields tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_bare_input_message_and_fields tests/contract/test_engine_contracts.py::test_runtime_templates_reject_unknown_bare_input_field tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_ctx_input_message_without_typed_input tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_ctx_input_message_separately_from_request`
  Result: `215 passed`, `2 failed`, `14 warnings`.
- The two failures are intentional audit surfacing: they show the implementation still resolves `ctx.input` through raw input fields in runtime template paths instead of the accepted composite input view.

- `TST-001` `blocking` `[tests/contract/test_engine_contracts.py::test_runtime_templates_reject_undeclared_ctx_input_message_without_typed_input, tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_declared_ctx_input_message_separately_from_request, artifacts/test/phases/sdk-facade/test_strategy.md]` The tracked contract coverage still encodes stale pre-spec behavior for `ctx.input.message`. The first test asserts that `ctx.input.message` should fail when no typed input exists, even though the accepted contract and run-local decisions require `ctx.input.message` to always reflect the runtime message. The second test still models `PromptInput.message`, which mirrors the now-rejected `Workflow.Input.message` pattern and normalizes exactly the behavior the spec forbids. Because the strategy artifact cites both tests as supporting SDK behavior, the current test set would silently bless a regression back to the wrong runtime-input contract. Minimal correction: replace those contract expectations with assertions that `ctx.input.message` resolves from runtime message regardless of typed input presence, and stop using typed input models that declare `message` in this phase’s regression surface.
