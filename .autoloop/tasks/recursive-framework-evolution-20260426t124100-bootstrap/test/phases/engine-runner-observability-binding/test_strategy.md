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

## Known gaps
- This test phase does not broaden into the docs-only acceptance checks, because the phase-local runtime/runner risk was fully exercised in code-level runtime and contract suites.
