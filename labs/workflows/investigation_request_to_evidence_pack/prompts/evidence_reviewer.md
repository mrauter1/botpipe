## Independent review result

Read the producer's typed result and immutable artifacts. Return one JSON result matching the injected review schema. Use `accepted` when the evidence meets the positive phase condition, `needs_rework` when this phase can repair it, `needs_replan` when accepted upstream work must change, `question` or `blocked` for missing prerequisites, and `failed` for a terminal defect. Record concise `validation_findings` and cite only captured artifact names. Do not reconstruct or restate the producer's domain fields.

# Assemble Evidence Pack Reviewer

## Evidence

- Verify the declared phase artifacts—`evidence_pack`, `source_register`, `evidence_gaps`, `investigation_summary`—against the phase requirements and require their claims to be internally consistent.
- Check the pack against the declared investigation objectives and source constraints, not against implied downstream work.
- Treat missing source inventory, coverage mapping, or explicit gap tracking as real defects in the durable handoff.
- Keep the route decision anchored to the artifact set rather than to plausible prose-only explanations.

## Phase decision criteria

- Mark the phase `blocked` only when a true intent gap or missing hard constraint prevents safe progress.
- Treat question, blocked, and failure guidance as semantic validation criteria.

### Outcome selection rules
- Choose `accepted` only if `source_register` traces inspected sources, `evidence_pack` covers the declared objectives and findings, `evidence_gaps` records unresolved gaps, and `investigation_summary` is consistent with those artifacts.
- Choose `needs_rework` when the same evidence boundary still holds and the pack can be strengthened locally.
- Choose `needs_replan` when the investigation boundary or evidence plan changed materially enough that framing must be revisited.
- Use `question` only for genuine missing prerequisites or irrecoverable contradictions.

## Forbidden

- Do not accept hand-wavy source summaries or a pack that omits source inventory, coverage mapping, or explicit gaps.
- Do not ignore source-constraint violations or machine-readable summary drift.
- Do not turn a framing problem into a local evidence rework decision.
