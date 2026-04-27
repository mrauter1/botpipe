# Test Strategy

- Task ID: standalone-implementation-plan-autoloop-v3-green-f94366a9
- Pair: test
- Phase ID: normalization-and-discovery
- Phase Directory Key: normalization-and-discovery
- Phase Title: Normalization and discovery
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Simple discovery before lowering:
  `tests/runtime/test_workflow_reference_resolution.py::test_simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection`
  checks path, module, and catalog-name resolution plus capability inspection route table.
- Inherited simple declarations:
  `tests/unit/test_simple_surface.py::test_inherited_simple_workflow_declarations_remain_discoverable_and_compilable`
  checks that inherited simple members lower into a compilable workflow definition.
- Reserved-route normalization:
  `tests/unit/test_validation.py::test_compilation_exposes_step_control_contracts`
  and existing simple-surface workflow-step assertions check `question` / `blocked` / `failed` availability and fallback summaries.
- `reads` semantics:
  `tests/unit/test_validation.py::test_validation_rejects_ambiguous_declared_read_reference`
  and `tests/unit/test_validation.py::test_validation_rejects_future_read_artifacts`
  check ambiguous declared reads fail while unknown workspace-path reads remain optional and compile.
- Direct `system_step(fn)` lowering contract:
  `tests/unit/test_simple_surface.py::test_simple_system_step_lowers_to_core_system_handler_without_on_step_method`,
  `tests/unit/test_simple_surface.py::test_simple_system_step_normalizes_supported_handler_signatures_and_return_shapes`,
  and `tests/unit/test_validation.py::test_validation_accepts_direct_system_step_handler_without_on_step_method`.
- Hook route-override validation:
  `tests/unit/test_validation.py::test_validation_rejects_statically_invalid_after_hook_route_override`
  and `tests/unit/test_validation.py::test_validation_rejects_conflicting_static_after_hook_result_override`
  cover unknown static route tags and conflicting `AfterHookResult(route=..., event=...)`.

## Preserved invariants checked

- Simple workflows compile without explicit legacy handler generation for direct system/workflow simple declarations.
- Reserved pause/fail routes remain mechanically available during compilation and inspection.
- Optional `reads` do not silently reinterpret ambiguous declared-artifact references as workspace paths.

## Edge cases and failure paths

- Inherited members discovered by loader/capability inspection must also lower successfully.
- Static after-hook analysis is pinned only for source-inspectable constant string / `Event` / `AfterHookResult` returns.
- Failure-path coverage explicitly checks ambiguous artifact names and conflicting route-vs-event declarations.

## Known gaps

- This phase does not expand to engine-time route override execution behavior or provider rendering.
- Broader runtime/reference suites still contain unrelated baseline failures outside this phase boundary, so coverage remains targeted and deterministic.
