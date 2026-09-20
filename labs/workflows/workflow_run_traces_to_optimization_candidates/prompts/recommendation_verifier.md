# Independently review the CandidateSet

Use the independent verifier session. Check the exact CandidateSet against evidence, baseline boundary, constraints, enabled kinds, total cap, relevance, risks, and falsifiable validation plans. Do not alter facts or candidates.

Write `workflow_optimization_candidate_review.json`. Build the exact draft below without `review_id`, then call `finalize_candidate_review_payload(draft)` and serialize with `model_dump(mode="json", by_alias=True)`:

```json
{"schema":"botpipe.workflow_optimization.candidate_review/v2","candidate_set_id":"<copy>","evidence_snapshot_id":"<copy>","baseline_surface_manifest_id":"<copy>","accepted":true,"reviewed_candidate_ids":["<every candidate_id in exact CandidateSet order>"],"findings":[{"candidate_id":"<copied candidate_id>","severity":"warning","message":"<specific finding>"}]}
```

`severity` is `error`, `warning`, or `note`. Use an empty findings array when there are none. Route `recommendations_reviewed` only when accepted with no errors; otherwise use `recommendation_rework` for a bounded repair.
