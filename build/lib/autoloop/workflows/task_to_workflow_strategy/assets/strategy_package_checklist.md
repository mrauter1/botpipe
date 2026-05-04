# Strategy Package Checklist

- Confirm the strategy package compares at least three candidate workflows or building blocks and names the builder baseline explicitly.
- Confirm the selected route is one of `run_existing`, `compose`, `adapt`, or `create_new`, and that the route matches the durable decision artifacts.
- Confirm `create_new` is justified only by a material fit gap, not by framework awkwardness or missing local effort.
- Confirm the package names the recommended workflows and explains why the rejected routes lost.
- Confirm `strategy_summary.json` includes `selected_strategy`, `recommended_workflows`, `comparison_candidates`, `builder_baseline_workflow`, `builder_considered`, `create_new_required`, `authoritative_artifacts`, `rejected_routes`, `next_action`, and `ready_for_handoff`.
- Confirm that when `selected_strategy` is `adapt`, the package and `strategy_next_action.md` explicitly point to `candidate_workflow_to_adapted_execution_plan` without adding new summary fields.
- Confirm `strategy_next_action.md` tells the next operator exactly what should happen next without implying the downstream workflow already ran.
- Confirm the terminal output is a strategy package and receipt only; no hidden downstream execution should occur in this workflow.
