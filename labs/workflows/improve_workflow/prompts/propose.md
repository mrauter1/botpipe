# Propose one bounded workflow experiment

Return a `Proposal` that matches the injected schema. This is a read-only
analysis step: do not edit source, evidence, manifests, or journal state. Inspect
source only under the supplied `analysis_source_root`, which is the frozen model
workspace.

Treat `evidence` and the frozen `assessment` as immutable. The assessment owns
the workflow intent, semantic classifications, uncertainties, and evaluation
rubric; do not move those goalposts to favor a candidate. Treat
`baseline_surface_manifest` as the exact editable boundary. Propose at most one
change idea. Keep every target inside that boundary and use repository-relative
paths.

Investigate the assessment coherently instead of treating descriptive metrics
as a target ranking. A trace-backed candidate may cite only focused observation
IDs from the selected evidence group. A source-backed opportunity may honestly
use an empty observation citation list and names its exact captured paths in
`source_evidence_paths`. Those paths must already support the frozen assessment;
the candidate must not claim an observed failure.

The expected effect is a hypothesis. Do not claim measured improvement. Make
the change concrete, name its risks, and include a validation plan tied to the
frozen rubric with useful checks and a falsification condition. Prefer the
smallest reversible experiment that addresses the most relevant diagnosis and
the user's request.

An empty proposal is valid when the investigation cannot support a safe or
useful experiment; use `collect_evidence` or `no_change` and give a specific `reason`.
For a change idea use `implement_candidate` and a null reason. The runtime owns
candidate classification, content IDs, evidence anchors, and publication
metadata; do not return any of those fields.

When `review_feedback` is present, revise the prior idea only to address those
findings. Preserve the frozen assessment, rubric, valid evidence links, and
baseline boundary.
