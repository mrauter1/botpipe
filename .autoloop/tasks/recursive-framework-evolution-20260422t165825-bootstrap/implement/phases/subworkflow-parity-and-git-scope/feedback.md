# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: implement
- Phase ID: subworkflow-parity-and-git-scope
- Phase Directory Key: subworkflow-parity-and-git-scope
- Phase Title: Subworkflow Parity And Git Scope
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | `runtime.runner._build_workflow_invoker`, `runtime.runner._prepare_workspaces`, `runtime.workspace.ensure_workspace`
  Child invocation currently routes the child `message` through the same task-level request update path used for top-level runs. Repro: running the new class-based child fixture leaves `.autoloop/tasks/<task>/request.md` set to the child text (`"Run child from class\n"`) and appends that internal child message to `messages.jsonl`, replacing the shared task snapshot that other workflows are supposed to read via `{task_folder}/request.md`. This violates the task/workflow/run separation in the approved layout and can change parent or sibling workflow behavior mid-task. Minimal fix: centralize an opt-out for nested child runs in the workspace/runner path so `ctx.invoke_workflow(...)` creates only the child run-local `request.md` and does not mutate task-level `request.md` or `messages.jsonl`.

- IMP-002 | non-blocking | `runtime.runner._child_run_record_payload`, `runtime.runner._execute_compiled_workflow`
  Parent-side `children.jsonl` records are not shape-stable across outcomes. Success/pause child records are emitted via `_child_run_record_payload(...)` with absolute path fields plus `last_event`, while the fatal-error path writes a hand-built payload with repo-relative paths and no `package_folder` / `last_event`. That makes future readers branch on outcome type just to parse one metadata file. Minimal fix: route fatal child-record emission through the same serializer used for non-fatal child runs, extending that helper with optional error details instead of duplicating a second schema.
