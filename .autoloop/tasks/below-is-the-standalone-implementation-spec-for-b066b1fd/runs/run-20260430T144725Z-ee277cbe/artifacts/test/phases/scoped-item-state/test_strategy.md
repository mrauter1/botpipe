# Test Strategy

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: test
- Phase ID: scoped-item-state
- Phase Directory Key: scoped-item-state
- Phase Title: Implement Scoped Item State
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 worklist item state persists independently per item:
  Covered by `tests/contract/test_engine_contracts.py::test_scoped_item_state_and_step_item_state_resume_from_checkpoint`, which mutates item state on multiple worklist items, checkpoints on failure, and verifies restored per-item payloads on resume.
- AC-1 scoped step-item state persists independently per item:
  Covered by `tests/contract/test_engine_contracts.py::test_scoped_item_state_and_step_item_state_resume_from_checkpoint`, which asserts isolated per-item `step_item_state` payloads and restored visit/custom-field values after resume.
- AC-1 repaired simple authoring path persists scoped state at runtime:
  Covered by `tests/unit/test_simple_surface.py::test_simple_scoped_item_state_and_step_item_state_restore_on_resume`, which runs a simple `step(..., scope=..., item_state=...)` workflow through pause/resume and asserts restored `ctx.item_state` plus `ctx.step_item_state` built-ins/custom fields.
- AC-2 `{item.state.*}` prompt references resolve only against declared worklist item-state fields:
  Covered by `tests/unit/test_simple_surface.py::test_simple_workflow_accepts_scoped_item_state_prompt_placeholders` and `::test_simple_workflow_rejects_unknown_scoped_item_state_prompt_fields`.
- AC-2 `{step_name.item_state.*}` prompt references resolve only against declared scoped step-item-state fields:
  Covered by `tests/unit/test_simple_surface.py::test_simple_workflow_accepts_scoped_step_item_state_prompt_placeholders`, `::test_simple_workflow_rejects_unknown_scoped_step_item_state_prompt_fields`, and `::test_simple_produce_verify_workflow_step_item_state_includes_producer_verifier_builtins`.

## Preserved invariants checked

- Unscoped simple steps still reject `item_state=...` authoring:
  Covered by `tests/unit/test_simple_surface.py::test_simple_workflow_rejects_item_state_without_scope`.
- Unscoped simple producer/verifier steps still reject `item_state=...` authoring:
  Covered by `tests/unit/test_simple_surface.py::test_simple_produce_verify_workflow_rejects_item_state_without_scope`.
- Generic prompt-style simple steps keep only generic step-item built-ins, while `produce_verify_step(...)` keeps `rework_count` / `replan_count`:
  Covered by `tests/unit/test_simple_surface.py::test_simple_workflow_accepts_scoped_step_item_state_prompt_placeholders` and `::test_simple_produce_verify_workflow_step_item_state_includes_producer_verifier_builtins`.

## Edge cases and failure paths

- Unknown worklist item-state prompt field fails validation deterministically at compile time.
- Unknown scoped step-item-state prompt field fails validation deterministically at compile time.
- Unscoped `item_state=...` authoring fails deterministically at compile time for both prompt-style and producer/verifier simple steps.
- Resume path covers built-in `visits` / `last_route` restoration before the next simple-step `after` hook mutates state again.

## Known gaps

- Full `pytest` execution was not run in this shell because `pytest` and runtime dependencies such as `pydantic` are unavailable here; validation was limited to `py_compile`.
- No additional filesystem-backed or multi-worklist simple-surface runtime scenarios were added because the existing contract test already covers cross-item persistence and namespaced checkpoint keys on the core runtime path.
