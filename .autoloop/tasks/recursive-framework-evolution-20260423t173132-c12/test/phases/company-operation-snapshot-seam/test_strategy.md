# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c12
- Pair: test
- Phase ID: company-operation-snapshot-seam
- Phase Directory Key: company-operation-snapshot-seam
- Phase Title: Company Operation Snapshot Seam
- Scope: phase-local producer artifact

## Behaviors covered

- `list_task_operation_summaries(...)` publishes bounded task summaries with deterministic ordering, request excerpts, recent message excerpts, source paths, and per-task workflow telemetry.
- `write_company_operation_snapshot(...)` writes only under `ctx.workflow_folder`, normalizes task/workflow/status filters, packages bounded company-operation payloads, and leaves `.autoloop` state untouched.
- `docs/authoring.md` freezes the helper boundary as read-only, workflow-local, non-scoring, and non-executing.

## Preserved invariants checked

- Explicit `task_ids` remain in scope even when workflow/status filters produce zero matching runs.
- Without explicit `task_ids`, workflow/status filters narrow the snapshot to tasks with matching telemetry.
- Long recent messages are truncated to bounded excerpts rather than copied verbatim.
- Workflow-local path validation rejects escapes and non-`.json` outputs.

## Edge cases

- Empty filtered telemetry for explicitly requested tasks.
- Duplicate and whitespace-padded task/workflow/status filters.
- Mixed tasks where some selected workflows have zero runs in the scoped slice.

## Failure paths

- Invalid `task_ids`, `workflow_names`, and `statuses` entries.
- Non-positive `max_tasks`, `max_runs_per_workflow`, and `max_messages_per_task`.
- Helper path escape and wrong file-extension rejection.

## Known gaps

- No workflow-package runtime integration exists yet for `company_operation_to_recursive_improvement_cycle`; that downstream phase will need end-to-end publication tests against this seam.

## Validation

- `.venv/bin/pytest -q tests/runtime/test_workspace_and_context.py tests/unit/test_stdlib_and_extensions.py` -> `57 passed`
