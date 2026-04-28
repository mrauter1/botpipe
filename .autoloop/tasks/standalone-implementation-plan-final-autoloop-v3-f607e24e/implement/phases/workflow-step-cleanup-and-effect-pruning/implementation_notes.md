# Implementation Notes

- Task ID: standalone-implementation-plan-final-autoloop-v3-f607e24e
- Pair: implement
- Phase ID: workflow-step-cleanup-and-effect-pruning
- Phase Directory Key: workflow-step-cleanup-and-effect-pruning
- Phase Title: Workflow-Step Cleanup And Effect Pruning
- Scope: phase-local producer artifact

## Files changed

- `core/effects.py`
- `core/__init__.py`
- `core/engine.py`
- `core/validation.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`
- `tests/strictness/test_no_compat.py`

## Symbols touched

- Removed `BoardMutation`
- Removed `core.validation` dead helpers:
  `_simple_artifact_reference_lookup`
  `_install_simple_workflow_step_handler`
  `_resolve_simple_message_artifact`
  `_simple_workflow_step_message`
  `_write_simple_workflow_step_outputs`
  `_simple_workflow_step_output_payload`
  `_simple_workflow_step_output_summary`
  `_map_simple_workflow_child_result`
- Updated `_execute_route_effect(...)` and `_validate_route_effects(...)`

## Checklist mapping

- Step 2.1: deleted obsolete generated workflow-step helper code and cleaned unused imports.
- Step 2.3: preserved `workflow_step(...)` lowering to `WorkflowStep`; added contract regression assertions for compiled kind, no generated handler, and no compiled `system_handler`.
- Step 3.1-3.3: deleted `BoardMutation` from active effect types, engine handling, validation handling, and `core` exports.
- Step 3.4: replaced the old unsupported-BoardMutation validation test with public-surface absence assertions and strictness scan coverage.

## Assumptions

- This phase stays scoped to workflow-step cleanup and effect pruning; no `contracts_path`, stdlib rename, or docs wording changes were included.
- Unsupported route effects may now surface the generic `unsupported route effect` validation/execution errors instead of the previous dedicated BoardMutation message because the type no longer exists.

## Preserved invariants

- `workflow_step(...)` still compiles to a real `WorkflowStep` and Engine still executes workflow steps directly.
- Workflow classes do not receive generated `on_<step>` handlers for simple workflow steps.
- Public `autoloop` and `core` surfaces do not export a placeholder effect for unimplemented board mutations.

## Intended behavior changes

- `BoardMutation` is no longer importable from `core` exports because the effect type has been removed.
- Active strictness coverage now fails if `BoardMutation` or `_install_simple_workflow_step_handler` reappear in maintained roots.

## Known non-changes

- No out-of-phase retry-aware validation logic was changed in this pass.
- No docs required edits for `BoardMutation`; active docs had no references.

## Expected side effects

- Any stale caller attempting to use `BoardMutation` will now fail at import time rather than at workflow validation/execution time.
- Generated workflow-step fallback code can no longer drift independently from the real Engine workflow-step execution path because the duplicate implementation is gone.

## Validation performed

- `rg` over maintained roots confirmed removal of `BoardMutation` and the deleted workflow-step helper symbols from active source.
- `.venv/bin/python -m pytest tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py -k "workflow_step or board_mutation"` passed.
- `.venv/bin/python -m pytest tests/strictness/test_no_compat.py` passed.
- Broader pass `.venv/bin/python -m pytest tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py tests/strictness/test_no_compat.py` failed on an existing retry-aware validation assertion in `tests/contract/test_engine_contracts.py::test_provider_invalid_question_retry_exhaustion_marks_failure_context` expecting `failure_context["provider_attributable"]`; left untouched because it belongs to the prior phase.

## Deduplication / centralization

- Kept workflow-step runtime behavior centralized in `core/engine.py`; deleted the stale generated-handler duplicate logic from `core/validation.py`.
