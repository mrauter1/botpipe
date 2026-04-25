# Test Strategy

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: test
- Phase ID: worklists
- Phase Directory Key: worklists
- Phase Title: Worklists And Scoped Steps
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Scoped happy path:
  `tests/contract/test_engine_contracts.py::test_scoped_step_advances_worklist_items_and_uses_item_placeholders`
  pins scoped item resolution, artifact placeholders, explicit `Advance(...)` looping, and work-item session continuity rotation.
- Explicit item selection:
  `tests/contract/test_engine_contracts.py::test_selector_single_item_from_workflow_params_limits_scoped_execution`
  pins selector-driven single-item execution without hidden iteration across the remaining worklist.
- Deterministic item identity:
  `tests/unit/test_primitives_and_stores.py::test_worklist_load_items_rejects_duplicate_ids`
  pins duplicate-id rejection on static worklists at the centralized `load_items(...)` path.
- Artifact-backed duplicate identity failure:
  `tests/contract/test_engine_contracts.py::test_artifact_backed_worklist_duplicate_ids_fail_before_scoped_execution`
  pins the same duplicate-id rejection for artifact-backed worklists before scoped execution begins.
- Advance validation failure paths:
  `tests/unit/test_validation.py::test_validation_rejects_advance_from_unscoped_step`
  `tests/unit/test_validation.py::test_validation_rejects_advance_for_mismatched_scoped_step_worklist`
  `tests/unit/test_validation.py::test_validation_rejects_advance_from_global_transition`
  pin that `Advance(...)` is valid only from the source step's matching worklist scope and never from `GLOBAL`.
- Existing effect validation invariant:
  `tests/unit/test_validation.py::test_invalid_effect_worklist_reference_rejected`
  continues to pin unknown-worklist rejection for worklist-bound effects.

## Preserved Invariants Checked

- Scoped `Advance(...)` still re-enters the same step while items remain.
- Worklist progression remains explicit; no full-worklist loop happens without `Advance(...)`.
- `item` and `worklist.*` placeholders remain deterministic when a current item exists.

## Edge Cases And Failure Paths

- Duplicate work item ids on both static and artifact-backed sources.
- `Advance(...)` from unscoped, mismatched-scoped, and `GLOBAL` transitions.
- Selector-limited execution over a scoped worklist.

## Flake Risk / Stabilization

- Tests are in-memory or tmp-path based only; no network, time, or ordering dependencies were introduced.
- Artifact-backed fixtures write fixed JSON payloads and use `ScriptedLLMProvider` for deterministic engine behavior.

## Known Gaps

- The runtime `_advance_worklist(...)` guard for invalid persisted/programmatically assembled routes is not exercised independently from compile-time validation; current coverage relies on the compile-time branch plus the shared engine contract tests.
