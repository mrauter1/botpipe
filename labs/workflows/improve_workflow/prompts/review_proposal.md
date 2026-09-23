# Independently review one workflow improvement proposal

Return a `ChangeReview` that matches the injected schema. Review the exact
`candidate_set` without editing it or any source, evidence, manifest, or
journal state.

Check that every candidate:

- addresses the ranked objective and user's request using admitted evidence;
- cites only focused observations in the selected evidence group;
- stays within the baseline surface and names real repository-relative targets;
- respects the one-candidate cap;
- describes a concrete change, plausible effect, material risks, and a
  falsifiable validation plan;
- avoids claims of measured improvement.

Accept only when the whole set is useful, evidence-bound, internally
consistent, and safe to hand to implementation. Give a concise `summary` and
put every issue requiring revision in `required_changes` with
`accepted: false`. An accepted review must have no required changes. For an
empty candidate set, accept it only when its next action and reason follow from
the evidence.

The runtime owns review IDs, copied anchors, reviewed candidate IDs, finding
severity, and publication metadata; do not return any of those fields.
