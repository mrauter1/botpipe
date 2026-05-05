# Implementation Notes

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: implement
- Phase ID: stdlib-progress-worklists
- Phase Directory Key: stdlib-progress-worklists
- Phase Title: Add canonical progress JSON worklists
- Scope: phase-local producer artifact

## Files changed
- `autoloop/stdlib/worklists.py`
- `autoloop/stdlib/__init__.py`
- `tests/unit/test_stdlib_progress_worklists.py`
- `tests/runtime/test_progress_worklists.py`
- `tests/unit/test_worklist_selectors.py` for selector contract coverage tied to this helper surface
- `autoloop/core/worklists.py` as the already-landed selector/artifact dependency surface

## Symbols touched
- `WorkStatus`
- `WorkStatusPolicy`
- `SKIPPABLE_WORK_STATUS_POLICY`
- `ProgressItem`
- `ProgressBoard`
- `ProgressJsonCollectionSource`
- `progress_selector`
- `progress_artifact_worklist`
- `Worklist.artifact`

## Checklist mapping
- Plan milestone 2: canonical stdlib progress worklist helpers are present with fixed `items` / `id` / `title` / `status` shape, derived artifact naming, selector naming, fallback materialization, and status-policy validation.
- Plan milestone 3: focused selector/stdlib/runtime coverage passes, including the reviewer-raised duplicate-id fallback regression path.

## Assumptions
- The existing failures in `tests/unit/test_stdlib_and_extensions.py` and `tests/runtime/test_workspace_and_context.py` are not caused by the progress worklist implementation because they fail in portfolio/runtime workflow discovery code paths rather than the touched stdlib worklist surface.

## Preserved invariants
- Core selection remains generic and lives in `Worklist`; the stdlib source only loads and saves ordered canonical board items.
- The common-case source stays strict greenfield: no legacy board-shape aliases, no selector aliases, no automatic field detection, and no workflow-domain status vocabulary in core.
- Save behavior only mutates `status`, preserves item order, and preserves non-status payload fields.
- Fallback-backed writes now reject duplicate item ids before any artifact is created, so fallback materialization cannot persist an invalid canonical board.

## Intended behavior changes
- `progress_artifact_worklist(name, ...)` derives `{workflow_folder}/worklists/{name}.json`, `{name}_board`, and selector params `{name}`, `from_{name}`, `to_{name}`, `{name}_mode`.
- Default stdlib statuses are exactly `planned`, `in_progress`, `blocked`, `completed`, and `failed`; `skipped` is opt-in through `extra_statuses`.
- Missing artifacts can be materialized from fallback payloads/models and persisted as canonical pretty JSON with trailing newline.
- Duplicate item ids returned from fallback now fail immediately during fallback normalization instead of being written to disk and failing on a later load.

## Known non-changes
- Root `autoloop/__init__.py` remains untouched in this pass.
- No route-helper wrappers, provider/checkpoint/session internals, or legacy compatibility shims were added.
- Adjacent workflow catalog/runtime discovery failures from broader stdlib/workspace suites remain out of scope and were not patched in this phase-local turn.

## Expected side effects
- Validation used a local workspace `.venv/` with editable install plus `pytest`.

## Validation performed
- Passed: `.venv/bin/python -m pytest tests/unit/test_worklist_selectors.py tests/unit/test_stdlib_progress_worklists.py tests/runtime/test_progress_worklists.py`
- The focused suite now covers reviewer finding `IMP-001` by asserting duplicate-id fallbacks fail before any artifact write.

## Deduplication / centralization
- Ordered selection stays centralized in `autoloop/core/worklists.py`.
- Canonical JSON progress-board persistence stays centralized in `autoloop/stdlib/worklists.py` instead of adding route helpers or alternative board-shape adapters.
