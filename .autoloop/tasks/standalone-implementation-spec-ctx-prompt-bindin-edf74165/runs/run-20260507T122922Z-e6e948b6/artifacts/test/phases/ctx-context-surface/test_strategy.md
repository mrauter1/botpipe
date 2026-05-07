# Test Strategy

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: test
- Phase ID: ctx-context-surface
- Phase Directory Key: ctx-context-surface
- Phase Title: Add Request Context Surface
- Scope: phase-local producer artifact

## Behavior-to-test coverage

- AC-1 run snapshot access:
  - `tests/unit/test_primitives_and_stores.py::test_context_request_surface_reads_run_snapshot_and_task_request_file`
  - Covers lazy run-local message/text access, newline trimming, and `ctx.request.file == ctx.request_file`.
- AC-1 failure path:
  - `tests/unit/test_primitives_and_stores.py::test_context_message_raises_when_run_request_snapshot_is_missing`
  - Covers missing run snapshot error path and expected `WorkflowExecutionError`.
- AC-2 optional task request path:
  - `tests/unit/test_primitives_and_stores.py::test_context_request_surface_leaves_task_request_file_unset_when_absent`
  - Covers `ctx.request.task_file is None` when no task-level request exists while `ctx.message` still resolves from the run snapshot.
- AC-2 cloned context propagation:
  - `tests/unit/test_branch_group_context_sessions.py::test_branch_and_fan_in_contexts_preserve_parent_request_snapshot`
  - Covers branch and fan-in reuse of the parent run request file and task request path.
- AC-2 resume stability:
  - `tests/runtime/test_workspace_and_context.py::test_resume_context_message_uses_run_local_request_snapshot_not_mutated_task_request`
  - Covers persisted run-local request precedence over later task request mutation on resume.
- Shared helper contract:
  - `tests/unit/test_primitives_and_stores.py::test_validate_safe_ctx_reference_rejects_unsafe_segments`
  - Covers allowed `ctx` path shapes plus unsafe and unsupported deeper-path rejection.

## Preserved invariants checked

- `ctx.message` continues to derive from `run_folder/request.md` when explicit request paths are omitted.
- Missing task-level request metadata does not manufacture a fake path.
- Branch/fan-in cloning does not alter state/input/params semantics while preserving request context.

## Edge cases and failure paths

- Internal newline preservation with only trailing newline stripping.
- Missing run snapshot raises instead of silently returning empty text.
- Unsupported `ctx.*` deeper paths are rejected by the shared helper.

## Stabilization approach

- All coverage is filesystem-local and deterministic under `tmp_path`.
- No timing, network, or ordering assumptions are encoded.

## Known gaps

- Prompt rendering, artifact-path rejection, and compile-time placeholder validation remain intentionally uncovered in this phase because they are out of scope for `ctx-context-surface`.
