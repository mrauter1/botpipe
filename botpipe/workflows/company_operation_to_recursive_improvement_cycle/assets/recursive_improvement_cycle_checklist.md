# Recursive Improvement Cycle Checklist

- Confirm `workflow_capability_snapshot.json`, `workflow_portfolio_health_snapshot.json`, and `company_operation_snapshot.json` all exist and agree on the scoped workflow set.
- Keep the workflow boundary at recursive-improvement publication only; recommendations may name downstream workflows, but this workflow must not execute them.
- Keep scoped task ids explicit from `company_operation_snapshot.json` through `recursive_improvement_summary.json`.
- Keep every `candidate_id` explicit in both `recursive_improvement_priority_matrix.md` and `recursive_improvement_cycle.md`.
- Keep workflow portfolio, workflow package, follow-through, composition/escalation policy, and operating-pattern pressure visible in the package where the evidence supports them.
- Ensure `recursive_improvement_summary.json` matches `recursive_improvement_candidates.json` without category-count drift.
- Keep `recursive_improvement_next_actions.md` explicit about the publication boundary and the exact next action another operator or workflow should take.
