# Implementation Notes

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: implement
- Phase ID: effects-and-validation-helper
- Phase Directory Key: effects-and-validation-helper
- Phase Title: Effects And Validation Helper
- Scope: phase-local producer artifact

## Files Changed

- `autoloop/core/effects.py`
- `autoloop/core/validation_helpers.py`
- `autoloop/core/routes.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/context.py`
- `autoloop/core/discovery.py`
- `autoloop/core/__init__.py`
- `autoloop/simple.py`
- `autoloop/__init__.py`
- `tests/unit/test_simple_surface.py`
- `tests/contract/test_engine_contracts.py`

## Symbols Touched

- `WorklistEffect`
- `Effects`
- `Route.advance`
- `Route.refresh`
- `Route.complete_current`
- `HookRunner.normalize_result`
- `HookRunner._apply_effects`
- `_ContextRuntime.emit_runtime_event`
- `ValidationResult`
- `validation_step`
- `_lower_simple_declared_routes`

## Checklist Mapping

- Phase AC-1: implemented typed worklist effects, direct hook/Python-step returns, deterministic refresh/status/advance ordering, and route-helper lowering through `Effects`.
- Phase AC-2: implemented `ValidationResult` plus `validation_step`, deterministic feedback artifact writing, repair routing, and runtime events.
- Phase AC-3: validation helper exceptions now route through an authored `"failed"` route when configured; otherwise the original exception still raises.
- Phase AC-4: exported `Effects.then`, `Effects.advance`, `Effects.complete_and_advance`, `Effects.refresh`, and additive `Route.*` helper constructors.

## Assumptions

- `validation_step` remains a simple-surface authoring helper; external/simple transition ownership still decides success and repair destinations.
- Validation success should emit a runtime event even when no feedback artifact is written; the payload uses `feedback_artifact=None`.

## Preserved Invariants

- Worklist mutations still flow through existing `WorklistRuntimeView` APIs, so runtime events, cache updates, and checkpoint behavior stay on the existing state path.
- `Route.to(..., effects=...)` remains unsupported.
- Route-hook validation still expects callables; helper routes use generated `on_taken` callables rather than storing raw effect objects on routes.

## Intended Behavior Changes

- Hooks and Python steps may now return `Effects` directly.
- Common worklist progression can be authored with `Route.advance(...)`, `Route.refresh(...)`, and `Route.complete_current(...)`.
- `validation_step` provides deterministic repair-loop feedback writing and standardized pass/fail-repair runtime events.

## Known Non-Changes

- No broad flow DSL or new step kind was added.
- No prompt-placeholder relaxation or artifact-ownership diagnostics were implemented in this phase.
- `validation_step` does not infer repair destinations; callers still supply explicit route wiring where needed.

## Expected Side Effects

- Simple-surface root exports now include `Effects`, `WorklistEffect`, `ValidationResult`, and `validation_step`.
- Simple discovery now merges declaration-local `implicit_routes`, used here only to attach helper-owned `"failed"` transitions without disabling default `"done"` routing.

## Validation Performed

- `python3 -m py_compile autoloop/core/effects.py autoloop/core/validation_helpers.py autoloop/core/routes.py autoloop/core/engine_collaborators.py autoloop/core/context.py autoloop/core/discovery.py autoloop/core/__init__.py autoloop/simple.py autoloop/__init__.py`
- `./.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py -k "autoloop_root_exports_only_the_canonical_public_surface or effect_exports_and_route_helpers_are_public or validation_result_helpers_render_expected_shape"`
- `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k "effects_complete_and_advance_persist_status_and_exhaust or effect_refresh_reloads_worklist_source or effect_without_active_worklist_fails_clearly or validation_step_valid_routes_to_default_done_and_emits_runtime_event or validation_step_invalid_writes_feedback_and_routes_repair or validation_step_exception_uses_failed_route_when_configured"`
- `./.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py`
- `./.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py -k "worklist or selection"`
- `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k "scoped_step_advances_worklist_items_and_uses_item_placeholders or on_taken_goto_handoff_reaches_target_provider_step or on_taken_fail_preserves_mutated_state_and_emits_runtime_control or after_hook_re_resolves_artifact_paths_before_on_taken or route_handoff_is_scoped_to_the_active_worklist_item"`

## Deduplication / Centralization Decisions

- Centralized runtime effect execution inside `HookRunner.normalize_result(...)` so before/after/on_taken hooks and Python-step handlers share one effect path.
- Reused `_ContextRuntime` for helper runtime events instead of adding engine-only helper plumbing to simple-step wrappers.
