# Implementation Notes

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: implement
- Phase ID: core-selector-semantics
- Phase Directory Key: core-selector-semantics
- Phase Title: Extend generic worklist selectors
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/core/worklists.py`
- `autoloop/stdlib/__init__.py`
- `autoloop/stdlib/worklists.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_worklist_selectors.py`
- `tests/unit/test_stdlib_progress_worklists.py`
- `tests/runtime/test_progress_worklists.py`
- `decisions.txt`

## Symbols Touched
- Core: `Selector`, `Worklist.artifact`, `Worklist._selection_from_loaded_items`, `Worklist._resolve_selection`, `_selector_mode`, `_selector_param`, `_item_indexes`, `_require_item_id`
- Stdlib: `WorkStatus`, `WorkStatusPolicy`, `SKIPPABLE_WORK_STATUS_POLICY`, `ProgressItem`, `ProgressBoard`, `ProgressJsonCollectionSource`, `progress_selector`, `progress_artifact_worklist`
- Tests: selector semantics, stdlib progress source/policy coverage, runtime progress worklist coverage, existing mutable-source selector expectation

## Checklist Mapping
- Plan milestone 1: completed via canonical `all` / `single` / `up_to` / `from_to` selection in core with explicit validation and contextual execution errors.
- Plan milestone 2: completed via canonical stdlib progress worklist helper, fixed `items/id/title/status` contract, fallback materialization, default status policy, and `Worklist.artifact`.
- Plan milestone 3: completed for focused selector/progress/runtime coverage plus targeted existing contract regression checks; broader adjacent suites were run but remain blocked by unrelated catalog/root-resolution failures.

## Assumptions
- Selector-bound workflow params are string-valued; non-string selector params now fail clearly instead of being coerced.
- The canonical stdlib helper owns only `items/id/title/status`; any noncanonical board shape still belongs in custom sources.

## Preserved Invariants
- Source objects still own ordered item materialization and persistence only; selection remains in `Worklist`.
- Core `WorkItem.status` stays `str | None`.
- Existing artifact-backed generic worklists (`Worklist.from_artifact`) remain available and unchanged apart from post-load selector semantics.

## Intended Behavior Changes
- `mode=all` now rejects selector-bound item/start/end params by design.
- Generic worklists now support inclusive `up_to` and `from_to` selection in addition to `all` and `single`.
- Artifact-backed generated progress worklists expose `.artifact` directly from the returned `Worklist`.

## Known Non-Changes
- No root `autoloop/__init__.py` edits.
- No provider, checkpoint, session, route-internal, or loader/catalog changes were made.
- No selector aliases, board-shape aliases, or migration shims were added.

## Expected Side Effects
- Existing callers/tests that relied on subset selection under default `all` must switch to explicit `single` / `up_to` / `from_to`.
- Progress fallback materialization now writes canonical pretty JSON with normalized statuses when `write_fallback=True`.

## Validation Performed
- Passed: `'.venv_phase/bin/python -m pytest tests/unit/test_worklist_selectors.py tests/unit/test_stdlib_progress_worklists.py tests/runtime/test_progress_worklists.py'`
- Passed: `'.venv_phase/bin/python -m pytest tests/contract/test_engine_contracts.py -k "selector_single_item_from_workflow_params_limits_scoped_execution or after_hook_effects_complete_and_advance_persist_status_and_exhaust or missing_artifact_backed_worklist_fails_at_first_scoped_use or artifact_backed_worklist_materializes_after_runtime_creates_source"'`
- Passed: `'.venv_phase/bin/python - <<...>>'` direct source/runtime repro snippets for skipped-status policy behavior
- Failed outside phase scope: `'.venv_phase/bin/python -m pytest tests/unit/test_stdlib_and_extensions.py tests/unit/test_primitives_and_stores.py tests/runtime/test_workspace_and_context.py'` due unrelated workflow catalog/root-resolution failures in stdlib/workspace helper paths

## Dedup / Centralization
- Selection semantics were centralized in core helper flow after source validation rather than duplicated per source.
- Canonical progress-board load/ensure/save validation lives in `ProgressJsonCollectionSource` so workflow code only opts into the common-case helper.
