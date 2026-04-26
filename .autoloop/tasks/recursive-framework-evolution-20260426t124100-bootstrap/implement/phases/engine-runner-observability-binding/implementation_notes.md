# Implementation Notes

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: implement
- Phase ID: engine-runner-observability-binding
- Phase Directory Key: engine-runner-observability-binding
- Phase Title: Engine And Runner Binding
- Scope: phase-local producer artifact

## Files changed
- `core/engine.py`
- `runtime/cli.py`
- `runtime/__init__.py`
- `runtime/git_tracking.py`
- `runtime/loader.py`
- `runtime/observability.py`
- `runtime/runner.py`
- `runtime/workspace.py`
- `tests/runtime/test_optional_extensions.py`
- `tests/runtime/test_package_cli.py`
- `tests/runtime/test_runtime_git_tracking.py`
- `tests/runtime/test_workspace_and_context.py`

## Symbols touched
- `Engine.__init__`
- `Engine._bind_extensions`
- `Engine._notify_fatal`
- `_handle_run`
- `_handle_resume`
- `_handle_answer`
- `RuntimeGitTracker._after_run_operation`
- `RuntimeGitTracker._fatal_operation`
- `RuntimeGitTracker._flush_runtime_metadata`
- `RuntimeGitTracker._metadata_commit_message`
- `resolve_workflow_reference`
- `_no_bytecode_writes`
- `_cleanup_workflow_pycache`
- `BoundRuntimeObservability`
- `RunnerOptions.runtime_config`
- `_execute_compiled_workflow`
- `_runtime_observability_error`
- `_plan_workspaces`
- `_prepare_workspaces`
- `_runtime_compiled_workflow`
- `_resume_git_tracking_warnings`
- `_runner_options`
- `_git`
- `_init_repo`
- `resolve_task_workspace`
- `resolve_workflow_workspace`
- `resolve_run_workspace`

## Checklist mapping
- Runtime extension factory support: completed in `core/engine.py` and `runtime/runner.py`.
- Runner/workspace preflight ordering: completed with pure workspace planning helpers and preflight before materialization.
- Workflow-declared `GitTracking` ignore path: completed with event + `run.json` warning persistence.
- Resume git-tracking mismatch warning: completed for previously tracked segments resumed with tracking disabled.
- Reviewer IMP-001: resolved by moving terminal/fatal git finalization behind runner-owned terminal metadata writes and flushing post-commit summaries with a deterministic metadata commit.
- Reviewer IMP-002: resolved by allowing runtime observability fatal-hook errors to propagate selectively while preserving best-effort workflow extension fatal semantics.
- Reviewer IMP-003: resolved by updating remaining runtime/package tests to opt out explicitly or initialize git where CLI override behavior is under test.

## Assumptions
- Filtering workflow `GitTracking` at the runner boundary is sufficient because direct `Engine(...)` usage is outside the runtime-owned observability path.
- When runtime fatal observability is configured with `failure_mode="raise"`, the top-level failure may convert to the observability error while preserving the original workflow failure as `__cause__`.

## Preserved invariants
- Workflow-declared extension tuple order is preserved after runtime extensions are prepended.
- Workflow-declared tracing remains bindable and continues to write its sidecar independently of runtime tracing.
- Run binding contents and core step/terminal event models remain unchanged apart from runtime extension ordering.
- Workflow-declared extension fatal handlers remain best-effort; only runtime observability marks fatal-hook failures as propagating.

## Intended behavior changes
- Runtime git preflight now runs before any task/workflow/run workspace materialization in the filesystem runtime path.
- Runtime-owned observability binds without workflow declarations, and workflow-declared `GitTracking` is ignored with a deprecation warning instead of creating duplicate commits.
- Workflow resolution no longer leaves `__pycache__` dirt behind that would invalidate the clean-repo preflight.
- Terminal/fatal git commits now happen after runner-owned `run_finished` metadata writes, and a deterministic metadata follow-up commit keeps the repository clean while preserving `commit_after_run` summaries.
- CLI run/resume/answer now actually honor resolved runtime observability config by passing `config.runtime` into `RunnerOptions`.

## Known non-changes
- Workflow-declared tracing is not filtered or rewritten.

## Expected side effects
- Direct runtime callers can now pass `RunnerOptions.runtime_config`, and child workflow invocations inherit that runtime config.
- New pure workspace resolvers allow path planning without filesystem writes and can be reused by later phases.
- Git-tracked terminal/fatal runs add one deterministic metadata-only follow-up commit to capture `run.json` / `git_tracking.jsonl` summaries without leaving the workspace dirty.

## Validation performed
- `.venv/bin/python -m pytest tests/runtime/test_runtime_git_tracking.py tests/runtime/test_runtime_tracing.py tests/runtime/test_optional_extensions.py tests/runtime/test_workspace_and_context.py tests/runtime/test_package_cli.py tests/runtime/test_provider_backends.py tests/contract/test_engine_contracts.py -q`
- Consolidated result: `161 passed`

## Deduplication / centralization
- Preflight-safe path planning is centralized in workspace resolvers plus `_plan_workspaces` instead of being reimplemented inside the runner.
- Runtime `GitTracking` filtering and warning emission are centralized in `_runtime_compiled_workflow`, keeping the engine extension binding path generic.
- Runner-owned terminal/fatal git finalization is centralized through `BoundRuntimeObservability.commit_terminal()` / `commit_fatal()` so end-of-run metadata ordering is handled in one place.
