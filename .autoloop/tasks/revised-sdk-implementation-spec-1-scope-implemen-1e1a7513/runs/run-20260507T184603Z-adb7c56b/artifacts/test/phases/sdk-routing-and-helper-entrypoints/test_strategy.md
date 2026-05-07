# Test Strategy

- Task ID: revised-sdk-implementation-spec-1-scope-implemen-1e1a7513
- Pair: test
- Phase ID: sdk-routing-and-helper-entrypoints
- Phase Directory Key: sdk-routing-and-helper-entrypoints
- Phase Title: SDK Routing And Helper Entrypoints
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- AC-1 prompt rendering:
  - `test_sdk_runtime_prompt_rendering_supports_input_and_ctx_message`
  - `test_sdk_prompt_step_missing_input_field_fails_clearly`
  - `test_sdk_workflow_step_renders_child_message_with_input_placeholders`
- AC-2 routing:
  - `test_default_routes_for_supported_core_steps`
  - `test_sdk_step_preserves_explicit_routes_for_core_steps`
  - `test_sdk_prompt_step_preserves_explicit_self_routes`
  - `test_sdk_produce_verify_step_defaults_to_rework_self_loop`
- AC-3 helper entrypoints and retention threading:
  - `test_sdk_helper_entrypoints_build_core_steps_and_delegate_to_client_step`
  - `test_sdk_python_step_helper_executes_and_honors_retention_override`
  - `test_sdk_workflow_step_defaults_child_message_to_outer_message`
  - existing retention/result tests still cover helper-returned `StepResult` surfaces through `client.step(...)`
- AC-4 preserved compatibility:
  - `test_sdk_step_executes_synthetic_simple_operation_workflow`
  - `test_sdk_step_supports_core_python_step_instances`
  - existing unresolved/scoped/branch-group rejection tests remain active

## Preserved invariants checked
- `client.step(simple named declaration, ...)` remains supported.
- `StepResult.value` remains `None`.
- Branch-group and worklist-scoped SDK step declarations are still rejected.
- Helper entrypoints stay thin wrappers over `client.step(...)`.

## Edge cases and failure paths
- Missing `input.*` placeholders without typed input fail with a clear SDK error.
- Explicit `SELF` routes are exercised at runtime rather than only via transition-table inspection.
- Produce/verify default rework loops are exercised across multiple provider turns.
- Child workflow placeholder rendering is observed through a workspace side effect so retention cleanup cannot hide regressions.

## Flake risks and stabilization
- All new coverage is deterministic: `ScriptedLLMProvider` drives provider behavior, there is no network access, and no timing-sensitive assertions are used.
- Child workflow message assertions write to a fixed workspace file instead of task scratch to avoid retention-policy coupling.

## Known gaps
- The focused suite does not rerun broader repository tests outside `tests/unit/test_sdk_facade.py`.
- Compatibility fallback from strict `route_metadata` is covered indirectly by existing SDK-step tests rather than by a dedicated helper-specific regression case.
