# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: implement
- Phase ID: engine-runner-observability-binding
- Phase Directory Key: engine-runner-observability-binding
- Phase Title: Engine And Runner Binding
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | `runtime/git_tracking.py:RuntimeGitTracker._commit_run_initialized_operation`, `RuntimeGitTracker._after_run_operation`, `RuntimeGitTracker._fatal_operation`
  The runtime-owned init/finish/fatal commit path writes `git_tracking.jsonl` and `run.json` *after* calling `commit_all()`. That leaves the repository dirty at the end of a `commit_policy=run` run and after terminal/fatal completion, because `commit_after_init` / `commit_after_run` metadata is persisted outside the commit it summarizes. A resumed run can then fail its clean-start preflight on the runtime's own leftover metadata instead of user changes, which breaks the replay boundary and AC-4/AC-5. Minimal fix: centralize init/terminal git-tracking persistence so the final runtime-owned metadata write is itself captured by the corresponding milestone commit, or otherwise ensure the post-commit summary update cannot leave tracked changes behind.

- IMP-002 | blocking | `runtime/observability.py:BoundRuntimeObservability.on_fatal`, `core/engine.py:Engine._notify_fatal`
  Fatal-path observability failures are silently dropped even when the runtime config says `failure_mode="raise"`. `BoundRuntimeObservability.on_fatal()` catches and ignores all exceptions from `trace_writer.fatal()` and `git_tracker.on_fatal()`, and `_notify_fatal()` swallows any exception raised by extensions anyway. That contradicts the accepted requirement that runtime observability failures respect their configured failure modes; a fatal trace/git write failure now becomes undetectable. Minimal fix: route fatal observability writes through one central path that preserves the original engine exception ordering while still surfacing configured raise-mode observability failures instead of double-swallowing them.

- IMP-003 | blocking | `tests/runtime/test_workspace_and_context.py`, `runtime/runner.py`
  The phase did not complete the required runtime-test migration for the new default git-tracked execution path. Running `.venv/bin/python -m pytest tests/runtime/test_workspace_and_context.py -q` still produces 13 failures, all because those filesystem-run tests neither initialize a temp git repository nor explicitly disable git tracking. The request and shared decisions explicitly require those tests to opt out rather than weakening the runtime default, so the current branch is not validation-complete. Minimal fix: update the remaining runtime test modules or shared helpers so temp filesystem runs either bootstrap git or pass explicit runtime git opt-out config.

- IMP-004 | non-blocking | Cycle 2 re-review
  Verified that `IMP-001`, `IMP-002`, and `IMP-003` are addressed in the current implementation. No new actionable findings were identified in the phase-local scope after rechecking the runtime git finalization path, fatal-path observability propagation, CLI runtime-config wiring, and the updated runtime/CLI test surfaces.
