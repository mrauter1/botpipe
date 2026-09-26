# Analyze improvement pressure

Find the smallest evidence-backed set of changes likely to improve company operation. No category needs an item merely to look complete.

- `company_pressure_map` connects observed run patterns to operational consequences and confidence.
- `recursive_improvement_priority_matrix` records each stable `candidate_id`, legal category, `P1`/`P2`/`P3` priority, evidence, expected leverage, dependencies, and uncertainty.
- `recursive_improvement_candidates.json` has an `improvement_candidates` array. Each entry includes `candidate_id`, `category`, `priority`, `title`, `why_now`, `evidence_sources`, `next_step_hint`, and scoped `workflow_names`, `task_ids`, or both.
- Categories are `workflow_portfolio`, `workflow_package`, `evaluation_follow_through`, `refinement_follow_through`, `decomposition_follow_through`, `composition_or_escalation_policy`, and `operating_pattern`.

Use only scoped catalog and run-history evidence; do not infer causality from frequency alone. Accept when priorities are discriminating and traceable. Rework weak analysis locally; replan a changed scope. Do not mutate packages or launch follow-on workflows.
