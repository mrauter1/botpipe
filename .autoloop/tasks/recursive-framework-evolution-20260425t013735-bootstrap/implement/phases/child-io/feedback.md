# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: implement
- Phase ID: child-io
- Phase Directory Key: child-io
- Phase Title: Typed Child Workflow IO
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` — `runtime/workspace.py:resolve_run_workflow_input`, `runtime/workspace.py:create_run`, `runtime/runner.py:_execute_compiled_workflow`
  The new typed child-input path is broken on every fresh run. `create_run(...)` writes `run.json` without `workflow_input`, then `_execute_compiled_workflow(...)` immediately calls `resolve_run_workflow_input(...)`. Because `run.json` already exists, that helper reads the missing field and returns `None` instead of the caller-supplied payload, so the child workflow never receives its typed input. Any workflow that uses the new contract and reads `ctx.input` will fail at runtime on first execution, which violates AC-15 directly. Minimal fix: make the new-run persistence path symmetric with `workflow_params` by either writing `workflow_input` during `create_run(...)` or making `resolve_run_workflow_input(...)` fall back to the passed-in payload when the stored field is absent; keep that fallback centralized in `runtime/workspace.py` so run-start and resume semantics cannot drift.
