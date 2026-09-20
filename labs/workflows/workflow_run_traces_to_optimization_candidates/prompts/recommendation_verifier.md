# Independently review the CandidateSet

Use the independent verifier session. Check the exact CandidateSet against evidence, baseline boundary, constraints, enabled kinds, total cap, relevance, risks, and falsifiable validation plans. Do not alter facts or candidates.

Write `workflow_optimization_candidate_review.json` with schema `botpipe.workflow_optimization.candidate_review/v2`. Reviewed IDs exactly equal CandidateSet order. Call `finalize_candidate_review_payload(draft)` to fill the content-derived review ID. Route `recommendations_reviewed` only when accepted with no errors; otherwise use `recommendation_rework` for a bounded repair.
