# Implementation Notes

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: implement
- Phase ID: lazy-worklists-and-sessions
- Phase Directory Key: lazy-worklists-and-sessions
- Phase Title: Lazy Worklists And Sessions
- Scope: phase-local producer artifact

## Files changed

- `autoloop/core/context.py`
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `tests/contract/test_engine_contracts.py`
- `tests/unit/test_primitives_and_stores.py`

## Symbols touched

- `Context.ensure_selection`
- `_ContextRuntime.set_worklist_selection_resolver`
- `_ContextRuntime.emit_worklist_selection_resolved`
- `Engine._restore_worklist_selections`
- `Engine._ensure_worklist_selection`
- `Engine._worklist_source_type`
- `StateRuntime.ensure_worklist_selection`
- `StepDispatcher.execute`

## Checklist mapping

- Lazy fresh-start selections: completed via empty startup `selections` plus context-bound resolver.
- Sparse restore/checkpoint behavior: completed via restore-from-snapshots-only path; snapshotting remained sparse.
- Scoped-step first-use materialization: completed via pre-dispatch ensure and pre-item-state ensure in the main loop.
- Work-item continuity with lazy selections: completed via `Context.current(...)` lazy resolution and continuity error normalization.
- Regression coverage: added unit and contract coverage for deferred artifact-backed worklists, sparse resume, runtime resolution events, and work-item sessions.

## Assumptions

- Existing worklist source error messages are authoritative enough once wrapped with worklist name and source type.
- `worklist_selection_resolved` event payload does not need a separate engine-owned schema beyond step/worklist/current item metadata already available on context.

## Preserved invariants

- No eager worklist loading during compile, fresh start, resume bootstrap, or checkpoint save.
- Existing worklist mutation paths (`refresh`, status updates, advance) still own normal selection-change events and state sync.
- Explicitly materialized selections remain the only selections serialized into checkpoints.

## Intended behavior changes

- Missing worklist selections now materialize lazily through context/session/artifact access instead of raising immediately.
- Scoped steps resolve their scoped worklist before item-state derivation, artifact resolution, and session continuity.
- Work-item continuity failures now surface as `WorkflowExecutionError` with the continuity message instead of leaking `ValueError`.

## Known non-changes

- No typed worklist effects, validation-step helper, inspection payload redesign, or artifact-ownership diagnostics were implemented in this phase.
- No broad rewrite of worklist source validation messages beyond first-use context wrapping.

## Expected side effects

- First-use worklist resolution now emits `worklist_selection_resolved` when a runtime event sink is present.
- Non-scoped steps can use work-item continuity if the referenced worklist lazily materializes to a current item; empty selections still fail at runtime.

## Validation performed

- `python3 -m py_compile autoloop/core/context.py autoloop/core/engine.py autoloop/core/engine_collaborators.py tests/contract/test_engine_contracts.py tests/unit/test_primitives_and_stores.py`
- `./.venv/bin/python -m pytest tests/unit/test_primitives_and_stores.py -k 'lazy_materializes_missing_worklist or context_exposes_worklist_selection_helpers_and_item_placeholder_state or artifact_template_resolution_supports_worklist_placeholders'`
- `./.venv/bin/python -m pytest tests/unit/test_primitives_and_stores.py -k 'artifact_template_resolution_supports_worklist_placeholders or worklist_runtime_view_refresh_reloads_mutable_source or worklist_runtime_view_validate_reloads_mutable_source_and_reports_missing_selected_item or worklist_runtime_view_refresh_raises_when_mutable_source_drops_selected_item'`
- `./.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -k 'unused_artifact_backed_worklist_does_not_load_on_non_scoped_path or artifact_backed_worklist_materializes_after_runtime_creates_source or missing_artifact_backed_worklist_fails_at_first_scoped_use or resume_restores_materialized_worklists_and_lazily_materializes_unused_ones or work_item_session_resume_uses_dir_key_based_key_and_reuses_session or non_scoped_work_item_session_fails_when_no_current_item_exists or scoped_step_advances_worklist_items_and_uses_item_placeholders or scoped_item_state_and_step_item_state_resume_from_checkpoint'`
- `./.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -k 'selector_single_item_from_workflow_params_limits_scoped_execution or artifact_backed_worklist_duplicate_ids_fail_before_scoped_execution'`

## Deduplication / centralization

- First-use selection loading is centralized behind the engine-backed context resolver instead of being reimplemented separately in context, sessions, or artifact placeholder code.
