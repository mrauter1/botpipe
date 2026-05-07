# Implementation Notes

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: implement
- Phase ID: ctx-context-surface
- Phase Directory Key: ctx-context-surface
- Phase Title: Add Request Context Surface
- Scope: phase-local producer artifact

## Files changed

- `autoloop/core/context.py`
- `autoloop/core/context_placeholders.py`
- `autoloop/core/engine.py`
- `autoloop/core/branch_groups/context.py`
- `autoloop/runtime/runner.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_branch_group_context_sessions.py`
- `tests/runtime/test_workspace_and_context.py`

## Symbols touched

- `RequestContext`
- `Context.__init__`
- `Context.request_file`
- `Context.request`
- `Context.message`
- `validate_safe_ctx_reference`
- `create_branch_context`
- `create_fan_in_context`
- `Engine.run`
- `Engine.run_async`
- `Engine.resume`
- `Engine.resume_async`

## Checklist mapping

- Milestone 1 / phase AC-1: added lazy run request surface on `Context` backed by `run_folder/request.md`, with default derivation for synthetic contexts.
- Milestone 1 / phase AC-2: propagated `request_file` and `task_request_file` through runner-backed engine entrypoints and branch/fan-in child context cloning.
- Shared contract seed: added `autoloop/core/context_placeholders.py` for later compile-time/runtime `ctx.*` validation reuse.

## Assumptions

- Direct engine callers should remain source-compatible, so explicit request-path threading was added as optional internal parameters with existing path-derivation fallback preserved.
- Task-level request metadata remains optional; `ctx.request.task_file` is `None` when `task_folder/request.md` is absent.

## Preserved invariants

- `ctx.input`, `ctx.state`, and `ctx.params` semantics in Python steps were not changed.
- Run persistence layout and CLI/runtime workspace creation stay unchanged.
- Resume still reads the existing run-local `request.md`; task request mutation does not replace the persisted run snapshot.

## Intended behavior changes

- Python/system step contexts now expose `ctx.request_file`, `ctx.request`, and `ctx.message`.
- Branch and fan-in child contexts now preserve the parent run’s explicit request snapshot paths instead of re-deriving them.

## Known non-changes

- Prompt rendering, compile-time prompt validation, artifact-path rejection, and documentation updates are intentionally deferred to later phases.
- No provider adapter changes were made.

## Expected side effects

- Engine entrypoints now accept optional request-path arguments, used by the filesystem runner to pin root contexts to the persisted run snapshot.

## Validation performed

- `19 passed in 0.92s` via:
  - `tests/unit/test_branch_group_context_sessions.py`
  - `tests/unit/test_primitives_and_stores.py::test_context_request_surface_reads_run_snapshot_and_task_request_file`
  - `tests/unit/test_primitives_and_stores.py::test_context_message_raises_when_run_request_snapshot_is_missing`
  - `tests/unit/test_primitives_and_stores.py::test_validate_safe_ctx_reference_rejects_unsafe_segments`
  - `tests/unit/test_primitives_and_stores.py::test_artifact_template_resolution_supports_dot_notation_and_missing_keys`
  - `tests/runtime/test_workspace_and_context.py::test_run_creates_task_workflow_run_layout_and_immutable_request_snapshots`
  - `tests/runtime/test_workspace_and_context.py::test_resume_preserves_persisted_workflow_params_when_not_resupplied`
  - `tests/runtime/test_workspace_and_context.py::test_resume_context_message_uses_run_local_request_snapshot_not_mutated_task_request`

## Deduplication / centralization

- Centralized the future `ctx.*` allowlist and safe-path syntax contract in `autoloop/core/context_placeholders.py` instead of scattering early copies across `Context`, runner, or tests.
