# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: implement
- Phase ID: runtime-observability-persistence
- Phase Directory Key: runtime-observability-persistence
- Phase Title: Runtime Observability Persistence
- Scope: phase-local authoritative verifier artifact

## Findings

### IMP-001 — blocking — `runtime/git_tracking.py` failure mode is only honored during preflight
`RuntimeGitTracker` applies `failure_mode` when the repository is missing or dirty in `prepare_before_workspace_creation()`, but every later operational path (`commit_run_initialized()`, `after_step()`, `after_run()`, `on_fatal()`, and `_record()`) lets `GitRepoError` and file-write failures escape unconditionally. A concrete failure case is a clean repo without configured git author identity or with a rejecting commit hook: `prepare_before_workspace_creation()` succeeds, then `git commit` fails and aborts the run even when `failure_mode="ignore"`. This violates the requested runtime observability failure-mode behavior. Minimal fix: centralize git-tracker operation handling behind one helper that converts commit / JSONL write failures into the configured ignore behavior instead of only guarding the initial repo-discovery checks.

### IMP-002 — blocking — `runtime/tracing.py` constructor ignores `tracing.failure_mode`
`RuntimeTraceWriter.__init__()` eagerly calls `mkdir()`, `touch()`, and `update_run_tracing()` outside the guarded failure-mode path. If the configured trace path or `run.json` location is unwritable, construction raises immediately even when `TracingRuntimeConfig.failure_mode == "ignore"`, so the runtime never reaches the promised “best-effort warning and continue” behavior. This is a material contract violation for the requested tracing API. Minimal fix: route initialization-time file creation and metadata writes through the same failure-mode-aware guard used for append operations, with `append_run_warning()` as the ignore-path sink.

### IMP-003 — blocking — `static_step_graph.json` is never actually persisted by the runtime-owned path
The phase objective and in-scope contract require persisting `static_step_graph.json`, but the implementation only adds a helper in `runtime/static_graph.py`. No runtime-owned code path calls `write_static_step_graph()`, while `RuntimeTraceWriter._update_metadata()` advertises `"static_step_graph_file": "static_step_graph.json"` unconditionally in `run.json`. In a normal run using this phase’s changes, the metadata can point to a nonexistent file, so the required evidence artifact is still missing. Minimal fix: wire static-graph writing into a single phase-owned initialization path alongside trace/git metadata setup, rather than leaving the writer helper orphaned.

### IMP-004 — non-blocking — `run.json` now duplicates per-step git history instead of staying aggregate/latest
`append_run_git_step()` stores every step record under `run.json.git_tracking.steps`, even though the request explicitly positions `git_tracking.jsonl` as the authoritative append-only step history and `run.json` as aggregate/latest metadata. This adds a second per-step history format to maintain and will bloat `run.json` on long or resumed runs. Minimal fix: keep only summary/latest git-tracking fields in `run.json` and leave step-by-step history exclusively in `git_tracking.jsonl`.
