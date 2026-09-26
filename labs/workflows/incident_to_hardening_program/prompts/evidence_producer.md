# Assemble incident evidence

Build the factual basis for mitigation and cause analysis.

Treat captured declared-evidence artifacts as the stable baseline. If legitimate live discovery adds evidence, identify it as newly observed and record when and where it was inspected; never silently substitute it for an unavailable declaration.

- `incident_timeline` records source-linked events, time basis, confidence, and gaps; do not force uncertain events into a false total order.
- `affected_surface` distinguishes confirmed, suspected, and ruled-out components or users.
- `blast_radius` explains impact dimensions, estimates, assumptions, and confidence.
- `observability_gaps` names blind spots and how they constrain claims.
- `evidence_gap_register` prioritizes missing proof by response consequence and states how to obtain it.

Return impacted surfaces and unresolved gaps in the typed result. Accept when later hypotheses can be tested against this pack. Rework traceability or coverage defects; replan a materially changed incident boundary. Never invent telemetry or equate missing signals with no impact.
