# Investigate a workflow before proposing a change

Return a `DiagnosticAssessment` matching the injected schema. This is a
read-only investigation. Inspect the selected workflow's captured source only
under `analysis_source_root` (your workspace), never an authoritative absolute
path, and
the supplied run history to understand what the workflow is trying to achieve,
what actually happened, and where quality, accuracy, reliability, or efficiency
could improve. Choose only dimensions that matter to this workflow.

Assess the whole workflow and any individual steps that are relevant. It is
valid to mark a scope uncertain or not assessed when the evidence is
insufficient. Distinguish direct run observations, source inspection, and your
own inference in every evidence link. Cite exact observation IDs and captured
source paths only; do not invent executions, causes, counts, or measurements.

Create a concise, context-specific rubric for judging a later candidate. State
the evidence each criterion needs and what would falsify it. This assessment
and rubric will be frozen before candidate generation, so do not describe or
choose an implementation. The optional priority is a user preference, not a
preselected target. The supplied aggregates are descriptive and are not a
ranking.
