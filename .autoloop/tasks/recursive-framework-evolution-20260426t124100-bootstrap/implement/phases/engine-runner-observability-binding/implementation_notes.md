# Implementation Notes

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: implement
- Phase ID: engine-runner-observability-binding
- Phase Directory Key: engine-runner-observability-binding
- Phase Title: Engine And Runner Binding
- Scope: phase-local producer artifact

## Files changed
- `core/engine.py`
- `runtime/__init__.py`
- `runtime/loader.py`
- `runtime/observability.py`
- `runtime/runner.py`
- `runtime/workspace.py`
- `tests/runtime/test_optional_extensions.py`
- `tests/runtime/test_runtime_git_tracking.py`

## Symbols touched
- `Engine.__init__`
- `Engine._bind_extensions`
- `Engine._notify_fatal`
- `resolve_workflow_reference`
- `_no_bytecode_writes`
- `_cleanup_workflow_pycache`
- `BoundRuntimeObservability`
- `RunnerOptions.runtime_config`
- `_execute_compiled_workflow`
- `_plan_workspaces`
- `_prepare_workspaces`
- `_runtime_compiled_workflow`
- `_resume_git_tracking_warnings`
- `resolve_task_workspace`
- `resolve_workflow_workspace`
- `resolve_run_workspace`

## Checklist mapping
- Runtime extension factory support: completed in `core/engine.py` and `runtime/runner.py`.
- Runner/workspace preflight ordering: completed with pure workspace planning helpers and preflight before materialization.
- Workflow-declared `GitTracking` ignore path: completed with event + `run.json` warning persistence.
- Resume git-tracking mismatch warning: completed for previously tracked segments resumed with tracking disabled.

## Assumptions
- Filtering workflow `GitTracking` at the runner boundary is sufficient because direct `Engine(...)` usage is outside the runtime-owned observability path.
- Fatal-path observability should not mask the original engine exception; fatal hook write failures are treated as best effort there.

## Preserved invariants
- Workflow-declared extension tuple order is preserved after runtime extensions are prepended.
- Workflow-declared tracing remains bindable and continues to write its sidecar independently of runtime tracing.
- Run binding contents and core step/terminal event models remain unchanged apart from runtime extension ordering.

## Intended behavior changes
- Runtime git preflight now runs before any task/workflow/run workspace materialization in the filesystem runtime path.
- Runtime-owned observability binds without workflow declarations, and workflow-declared `GitTracking` is ignored with a deprecation warning instead of creating duplicate commits.
- Workflow resolution no longer leaves `__pycache__` dirt behind that would invalidate the clean-repo preflight.

## Known non-changes
- Workflow-declared tracing is not filtered or rewritten.
- This phase does not sweep every runtime integration test module that still assumes non-git temporary roots; only phase-relevant targeted coverage was updated here.

## Expected side effects
- Direct runtime callers can now pass `RunnerOptions.runtime_config`, and child workflow invocations inherit that runtime config.
- New pure workspace resolvers allow path planning without filesystem writes and can be reused by later phases.

## Validation performed
- `.venv/bin/python -m py_compile core/engine.py runtime/runner.py runtime/loader.py runtime/observability.py runtime/workspace.py tests/runtime/test_optional_extensions.py tests/runtime/test_runtime_git_tracking.py`
- `.venv/bin/python -m pytest tests/runtime/test_runtime_git_tracking.py tests/runtime/test_runtime_tracing.py tests/contract/test_engine_contracts.py -q`
- `.venv/bin/python -m pytest tests/runtime/test_optional_extensions.py -q`
- Sampled broader module check: `tests/runtime/test_workspace_and_context.py -q` still fails because many older tests do not yet initialize git or opt out explicitly under the new runtime default.

## Deduplication / centralization
- Preflight-safe path planning is centralized in workspace resolvers plus `_plan_workspaces` instead of being reimplemented inside the runner.
- Runtime `GitTracking` filtering and warning emission are centralized in `_runtime_compiled_workflow`, keeping the engine extension binding path generic.
