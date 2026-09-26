# Package the candidate set

Turn the accepted comparison into a clean strategy handoff. Preserve the analyzed candidates, ordering, posture, and builder-baseline facts.

- `candidate_workflow_set` explains the criteria, evidence, ranked candidates, gaps, uncertainties, and recommended candidates.
- `candidate_workflow_set_summary.json` contains `comparison_candidates`, `ranked_candidates`, `recommended_candidate_workflows`, `builder_baseline_workflow`, `builder_considered`, `portfolio_posture`, `authoritative_artifacts`, `next_action`, and `ready_for_strategy_selection`.
- `candidate_workflow_next_action` tells the strategy selector what decision remains and which assumptions or missing evidence matter.

Accept only when human and machine-readable artifacts agree and recommendations come from the ranking. Rework packaging drift locally; replan when the comparison itself must change. Stop at publication—do not select a final route or run candidates.
