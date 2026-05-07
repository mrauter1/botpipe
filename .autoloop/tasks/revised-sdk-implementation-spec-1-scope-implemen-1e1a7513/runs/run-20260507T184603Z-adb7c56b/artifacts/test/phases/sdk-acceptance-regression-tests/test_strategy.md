# Test Strategy

- Task ID: revised-sdk-implementation-spec-1-scope-implemen-1e1a7513
- Pair: test
- Phase ID: sdk-acceptance-regression-tests
- Phase Directory Key: sdk-acceptance-regression-tests
- Phase Title: SDK Acceptance Regression Tests
- Scope: phase-local producer artifact

## Coverage map
- Public exports:
  `test_sdk_public_exports_include_revised_sdk_surface` verifies the new SDK step/result/retention exports remain importable from `autoloop`.
- Prompt rendering:
  `test_sdk_runtime_prompt_rendering_supports_input_and_ctx_message` covers `{input.message}`, `{ctx.message}`, and typed `{input.topic}` in the local SDK facade surface.
- Typed-input failure path:
  `test_sdk_prompt_step_missing_input_field_fails_clearly` locks the missing-field error for `{input.customer}` without typed input.
- Step helpers and compatibility:
  `test_sdk_helper_entrypoints_build_core_steps_and_delegate_to_client_step` covers helper construction and retention passthrough.
  `test_sdk_step_executes_synthetic_simple_operation_workflow` preserves `client.step(simple named declaration, ...)` compatibility.
- Routes:
  `test_default_routes_for_supported_core_steps`, `test_sdk_step_preserves_explicit_routes_for_core_steps`, `test_sdk_prompt_step_preserves_explicit_self_routes`, and `test_sdk_produce_verify_step_defaults_to_rework_self_loop` cover defaults plus explicit `SELF` preservation.
- Result artifacts:
  `test_sdk_run_exposes_result_artifact_metadata_and_helpers` and `test_result_artifact_read_model_rejects_missing_or_non_model_schema` cover retained `ResultArtifact` read helpers and schema failure paths.
- Retention and cleanup:
  Existing retention/cleanup tests cover success deletion, keep-all/ephemeral policy behavior, promoted write collision handling, too-many-pauses retention, cleanup dry-run behavior, age filtering, and safe deletion refusal cases.
- Runtime-equivalent declared-write context:
  `test_sdk_run_retention_collects_declared_writes_with_runtime_param_context` covers bare `params.*` and `workflow_params.*` artifact placeholders through the SDK retention path and asserts both retained and source basenames.

## Preserved invariants checked
- `StepResult.value` stays `None` even when the wrapped workflow result exposes `output`.
- Child workflow helper message forwarding still honors the outer message default and input placeholder rendering.
- Cleanup remains conservative and sentinel-gated.

## Edge cases and failure paths
- Missing typed input fields raise clear SDK errors.
- Unsafe cleanup candidates are rejected for missing/mismatched sentinel data or paths outside the SDK task root.
- Retention keeps scratch on pause/too-many-pauses paths and omits task-local writes in ephemeral mode.

## Flake control
- All assertions use local temp directories, scripted providers, and deterministic file contents.
- Cleanup age filtering relies on fixed sentinel `created_at` strings rather than filesystem mtimes.

## Known gaps
- This phase does not broaden coverage for unrelated runtime placeholder surfaces beyond the request-relevant SDK seam and the focused artifact-template subset re-run.
