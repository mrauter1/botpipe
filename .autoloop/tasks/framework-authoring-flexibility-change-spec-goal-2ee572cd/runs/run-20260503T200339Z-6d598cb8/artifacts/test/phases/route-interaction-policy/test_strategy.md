# Test Strategy

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: test
- Phase ID: route-interaction-policy
- Phase Directory Key: route-interaction-policy
- Phase Title: Route Policy Rebase
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Interactive provider defaults expose `question`, while full-auto hides it:
  - Covered by `tests/contract/test_engine_contracts.py::test_llm_requests_include_step_control_contracts`
  - Covered by `tests/contract/test_engine_contracts.py::test_full_auto_hides_default_question_route_from_provider_contract`
  - Covered by `tests/runtime/test_workspace_and_context.py::test_runner_full_auto_hides_default_question_route_from_provider_contract`
- Explicit authored `blocked` and `failed` remain legal and provider-visible:
  - Covered by `tests/contract/test_engine_contracts.py::test_llm_requests_include_step_control_contracts`
  - Covered by `tests/contract/test_engine_contracts.py::test_pair_requests_include_step_control_contracts`
  - Covered by `tests/contract/test_engine_contracts.py::test_explicit_blocked_and_failed_routes_do_not_require_reason_field`
- Only `question` keeps reserved payload validation:
  - Covered by `tests/contract/test_engine_contracts.py::test_question_route_requires_question_field`
  - Covered by `tests/contract/test_engine_contracts.py::test_provider_question_route_is_illegal_in_full_auto_mode`
  - Covered by `tests/unit/test_provider_retries.py` retry-feedback assertions for `question`-only guidance
- Core and simple authoring surfaces share the `ControlRoutes` contract:
  - Covered by `tests/unit/test_validation.py::test_core_control_routes_compile_provider_visibility_and_non_provider_defaults`
  - Covered by `tests/unit/test_simple_surface.py::test_simple_workflow_respects_control_routes_false_and_custom_semantic_routes`
- Python and child-workflow steps no longer receive default injected control routes:
  - Covered by `tests/unit/test_validation.py::test_core_control_routes_compile_provider_visibility_and_non_provider_defaults`
  - Covered by `tests/unit/test_simple_surface.py::test_simple_workflow_respects_control_routes_false_and_custom_semantic_routes`
- Provider prompt/retry contract no longer teaches special `blocked`/`failed` semantics:
  - Covered by `tests/unit/test_provider_boundary_core.py::test_render_provider_turn_renders_markdown_contract_without_raw_output`
  - Covered by `tests/unit/test_provider_retries.py` assertions that `blocked`/`failed` reason instructions are absent

## Preserved invariants checked

- `CompiledStep.available_routes` remains the execution-legal route set even when provider-visible routes differ by policy.
- Explicit authored global `failed` stays visible to provider-facing steps.
- `control_routes=False` still suppresses injected `question` for both simple and core declarations.

## Edge cases and failure paths

- Full-auto provider output selecting `question` gets retry feedback instead of being accepted.
- `question` without a non-empty `question` field is rejected.
- Hidden provider routes stay out of rendered provider contracts.

## Flake risk and stabilization

- Added coverage is deterministic and filesystem-local only.
- No network, clock, or ordering-sensitive assertions were introduced.

## Known gaps

- Executable `pytest` coverage could not be run in this shell because `pytest` and runtime dependency `pydantic` are unavailable here.
