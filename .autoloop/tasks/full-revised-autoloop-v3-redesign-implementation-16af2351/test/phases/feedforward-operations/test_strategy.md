# Test Strategy

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: test
- Phase ID: feedforward-operations
- Phase Directory Key: feedforward-operations
- Phase Title: Feedforward operations
- Scope: phase-local producer artifact

## Behavior-to-test map

- AC-1 standalone operations:
  - `tests/unit/test_simple_surface.py::test_standalone_llm_and_classify_use_operation_provider_path`
  - `tests/unit/test_simple_surface.py::test_standalone_operations_treat_plain_strings_as_inline_prompts_for_rendered_provider`
  - `tests/unit/test_simple_surface.py::test_standalone_operations_retry_on_parse_and_choice_failures`
  - `tests/unit/test_simple_surface.py::test_standalone_operations_replay_and_fail_loudly_on_fingerprint_mismatch`
- AC-2 step-declared value nodes:
  - `tests/unit/test_simple_surface.py::test_llm_and_classify_step_compile_as_value_nodes_without_control_routes`
- AC-3 replay and resume for workflow-bound value nodes:
  - `tests/contract/test_engine_contracts.py::test_llm_and_classify_step_replay_across_reruns`
  - `tests/contract/test_engine_contracts.py::test_operation_replay_fingerprint_mismatch_fails_loudly`
  - `tests/contract/test_engine_contracts.py::test_resume_restores_recorded_values_for_following_python_step`

## Preserved invariants checked

- Feedforward nodes stay value-producing and do not gain implicit classifier routing.
- Bare string prompts remain canonical inline prompts for both standalone calls and helper calls inside `python_step`.
- Replay drift fails loudly instead of silently recomputing or silently reusing stale values.

## Edge cases and failure paths

- Typed-value parse retry for standalone `llm(...)`.
- Invalid choice retry for standalone `classify(...)`.
- Standalone replay hit avoids a second provider call.
- Standalone replay mismatch raises `ProviderExecutionError` on fingerprint drift.

## Stabilization

- Standalone replay tests pass explicit `callsite=` values so replay keys do not depend on source line numbers or stack shape.
- Rendered-provider prompt assertions use in-memory transports only; no network, timing, or filesystem race assumptions beyond per-test temp directories.

## Known gaps

- Full pytest execution remains environment-blocked here because `pytest` and `pydantic` are not installed in this workspace.
