# Propose one evidence-bound workflow improvement

Return a `Proposal` that matches the injected schema. This is a read-only
analysis step: do not edit source, evidence, manifests, or journal state.

Treat `evidence_snapshot` as immutable fact and `baseline_surface_manifest` as
the exact editable boundary. Propose at most one change idea. Cite only focused
observation IDs from the selected evidence group. Keep every target inside the
baseline boundary and use repository-relative paths.

The expected effect is a hypothesis. Do not claim measured improvement. Make
the change concrete, name its risks, and include a validation plan with useful
checks and a falsification condition. Prefer the smallest change that directly
addresses the ranked evidence and the user's request.

An empty proposal is valid only when the evidence cannot support a safe
candidate; use `collect_evidence` or `no_change` and give a specific `reason`.
For a change idea use `implement_candidate` and a null reason. The runtime owns
candidate classification, content IDs, evidence anchors, and publication
metadata; do not return any of those fields.

When `review_feedback` is present, revise the prior idea only to address those
findings while preserving valid evidence citations and the baseline boundary.
