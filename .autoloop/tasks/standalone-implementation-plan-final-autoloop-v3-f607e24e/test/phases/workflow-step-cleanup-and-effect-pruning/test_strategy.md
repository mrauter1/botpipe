# Test Strategy

- Task ID: standalone-implementation-plan-final-autoloop-v3-f607e24e
- Pair: test
- Phase ID: workflow-step-cleanup-and-effect-pruning
- Phase Directory Key: workflow-step-cleanup-and-effect-pruning
- Phase Title: Workflow-Step Cleanup And Effect Pruning
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 `workflow_step(...)` lowers to `core.steps.WorkflowStep`:
  Covered by `tests/unit/test_simple_surface.py::test_simple_workflow_step_compiles_as_core_workflow_step_without_generated_handler`.
  Preserved invariants: compiled kind is `workflow`, compiled `system_handler` is `None`, default terminal routes are unchanged.
- AC-2 simple workflows do not receive generated `on_<step>` handlers:
  Covered by `tests/unit/test_simple_surface.py::test_simple_workflow_step_compiles_as_core_workflow_step_without_generated_handler`.
  Edge case: `tests/contract/test_engine_contracts.py::test_workflow_step_rework_route_relaunches_child_workflow_and_preserves_hooks` reasserts no `on_launch` handler on a real engine execution path.
- AC-3 `BoardMutation` is removed from active public surfaces and active source:
  Covered by `tests/unit/test_validation.py::test_board_mutation_is_not_exported_from_public_modules`.
  Covered by `tests/unit/test_validation.py::test_board_mutation_is_not_defined_in_core_effects_module`.
  Covered by `tests/strictness/test_no_compat.py::test_active_tree_does_not_reintroduce_removed_compatibility_surfaces`.

## Failure paths / regression risks checked

- Reintroduction of generated workflow-step fallback helpers is caught by the strictness token scan for `_install_simple_workflow_step_handler`.
- Reintroduction of `BoardMutation` as either a module attribute or `__all__` export from `core.effects` is caught directly.
- Reintroduction of `BoardMutation` or generated workflow-step residue anywhere in maintained roots is caught by the strictness scan.

## Determinism / flake control

- Tests are pure import/compile/runtime assertions with no timing or network dependency.
- Strictness coverage uses maintained-root text scans with split-string token construction to avoid self-matching the forbidden terms.

## Known gaps

- Full touched-suite green status is still blocked by the pre-existing retry-aware validation failure in `tests/contract/test_engine_contracts.py::test_provider_invalid_question_retry_exhaustion_marks_failure_context`; that belongs to the earlier dependency phase, not this cleanup phase.
