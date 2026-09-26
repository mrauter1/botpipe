# Analyze the portfolio operating model

Assess current workflows against the accepted criteria and real evidence.

- `portfolio_health_analysis` explains coverage, overlap, reliability, demand, run-health limitations, and material gaps.
- `lifecycle_recommendations.json` gives every analyzed workflow exactly one legal posture (`keep`, `refine`, `decompose`, `merge`, or `retire`), a `P1`/`P2`/`P3` priority, rationale, and evidence.
- `portfolio_change_candidates.json` has `change_candidates`; each entry includes `candidate_id`, legal `action`, `priority`, `workflow_names`, `why_now`, `evidence_sources`, `next_step_hint`, and `proposed_workflow_name` for `create_next`.
- Recommend change only when its expected value and evidence exceed the cost and migration risk. A workflow with sparse usage is not automatically obsolete.

Accept when recommendations cover the analyzed set and change candidates are traceable. Rework local inconsistencies; replan a changed scope or criteria. Do not mutate, merge, or retire packages.
