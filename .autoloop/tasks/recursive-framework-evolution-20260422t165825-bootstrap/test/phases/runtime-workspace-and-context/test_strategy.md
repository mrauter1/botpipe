# Test Strategy

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: test
- Phase ID: runtime-workspace-and-context
- Phase Directory Key: runtime-workspace-and-context
- Phase Title: Runtime Workspace And Context
- Scope: phase-local producer artifact

## Behavior Coverage Map

- AC-1 task -> workflow -> run layout:
  `tests/runtime/test_workspace_and_context.py::test_run_creates_task_workflow_run_layout_and_immutable_request_snapshots`
  checks `.autoloop/tasks/<task>/wf_<workflow>/runs/<run>` creation, workflow metadata, run metadata, and that shared task files such as `messages.jsonl` do not move into run scope.
- AC-2 message-first request handling:
  `tests/runtime/test_workspace_and_context.py::test_run_creates_task_workflow_run_layout_and_immutable_request_snapshots`
  checks task `messages.jsonl`, mutable task `request.md`, and immutable per-run `request.md` snapshots across multiple runs on one task.
- AC-3 context, placeholders, and prompt resolution:
  `tests/runtime/test_workspace_and_context.py::test_runtime_context_and_prompt_resolution_use_workflow_scope_and_package_root`
  checks `workflow_name`, `workflow_folder`, `package_folder`, `workflow_params`, and package-root prompt lookup.
- Resume immutability edge cases:
  `tests/runtime/test_workspace_and_context.py::test_resume_preserves_persisted_workflow_params_when_not_resupplied`
  covers omitted resume params preserving persisted run params.
  `tests/runtime/test_workspace_and_context.py::test_resume_ignores_explicit_workflow_param_override_for_existing_run`
  covers explicit resume-time override attempts being ignored for existing runs.
- Preserved invariant, tracing remains run-local:
  `tests/runtime/test_optional_extensions.py::test_tracing_extension_writes_a_sidecar_trace_without_replacing_events_jsonl`
  checks tracing output under the workflow-scoped run directory rather than task scope.

## Edge Cases / Failure Paths

- Multiple runs on one task preserve earlier run snapshots while updating the shared task request snapshot.
- Resume continues a paused run with persisted workflow params rather than clearing or replacing them.
- Explicit resume-time attempts to replace persisted workflow params are ignored for existing runs.

## Stabilization

- Tests use `tmp_path` sandboxes and `ScriptedLLMProvider` to avoid timing, network, or ordering flake.
- Coverage relies on filesystem assertions instead of timestamps or nondeterministic directory enumeration beyond selecting created run directories in the temp sandbox.

## Known Gaps

- Execution-level `pytest` runs are still blocked in this shell because `pytest` and `pydantic` are missing.
- Child workflow execution semantics and public CLI redesign remain out of scope for this phase.
