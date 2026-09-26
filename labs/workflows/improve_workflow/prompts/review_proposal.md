# Independently review one workflow improvement proposal

Return a `ChangeReview` that matches the injected schema. Review the exact
`candidate_set` without editing it or any source, evidence, manifest, or
journal state.

Inspect source only under the supplied `analysis_source_root`, which is the
frozen model workspace.

Check that the frozen assessment distinguishes observation, source inspection,
and inference, and that its chosen rubric fits the workflow's intent. Then check
that every candidate:

- addresses a relevant assessed failure or opportunity and the user's request;
- preserves the frozen rubric and acknowledges material uncertainty;
- cites only focused observations in the selected group when it claims trace
  support, while allowing no observation citation for an honest source-only
  opportunity whose exact `source_evidence_paths` already support the frozen
  assessment;
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
