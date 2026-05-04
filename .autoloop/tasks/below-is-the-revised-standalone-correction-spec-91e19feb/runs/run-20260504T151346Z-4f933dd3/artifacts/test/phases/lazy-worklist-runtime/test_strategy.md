# Test Strategy

- Task ID: below-is-the-revised-standalone-correction-spec-91e19feb
- Pair: test
- Phase ID: lazy-worklist-runtime
- Phase Directory Key: lazy-worklist-runtime
- Phase Title: Lazy Worklist Runtime
- Scope: phase-local producer artifact

## Coverage map

- AC-1 lazy compile / unused worklists:
  `tests/contract/test_engine_contracts.py::test_missing_artifact_backed_worklist_fails_at_first_scoped_use`
  `tests/contract/test_engine_contracts.py::test_resume_ignores_legacy_null_worklist_selection_payloads`
- AC-2 first-use materialization only for requested worklist:
  `tests/contract/test_engine_contracts.py::test_non_scoped_explicit_worklist_access_emits_resolution_event_for_only_requested_worklist`
  `tests/contract/test_engine_contracts.py::test_non_scoped_current_access_emits_resolution_event_for_only_requested_worklist`
  `tests/unit/test_primitives_and_stores.py::test_artifact_template_resolution_supports_item_state_placeholders`
  `tests/contract/test_engine_contracts.py::test_prompt_runtime_renders_item_state_placeholders`
- AC-3 strict lazy restore and resume edge cases:
  `tests/contract/test_engine_contracts.py::test_scoped_item_state_and_step_item_state_resume_from_checkpoint`
  `tests/contract/test_engine_contracts.py::test_work_item_session_resume_uses_dir_key_based_key_and_reuses_session`
  `tests/contract/test_engine_contracts.py::test_resume_ignores_legacy_null_worklist_selection_payloads`
- AC-4 lazy work-item session continuity:
  `tests/contract/test_engine_contracts.py::test_work_item_session_resume_uses_dir_key_based_key_and_reuses_session`
  `tests/contract/test_engine_contracts.py::test_non_scoped_work_item_session_fails_when_no_current_item_exists`
- AC-5 declared vs materialized inspection/static graph state:
  `tests/runtime/test_runtime_static_graph.py::test_worklist_item_state_surfaces_and_runtime_hook_locations_are_reported`
- AC-6 centralized artifact-backed missing-source policy:
  `tests/contract/test_engine_contracts.py::test_artifact_backed_worklist_scaffold_policy_creates_source_at_first_scoped_use`
  `tests/contract/test_engine_contracts.py::test_worklist_source_ensure_can_scaffold_backing_data_at_first_use`

## Preserved invariants checked

- Late-bound `item.state.<field>` placeholders compile and render only with active scoped context.
- Non-scoped worklist access materializes only the named worklist, not sibling declarations.
- Legacy/null checkpoint selection payloads do not force eager source loading on resume.

## Edge cases and failure paths

- Missing artifact-backed source still fails on first scoped use, not at compile/resume entry.
- Work-item session continuity still fails clearly when no current item exists.
- Legacy persisted `worklist_selections` entries with `null` values are ignored and resume with an empty lazy selection map.

## Validation run

- `./.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -q`

## Known gaps

- No additional static-graph artifact file assertions were added in this turn because the existing runtime static-graph tests already cover declared `materialization_state`, `source_descriptor`, and `missing_policy`.
