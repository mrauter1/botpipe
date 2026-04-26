# Test Strategy

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: test
- Phase ID: engine-runner-observability-binding
- Phase Directory Key: engine-runner-observability-binding
- Phase Title: Engine And Runner Binding
- Scope: phase-local producer artifact

## Behaviors covered
- Runtime-owned git tracking supersedes workflow-declared `GitTracking`, commits full-workspace changes, and records the deprecation warning without duplicate workflow-owned commits.
- Terminal/fatal runtime git finalization now leaves the repository clean, including the metadata follow-up commit path.
- Paused git-tracked runs remain clean and can resume successfully under runtime-owned git tracking.
- Resuming a previously git-tracked paused run with git tracking disabled is expected to persist `runtime_git_tracking_disabled_on_resume` in `run.json` and leave earlier `git_tracking.jsonl` records untouched.
- Resuming a previously untracked paused run with git tracking enabled is expected to start `git_tracking.jsonl` from the resume point without backfilling earlier segments.
- Fatal runtime tracing with `failure_mode="raise"` propagates the observability failure while preserving the original workflow failure as the exception cause.
- CLI `run` / `resume` / `answer` paths actually pass resolved runtime config into `RunnerOptions`, so `--no-git`, `--git-commit-policy`, and `--no-trace` affect execution.
- Non-git temp-root runtime and CLI tests explicitly disable git tracking unless the test is intentionally exercising git-enabled behavior.

## Preserved invariants checked
- Runtime extensions still bind before workflow-declared extensions while workflow extension semantics remain intact.
- Workflow-declared tracing remains sidecar-compatible and does not replace runtime `trace.jsonl` or `events.jsonl`.
- Dirty-repo preflight still fails before run workspace creation when runtime git tracking is enabled in raise mode.

## Edge and failure paths
- `commit_policy="run"` and `commit_policy="step"` both preserve clean terminal state after runtime-owned metadata writes.
- Pause/resume uses the same run directory without tripping runtime-owned clean-start preflight on leftover observability files.
- Fatal trace persistence failure is exercised under `failure_mode="raise"` to ensure the error is not silently swallowed.

## Files exercised
- `tests/runtime/test_runtime_git_tracking.py`
- `tests/runtime/test_optional_extensions.py`
- `tests/runtime/test_workspace_and_context.py`
- `tests/runtime/test_package_cli.py`
- `tests/runtime/test_runtime_tracing.py`
- `tests/contract/test_engine_contracts.py`

## Validation
- `.venv/bin/python -m pytest tests/runtime/test_optional_extensions.py tests/runtime/test_runtime_git_tracking.py tests/runtime/test_runtime_tracing.py tests/contract/test_engine_contracts.py -q`
- Result: `91 passed`
- `.venv/bin/python -m pytest tests/runtime/test_optional_extensions.py tests/runtime/test_runtime_git_tracking.py tests/runtime/test_runtime_tracing.py tests/contract/test_engine_contracts.py -q`
- Result: `1 failed, 92 passed`
- Failing case: `test_resume_with_git_tracking_disabled_after_tracked_segment_records_warning_without_backfill` currently exposes a runtime bug where the required `runtime_git_tracking_disabled_on_resume` warning is not persisted before resume metadata rewrites `run.json.git_tracking`.

## Known gaps
- No additional phase-local coverage gap remains after adding the AC-5 mixed-mode resume tests; the current blocker is the implementation bug surfaced by the tracked-to-disabled resume warning assertion.
