# Implementation Notes

- Task ID: this-prompt-is-grounded-in-the-current-strict-au-111e9032
- Pair: implement
- Phase ID: generic-runtime-filesystem-refactor
- Phase Directory Key: generic-runtime-filesystem-refactor
- Phase Title: Refactor The Generic Runtime
- Scope: phase-local producer artifact

## Files changed
- `autoloop_v3/extensions/__init__.py`
- `autoloop_v3/extensions/session_paths.py`
- `autoloop_v3/runtime/runner.py`
- `autoloop_v3/runtime/stores/filesystem.py`
- `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
- `.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/decisions.txt`
- `.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/implement/phases/generic-runtime-filesystem-refactor/implementation_notes.md`

## Symbols touched
- `SessionPathStrategy`
- `SessionPaths`
- `extract_session_path_strategy(...)`
- `FilesystemSessionStore(..., path_strategy=...)`
- `PreparedRunContext`
- `_prepare_run_context(...)`
- `_extract_session_path_strategy(...)`
- `FilesystemPromptRegistry(workflow_parent, workspace.root)`

## Checklist mapping
- Milestone 3 / phase AC-2: refactored runner setup so strict workflow loading happens before run workspace creation, with workflow-declared session-path extraction applied to the generic filesystem session store.
- Milestone 3 / phase AC-3: preserved generic persisted session compatibility while extending the store with a strategy object path surface.
- Milestone 3 / phase AC-4: added explicit runtime test coverage for legacy `superloop.*` config discovery and removed ambient-current-directory prompt lookup from the generic runner.

## Assumptions
- The session-path extension surface is required in this phase even though the broader optional extensions package lands incrementally later, because the runtime acceptance criteria require a generic session-path strategy surface now.

## Preserved invariants
- Runtime core remains phase-agnostic and does not learn Autoloop-v1 naming or policy.
- Generic session payload compatibility, including legacy `thread_id`, is unchanged.
- Config discovery still supports both `autoloop.*` and legacy `superloop.*` filenames.
- Prompt resolution now depends only on explicit runner inputs and workflow-relative roots, not process launch directory.
- Workflow-owned parity code can keep using the existing raw path resolver until the workflow migration phase moves it to declared extensions.

## Intended behavior changes
- Workflows may now declare one `SessionPaths(...)` extension and have the generic runner apply its strategy to the filesystem session store automatically.
- Duplicate `SessionPaths(...)` declarations now fail before task/run workspace creation.
- Relative prompt lookup in the generic runner no longer falls back to `Path.cwd()`.

## Known non-changes
- No git or tracing extension behavior was added in this phase.
- `autoloop_v1` parity logging, decisions, clarification handling, and session filename policy remain workflow-owned.

## Expected side effects
- New optional import surface: `autoloop_v3.extensions`.

## Validation performed
- `pytest -q autoloop_v3/tests/runtime/test_compatibility_runtime.py autoloop_v3/tests/runtime/test_workflow_integration_parity.py autoloop_v3/tests/contract/test_engine_contracts.py autoloop_v3/tests/unit/test_validation.py`
- `pytest -q`
- `pytest -q autoloop_v3/tests/runtime/test_compatibility_runtime.py`

## Deduplication / centralization
- Centralized session-path declaration parsing in `autoloop_v3.extensions.session_paths` instead of leaving policy as ad hoc runner/store callbacks.
- Centralized runtime setup assembly in `PreparedRunContext` / `_prepare_run_context(...)`.
