# Test Strategy

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: test
- Phase ID: sdk-operations-and-verification
- Phase Directory Key: sdk-operations-and-verification
- Phase Title: Finish Operations And Verification
- Scope: phase-local producer artifact

## Behavior-to-coverage map
- `Autoloop.run(...)` message plus typed input:
  Covered by `test_sdk_run_handles_typed_input_pause_loop_and_debug_artifacts` and `test_sdk_run_preserves_explicit_none_message`.
- SDK typed-input guardrails:
  Covered by `test_sdk_run_rejects_plain_dict_third_argument`.
- Pause loop and response validation:
  Covered by `test_sdk_run_handles_typed_input_pause_loop_and_debug_artifacts`, `test_sdk_run_wraps_resume_schema_mismatch_as_input_response_validation_error`, and the direct `InputRequired` provider/direct-pause cases.
- Provider-question policy defaults and overrides:
  Covered by `test_sdk_provider_questions_default_to_handler_presence`, `test_sdk_run_suppresses_provider_questions_without_handler_by_default`, `test_sdk_run_explicit_provider_questions_true_allows_handlerless_pause`, `test_sdk_run_keeps_direct_request_input_when_provider_questions_disabled`, and `test_sdk_run_explicit_provider_questions_false_suppresses_provider_questions_even_with_handler`.
- Standalone SDK operations:
  Covered by `test_sdk_llm_and_classify_delegate_to_operation_path`.
- SDK params success and failure paths:
  Covered by `test_sdk_run_exposes_params_without_leaking_them_into_ctx_input` for both mapping and `Workflow.Params` instances, plus `test_sdk_run_wraps_invalid_params_at_the_sdk_boundary` for wrapper error translation.
- SDK result mapping:
  Covered by `test_sdk_run_handles_typed_input_pause_loop_and_debug_artifacts` for completed runs and `test_sdk_run_maps_failed_terminal_to_failed_result_status` for failed runs.
- Synthetic `Autoloop.step(...)` happy path and route synthesis:
  Covered by `test_sdk_step_executes_synthetic_simple_operation_workflow`, `test_sdk_step_supports_core_python_step_instances`, and `test_sdk_step_supports_core_python_steps_with_explicit_terminal_route_metadata`.
- Synthetic `Autoloop.step(...)` unsupported declarations:
  Covered by `test_sdk_step_rejects_branch_group_declarations`.
- Active-event-loop sync normalization:
  Covered by `test_sdk_sync_entrypoints_normalize_active_event_loop_failures`.
- Runtime child-workflow regression adjacent to SDK changes:
  Covered by `tests/runtime/test_workspace_and_context.py`.

## Preserved invariants checked
- `ctx.message` and `ctx.input.message` stay aligned without persisting message into typed input fields.
- `params` remain on `ctx.params` / `workflow_params` and do not appear on `ctx.input`.
- `FAIL` maps to `WorkflowResult(status="failed", ok=False)`.
- Standalone operation calls stay on the operation path instead of bypassing runtime helpers.
- Sync SDK `run`/`step` still reject active event loops with SDK-owned errors.

## Edge cases and failure paths
- Explicit `message=None`.
- Direct Python `RequestInput(...)` pauses when provider questions are disabled.
- Provider-visible question suppression without a handler and with an explicit override.
- Invalid resume answer schema wrapping.
- Invalid SDK params wrapping at the facade boundary.
- Unsupported branch-group step declarations.

## Stabilization / flake controls
- Uses `ScriptedLLMProvider` and Python-step handlers only; no network, clocks, or nondeterministic ordering assertions.
- Filesystem assertions stay within per-test `tmp_path` state roots.

## Known gaps
- Async SDK entrypoints remain out of scope for this phase.
- `llm` / `classify` active-loop behavior is intentionally not asserted because they do not use the runtime sync bridge in this implementation.
