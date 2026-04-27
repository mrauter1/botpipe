# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: implement
- Phase ID: engine-hooks-workflow-step
- Phase Directory Key: engine-hooks-workflow-step
- Phase Title: Engine Hooks And WorkflowStep
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [core/engine.py:_schedule_route_handoffs, core/engine.py:_execute_step] Lowered child-workflow nodes now compile as `kind="workflow"`, so route handoffs are no longer filtered out the way system steps were. Unlike provider steps, workflow steps never call `_matching_pending_handoffs(...)` or otherwise consume/inject those queued handoffs into `ctx.invoke_workflow(...)`. A route that hands off to a workflow step will now accumulate stale `PendingHandoff` entries, persist them into checkpoints, and never deliver the message to the child workflow. Minimal fix: centralize workflow-step handoff handling by either consuming workflow-targeted handoffs in the workflow-step execution path and threading the merged message into the child invocation, or keep `_schedule_route_handoffs(...)` dropping handoffs for `kind in {"system", "workflow"}` until workflow-step handoff delivery is explicitly implemented.
