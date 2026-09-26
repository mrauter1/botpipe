# Select a workflow strategy

Choose one route—`run_existing`, `compose`, `adapt`, or `create_new`—from the accepted framing and child candidate set. Record the decision in `strategy_decision`, then return the injected typed result.

## Decision work

- Use only recommended workflows from the child candidate set.
- Explain how each recommended workflow contributes and why the rejected routes are weaker against the stated criteria.
- Treat the child posture as evidence, not an automatic lookup table: resolve contradictions explicitly and replan if they invalidate the comparison.
- Choose `create_new` only for a demonstrated material capability or control gap.
- For `adapt`, identify the workflow to adapt and hand off to `candidate_workflow_to_adapted_execution_plan`.

## Completion and exceptions

Accept when one route is supported by traceable evidence and its remaining uncertainty is visible. Rework a weak rationale locally; replan when the task framing or candidate set must materially change. Ask or block only on a prerequisite that could reverse the selection. This phase decides; it does not execute or package the route.
