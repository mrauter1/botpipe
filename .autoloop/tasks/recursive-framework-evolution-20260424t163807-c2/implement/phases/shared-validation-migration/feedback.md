# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260424t163807-c2
- Pair: implement
- Phase ID: shared-validation-migration
- Phase Directory Key: shared-validation-migration
- Phase Title: Migrate Older Domain Validation
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 | blocking
  - File/symbol: `workflows/release_candidate_to_go_no_go/workflow.py:on_publish_decision`, `workflows/incident_to_hardening_program/workflow.py:on_publish_incident_package`
  - The migration changed strict publish-time string validation into coercive validation by calling `require_non_empty_string(..., coerce=True)` for `decision_summary.json.recommended_decision`, `incident_summary.json.recommended_posture`, and `incident_summary.json.primary_hypothesis`.
  - Concrete regression: payloads like `{"recommended_decision": 1}` or `{"recommended_posture": 1, "primary_hypothesis": 2}` now publish successfully after coercion to strings, whereas the previous workflow-local logic rejected non-string values. That violates AC-2's requirement to preserve existing publication behavior and domain-specific publish invariants.
  - Minimal fix direction: keep the shared validation seam, but make these publication-only fields non-coercive (`coerce=False`) or use an equivalent shared non-coercing string helper for these symbols only.
