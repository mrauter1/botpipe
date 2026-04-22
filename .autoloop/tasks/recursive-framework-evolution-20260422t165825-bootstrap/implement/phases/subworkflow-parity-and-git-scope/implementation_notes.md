# Implementation Notes

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: implement
- Phase ID: subworkflow-parity-and-git-scope
- Phase Directory Key: subworkflow-parity-and-git-scope
- Phase Title: Subworkflow Parity And Git Scope
- Scope: phase-local producer artifact

## Files changed

- `core/context.py`
- `core/extensions.py`
- `core/engine.py`
- `runtime/events.py`
- `runtime/loader.py`
- `runtime/runner.py`
- `runtime/workspace.py`
- `extensions/git/__init__.py`
- `extensions/git/declaration.py`
- `extensions/git/filters.py`
- `extensions/git/repo.py`
- `extensions/git/runtime.py`
- `workflows/autoloop_v1/parity.py`
- `workflows/autoloop_v1/workflow.py`
- `workflows/autoloop_v1/workflow.toml`
- `workflows/autoloop_v1/prompts/plan_producer.md`
- `workflows/autoloop_v1/prompts/plan_verifier.md`
- `workflows/autoloop_v1/prompts/implement_producer.md`
- `workflows/autoloop_v1/prompts/implement_verifier.md`
- `workflows/autoloop_v1/prompts/test_producer.md`
- `workflows/autoloop_v1/prompts/test_verifier.md`
- `tests/runtime/test_workspace_and_context.py`
- `tests/runtime/test_workflow_integration_parity.py`
- `tests/runtime/test_optional_extensions.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/contract/test_engine_contracts.py`

## Symbols touched

- `core.context.ChildWorkflowResult`
- `Context.invoke_workflow(...)`
- `core.extensions.StepStart.answer`
- `core.extensions.StepFinish.producer_raw_output`
- `core.extensions.StepFinish.verifier_raw_output`
- `runtime.loader.coerce_workflow_parameter_mapping(...)`
- `runtime.workspace.write_parent_run_metadata(...)`
- `runtime.workspace.append_child_run_record(...)`
- `runtime.workspace.ensure_workspace(..., record_message=...)`
- `RunnerOptions.record_task_message`
- `runtime.runner._build_workflow_invoker(...)`
- `runtime.runner._build_child_workflow_result(...)`
- `runtime.runner._child_run_record_payload(...)`
- `runtime.runner._child_run_record_payload_from_parts(...)`
- `runtime.events.EventLogger.emit(...)`
- `extensions.git.workflow_workspace_pathspec(...)`
- `GitTrackingConfig.track_workflow_workspace_artifacts`
- `GitRepo.discover(...)`
- `GitRepo._git(...)`
- `workflows.autoloop_v1.parity.AutoloopV1Parity`
- `workflows.autoloop_v1.workflow.AutoloopV1`

## Checklist mapping

- Plan milestone 4 / phase objective: implemented first-class child workflow execution by imported class and workflow package name.
- Plan milestone 4 / phase objective: added child result contract, parent `children.jsonl`, and child `parent.json` metadata.
- Plan milestone 4 / phase objective: enriched `StepFinish` for package-local parity reconstruction and migrated Autoloop-v1 to a workflow-local extension on the general runtime.
- Plan milestone 4 / phase objective: narrowed git tracking defaults and filters from task scope to workflow scope.
- No checklist item intentionally deferred inside this phase scope.

## Assumptions

- Prior clarification stands: wrapper-local `--pairs` and `--full-auto-answers` are not required behavior for this phase.
- Child workflow parameters should use the same loader validation/coercion path as top-level package execution.

## Preserved invariants

- Child workflows stay under the same `task_id` but always receive isolated run folders, workflow folders, checkpoints, sessions, request snapshots, trace files, and pending-answer state.
- Child workflow invocation no longer mutates shared task-level `request.md` or `messages.jsonl`; nested child messages stay run-local.
- `ctx.invoke_workflow(...)` remains runtime-backed only and is supported from `SystemStep` handlers without exposing a second execution model.
- Autoloop-v1 continues to preserve raw logs, `sessions/plan.json`, per-phase sessions, clarification persistence, and blocked/question/failed status mapping without reintroducing a custom harness.
- Git tracking remains workflow-declared opt-in and tracing remains run-local.

## Intended behavior changes

- Parent workflows can now invoke child workflows by imported class or package name and receive a stable structured result object with identity, terminal status, last event, metadata, artifact references, and path references.
- Child runs now write `parent.json`, parent runs append `children.jsonl`, and the child `run.json` also carries parent linkage.
- Parent-side child history now uses the same serialized field set for fatal and non-fatal child outcomes.
- Autoloop-v1 now runs through the general runtime with package-local prompts and parity side effects reconstructed from extension callbacks rather than provider wrapping.
- Default git tracking scope now filters to `workflow_folder`, and git commands ignore inherited outer-repo selection env vars.

## Known non-changes

- No broader docs rewrite was done in this phase.
- No public CLI surface was changed here beyond consuming the package-based runtime already delivered by earlier phases.
- No wrapper-only pair-selection or auto-answer controls were reintroduced.

## Expected side effects

- Workflow-local parity code may append extra runtime events to `events.jsonl`; event sequencing is therefore synchronized against the on-disk log before each emit.
- Parent-side child history is append-only in `children.jsonl`; callers should treat `parent.json` as the child-side provenance record.
- Nested child-run messages do not appear in the shared task message ledger; only top-level task messages update task request state.

## Validation performed

- `python3 -m py_compile core/context.py core/extensions.py core/engine.py runtime/loader.py runtime/workspace.py runtime/runner.py runtime/events.py extensions/git/repo.py tests/runtime/test_optional_extensions.py tests/unit/test_stdlib_and_extensions.py`
- `python3 -m py_compile runtime/runner.py runtime/workspace.py tests/runtime/test_workspace_and_context.py`
- `.venv/bin/python -m pytest tests/runtime/test_workspace_and_context.py -q`
- `.venv/bin/python -m pytest tests/runtime/test_workspace_and_context.py tests/runtime/test_workflow_integration_parity.py tests/runtime/test_optional_extensions.py tests/unit/test_stdlib_and_extensions.py tests/contract/test_engine_contracts.py -q`
- Focused git slice after env sanitation: `.venv/bin/python -m pytest tests/runtime/test_optional_extensions.py tests/unit/test_stdlib_and_extensions.py -q`

## Deduplication / centralization decisions

- Child workflow parameter coercion is centralized in `runtime.loader.coerce_workflow_parameter_mapping(...)` so CLI runs and `ctx.invoke_workflow(...)` follow the same validation rules.
- Git repo env sanitation is centralized in `extensions.git.repo` instead of duplicating repo-selection workarounds across runtime callers.
