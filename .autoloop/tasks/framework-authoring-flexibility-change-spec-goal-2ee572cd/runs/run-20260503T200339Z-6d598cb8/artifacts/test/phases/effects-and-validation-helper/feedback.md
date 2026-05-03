# Test Author ↔ Test Auditor Feedback

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: test
- Phase ID: effects-and-validation-helper
- Phase Directory Key: effects-and-validation-helper
- Phase Title: Effects And Validation Helper
- Scope: phase-local authoritative verifier artifact

## 2026-05-03 test producer

- Added `tests/unit/test_simple_surface.py::test_effect_helpers_and_additional_route_helpers_lower_to_effects` to cover `Effects.then`, `Route.refresh`, and `Route.complete_current` lowering through the typed `Effects` path.
- Confirmed existing contract coverage already exercises typed effect execution order, refresh/status/advance behavior, repairable validation feedback writes, pass/fail validation runtime events, and explicit failed-route exception handling.
- Focused validation run: `./.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py -k "effect_helpers_and_additional_route_helpers_lower_to_effects or effect_exports_and_route_helpers_are_public or validation_result_helpers_render_expected_shape"` -> `3 passed`.

## 2026-05-03 test auditor

- `TST-001` `blocking` `tests/unit/test_simple_surface.py::test_effect_helpers_and_additional_route_helpers_lower_to_effects`, `tests/contract/test_engine_contracts.py`: AC-4 requires direct hook/Python-step returns to support `Effects.then`, but the current suite only checks that `Effects.then("next")` constructs an object with `event == "next"`. There is no runtime test that a hook or Python step returning `Effects.then("next")` actually routes through shared normalization and reaches the expected transition. A regression in event-only effect handling would currently pass all phase tests because the covered runtime cases all include worklist mutations or use raw `Effects(..., event=...)`. Add one engine-level regression where a hook or Python step returns `Effects.then("next")` with no worklist effects and assert the resulting route/history.

## 2026-05-03 test producer follow-up

- Added `tests/contract/test_engine_contracts.py::test_python_step_effect_then_routes_without_worklist_mutation` to exercise `Effects.then("next")` through the engine’s shared effect-normalization path with no worklist mutations.
- Updated the strategy coverage map so AC-4 explicitly includes the event-only `Effects.then(...)` runtime path.
- Focused validation run: `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k "python_step_effect_then_routes_without_worklist_mutation or after_hook_effects_complete_and_advance_persist_status_and_exhaust or python_step_effect_refresh_reloads_worklist_source or effect_without_active_worklist_fails_clearly or validation_step_valid_routes_to_default_done_and_emits_runtime_event or validation_step_invalid_writes_feedback_and_routes_repair or validation_step_exception_uses_failed_route_when_configured"` -> `7 passed`.

## 2026-05-03 test auditor recheck

- `TST-001` resolved: `tests/contract/test_engine_contracts.py::test_python_step_effect_then_routes_without_worklist_mutation` now covers the event-only `Effects.then(...)` runtime path that was previously missing from AC-4 coverage.
- Recheck validation run: `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k "python_step_effect_then_routes_without_worklist_mutation or after_hook_effects_complete_and_advance_persist_status_and_exhaust or python_step_effect_refresh_reloads_worklist_source or effect_without_active_worklist_fails_clearly or validation_step_valid_routes_to_default_done_and_emits_runtime_event or validation_step_invalid_writes_feedback_and_routes_repair or validation_step_exception_uses_failed_route_when_configured"` -> `7 passed`.
