# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: implement
- Phase ID: runtime-workspace-and-context
- Phase Directory Key: runtime-workspace-and-context
- Phase Title: Runtime Workspace And Context
- Scope: phase-local authoritative verifier artifact

- `IMP-001` | `blocking` | `runtime/runner.py:run_workflow`, `workflows/autoloop_v1/parity.py:run_autoloop_v1`, `runtime/workspace.py:update_run_metadata`
  The new `workflow_params` contract is not actually immutable across a run. Both runners pass `options.workflow_params or {}` into `update_run_metadata(...)` and the engine on every start/resume, so a run created with non-empty params will be silently rewritten to `{}` as soon as it is resumed without explicitly re-supplying params. Concrete failure: create a run with `workflow_params={"mode": "strict"}`, pause it, then resume with default `RunnerOptions(workflow_params=None)`; `run.json` is overwritten, `Context.workflow_params` becomes empty, and any parameter-sensitive workflow logic now sees the wrong state. Minimal fix: centralize resolved run params in one helper that loads persisted params from `run.json` for existing runs and only writes initial params on new run creation, then have both generic and Autoloop-v1 runners pass that resolved value through to metadata and engine/context construction.
