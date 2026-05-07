# Test Strategy

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: test
- Phase ID: sdk-facade
- Phase Directory Key: sdk-facade
- Phase Title: Add SDK Facade
- Scope: phase-local producer artifact

## Behavior-to-coverage map
- SDK typed input + pause loop happy path:
  `tests/unit/test_sdk_facade.py::test_sdk_run_handles_typed_input_pause_loop_and_debug_artifacts`
  Covers result mapping, handled inputs, debug ids/files, artifact reads, and composite `ctx.input` / `ctx.input_fields`.
- Message-less SDK run:
  `tests/unit/test_sdk_facade.py::test_sdk_run_preserves_explicit_none_message`
  Covers explicit `client.run(Wf, None)`, `ctx.message is None`, `ctx.input.message is None`, and `{input.message}` artifact-path rendering to an empty segment.
- Typed input failure path:
  `tests/unit/test_sdk_facade.py::test_sdk_run_rejects_plain_dict_third_argument`
  Covers public SDK rejection of dict third positional input.
- Resume input validation failure:
  `tests/unit/test_sdk_facade.py::test_sdk_run_wraps_resume_schema_mismatch_as_input_response_validation_error`
  Covers handler-response schema rejection wrapping.
- Provider question defaults + explicit overrides:
  `tests/unit/test_sdk_facade.py::test_sdk_provider_questions_default_to_handler_presence`
  `tests/unit/test_sdk_facade.py::test_sdk_run_suppresses_provider_questions_without_handler_by_default`
  `tests/unit/test_sdk_facade.py::test_sdk_run_explicit_provider_questions_true_allows_handlerless_pause`
  `tests/unit/test_sdk_facade.py::test_sdk_run_explicit_provider_questions_false_suppresses_provider_questions_even_with_handler`
  `tests/unit/test_sdk_facade.py::test_sdk_run_keeps_direct_request_input_when_provider_questions_disabled`
  Covers default enable/disable policy, explicit override behavior, and the invariant that direct `RequestInput(...)` pauses still work when provider-visible questions are suppressed.
- Standalone operations + synthetic step execution:
  `tests/unit/test_sdk_facade.py::test_sdk_llm_and_classify_delegate_to_operation_path`
  `tests/unit/test_sdk_facade.py::test_sdk_step_executes_synthetic_simple_operation_workflow`
  `tests/unit/test_sdk_facade.py::test_sdk_step_supports_core_python_step_instances`
  Covers operation delegation, step synthesis, and typed-input propagation through a strict core step.
- Sync active-event-loop normalization:
  `tests/unit/test_sdk_facade.py::test_sdk_sync_entrypoints_normalize_active_event_loop_failures`
  Covers bridge-backed sync entrypoints `run` and `step`.
- Compile/runtime regression surfaces relied on by SDK behavior:
  `tests/unit/test_validation.py::test_validation_rejects_workflow_input_message_field`
  `tests/runtime/test_workspace_and_context.py::test_resume_context_preserves_run_message_and_raw_input_fields`
  `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_bare_input_message_and_fields`
  `tests/contract/test_engine_contracts.py::test_runtime_templates_reject_unknown_bare_input_field`
  `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_ctx_input_message_without_typed_input`
  `tests/contract/test_engine_contracts.py::test_runtime_templates_resolve_ctx_input_message_separately_from_request`
  `tests/unit/test_simple_surface.py::test_autoloop_root_exports_only_the_canonical_public_surface`
  Covers the compile-time `Workflow.Input.message` break, resume message/input stability, placeholder rendering, and root exports.

## Preserved invariants checked
- `message`, `workflow_input`, and `workflow_params` stay separate in runtime state and rendered context.
- Omitted runtime messages still resume from persisted request snapshots, while explicit SDK `None` remains `None`.
- Provider question suppression does not suppress direct Python `RequestInput(...)` pauses.
- SDK debug/task/run metadata remains available without opening public resume/lifecycle APIs.

## Edge cases and failure paths
- Dict third positional input rejected.
- Schema-invalid pause response wrapped as `InputResponseValidationError`.
- Handlerless provider question pause allowed only when explicitly/default enabled.
- Handler-present provider question path still suppressed when explicitly disabled.
- Active-event-loop SDK sync error expectation is limited to entrypoints that actually bridge async execution in the current runtime.

## Flake risks and stabilization
- Uses `ScriptedLLMProvider` and local temp state roots only; no network or clock-based assertions beyond prefix checks.
- Active-loop coverage uses `asyncio.run(...)` with immediate synchronous calls to avoid task-ordering nondeterminism.

## Known gaps
- Async SDK entrypoints remain deferred by product scope, so no async facade tests were added.
- `llm` / `classify` active-loop failures are not asserted because the current implementation executes those operation calls synchronously without the runtime bridge failure path.
- The corrected `ctx.input.message` contract tests currently fail against the implementation, which means runtime template resolution still does not honor the accepted composite-input contract in all `ctx.*` paths.
