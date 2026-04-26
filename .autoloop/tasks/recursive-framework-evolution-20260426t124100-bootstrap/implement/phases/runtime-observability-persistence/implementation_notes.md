# Implementation Notes

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: implement
- Phase ID: runtime-observability-persistence
- Phase Directory Key: runtime-observability-persistence
- Phase Title: Runtime Observability Persistence
- Scope: phase-local producer artifact

## Files Changed
- `runtime/git_tracking.py`
- `runtime/tracing.py`
- `runtime/static_graph.py`
- `runtime/workspace.py`
- `runtime/__init__.py`
- `tests/runtime/test_runtime_git_tracking.py`
- `tests/runtime/test_runtime_tracing.py`
- `tests/runtime/test_runtime_static_graph.py`
- `.autoloop/tasks/recursive-framework-evolution-20260426t124100-bootstrap/decisions.txt`

## Symbols Touched
- `RuntimeGitTracker`
- `RuntimeTraceWriter`
- `workflow_static_step_graph_payload`
- `write_static_step_graph`
- `update_run_git_tracking`
- `append_run_git_step`
- `update_run_tracing`
- `append_run_warning`
- `next_observability_sequence`

## Checklist Mapping
- Plan item 8: implemented `runtime/git_tracking.py`
- Plan item 9: implemented `runtime/tracing.py`
- Plan item 10: implemented `runtime/static_graph.py`
- Plan item 14: centralized `run.json` git/tracing/warning helpers in `runtime/workspace.py`
- Plan item 15: implemented runtime-owned raw-output file persistence plus trace refs
- Plan item 16: implemented append-safe next-sequence discovery across trace/git/raw
- Plan item 17: added focused runtime git/tracing/static-graph tests
- Reviewer follow-up: fixed ignore-mode handling beyond preflight, made runtime tracing persist `static_step_graph.json`, and reduced `run.json` git state back to summary/latest form
- Deferred by phase scope: runner/engine binding, workflow `GitTracking` filtering, end-to-end run wiring

## Assumptions
- This phase is allowed to land persistence primitives and direct tests before runner/engine integration.
- `trace.jsonl` sequence discovery can use the default runtime trace filename for now; custom trace-path resume wiring belongs to the later integration phase.
- `RuntimeTraceWriter` is the acceptable phase-local owner for writing `static_step_graph.json` because the later runner phase will already instantiate runtime observability with the compiled static graph payload.

## Preserved Invariants
- Runtime git tracking still uses full-workspace `git add --all` through `GitRepo.commit_all()`.
- Trace records only capture `git.commit_before_step`; `commit_after_step` remains confined to `git_tracking.jsonl`.
- Raw-output file writes are append-only and refuse to overwrite an existing sequence/step/role path.
- Workspace metadata writes stay centralized in `runtime/workspace.py`.
- `run.json` no longer duplicates full per-step git history; it keeps only latest-step git summary fields.

## Intended Behavior Changes
- Added runtime-owned append-only git-tracking JSONL persistence and `run.json` git-tracking summaries.
- Added runtime-owned trace JSONL persistence with raw-output file refs and typed provider-usage serialization.
- Added runtime-owned `static_step_graph.json` persistence during observability initialization.
- Added resume-sequence discovery across trace/git/raw evidence.
- Extended git/tracing ignore-mode handling to runtime write/commit failures, not just initial repo discovery.

## Known Non-Changes
- No runner ordering changes yet.
- No engine runtime-extension binding yet.
- No workflow-declared `GitTracking` filtering yet.
- No documentation updates yet.

## Expected Side Effects
- Future runner integration can bind runtime observability without re-implementing file formats or metadata merging.
- `run.json` now has stable helper paths for git-tracking, tracing, and warning metadata updates.
- Ignore-mode git/tracing failures now degrade into metadata warnings/disablement instead of escaping immediately after preflight.

## Validation Performed
- `python3 -m py_compile runtime/workspace.py runtime/static_graph.py runtime/git_tracking.py runtime/tracing.py tests/runtime/test_runtime_git_tracking.py tests/runtime/test_runtime_tracing.py tests/runtime/test_runtime_static_graph.py`
- Attempted `python3 -m pytest ...`, but `pytest` is unavailable in this environment.
- Attempted runtime smoke execution, but the environment is missing `pydantic`, so import-time runtime validation could not run here.

## Deduplication / Centralization Decisions
- Centralized observability metadata mutation in `runtime/workspace.py` rather than ad hoc JSON writes inside tracker/writer code.
- Kept static graph serialization in a dedicated runtime module, but made the trace writer consume that helper directly so the file is actually persisted by the phase-local runtime-owned path.
- Centralized git-tracker runtime error handling in one wrapper so ignore-mode semantics apply consistently across commit and JSONL write operations.
