# Implementation Notes

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: implement
- Phase ID: runtime-workspace-and-context
- Phase Directory Key: runtime-workspace-and-context
- Phase Title: Runtime Workspace And Context
- Scope: phase-local producer artifact

## Files Changed

- `runtime/workspace.py`
- `runtime/runner.py`
- `runtime/__init__.py`
- `core/context.py`
- `core/extensions.py`
- `core/artifacts.py`
- `core/engine.py`
- `workflows/autoloop_v1/parity.py`
- `recursive_autoloop/run_recursive_autoloop.sh`
- `tests/runtime/test_optional_extensions.py`
- `tests/runtime/test_workspace_and_context.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_stdlib_and_extensions.py`

## Symbols Touched

- `TaskWorkspace`, `WorkflowWorkspace`, `RunWorkspace`
- `ensure_workspace(...)`, `ensure_workflow_workspace(...)`, `create_run(...)`, `open_existing_run(...)`
- `resolve_run_workflow_params(...)`
- `update_run_metadata(...)`, `update_workflow_metadata(...)`, `latest_run_id(...)`
- `RunnerOptions`, `PreparedRunContext`, `prepare_runtime_services(...)`, `run_workflow(...)`
- `Context`, `RunBinding`, `resolve_artifact_template(...)`, `Engine.run(...)`, `Engine.resume(...)`
- `run_autoloop_v1(...)`, `ensure_autoloop_v1_workspace(...)`

## Checklist Mapping

- Plan item 5: completed for runtime persistence by introducing task scope plus `wf_<workflow>` scope plus `runs/<run-id>`.
- Plan item 6: completed by adding task `messages.jsonl`, mutable task `request.md`, and immutable run-local `request.md`.
- Plan item 7: completed for `workflow_name`, `workflow_folder`, `package_folder`, and persisted `workflow_params`; `ctx.invoke_workflow(...)` is exposed as a runtime-backed stub only and actual child-run execution remains deferred to the later sub-workflow phase.
- Phase AC-1/AC-2/AC-3: addressed through workspace refactor, run/workflow metadata files, placeholder/context updates, and package-root prompt resolution tests.

## Intended Behavior Changes

- New runs now persist under `.autoloop/tasks/<task-id>/wf_<workflow>/runs/<run-id>/`.
- Task request history is append-only in `messages.jsonl`; task `request.md` is the current snapshot and run `request.md` is copied at run creation.
- Runtime metadata now writes `workflow.json` at workflow scope and `run.json` at run scope.
- Relative prompt lookup now resolves from the workflow package root only; the runtime no longer falls back to the repository root/cwd-style secondary lookup.
- Resumed runs now preserve persisted `workflow_params` when the caller does not re-supply them; runtime context and `run.json` continue to reflect the original run-scoped parameter set.
- Existing runs now treat persisted `run.json` workflow params as authoritative, so resume-time attempts to replace them are ignored and run-scoped params remain immutable for the full life of the run.

## Preserved Invariants

- `task_id`, `run_id`, `task_folder`, and `run_folder` remain stable runtime concepts.
- Session files and checkpoints remain run-local.
- Tracing remains run-local.
- Autoloop-v1 parity sidecars (`raw_phase_log.md`, `decisions.txt`, plan session paths) remain available while using the new workflow-scoped run layout.

## Known Non-Changes / Deferred

- Public CLI contract redesign is not implemented in this phase.
- Workflow-parameter validation/coercion is not implemented in this phase; the runtime only surfaces and persists `workflow_params`.
- Child workflow execution semantics are not implemented in this phase; `Context.invoke_workflow(...)` exists only as the runtime-backed entrypoint seam for the later phase.
- Git tracking still scopes to task workspace in this phase; the workflow-scope default flip remains deferred to the later git phase.

## Dependency / Out-of-Phase Justification

- `recursive_autoloop/run_recursive_autoloop.sh` was updated as a dependency fix because its latest-run/status inspection hard-coded the removed flat `tasks/<task>/runs/<run>` layout and would stop finding resumable runs after this workspace migration.

## Validation Performed

- `python3 -m compileall core runtime workflows tests`
- `python3 -m py_compile core/context.py core/extensions.py core/artifacts.py core/engine.py runtime/__init__.py runtime/runner.py runtime/workspace.py workflows/autoloop_v1/parity.py tests/runtime/test_optional_extensions.py tests/runtime/test_workspace_and_context.py tests/unit/test_primitives_and_stores.py tests/unit/test_stdlib_and_extensions.py`
- `bash -n recursive_autoloop/run_recursive_autoloop.sh`
- Added source-level regression coverage for pause/resume preserving persisted `workflow_params` and ignoring explicit resume-time overrides in `tests/runtime/test_workspace_and_context.py`.

## Validation Gaps

- `pytest` is not installed in this environment.
- Runtime imports requiring `pydantic` could not be executed here because `pydantic` is also missing from the environment, so execution-level test runs were not possible in this shell.
