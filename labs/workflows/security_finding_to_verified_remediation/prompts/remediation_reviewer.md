## Independent review result

Read the producer's typed result and immutable artifacts. Return one JSON result matching the injected review schema. Use `accepted` when the evidence meets the positive phase condition, `needs_rework` when this phase can repair it, `needs_replan` when accepted upstream work must change, `question` or `blocked` for missing prerequisites, and `failed` for a terminal defect. Record concise `validation_findings` and cite only captured artifact names. Do not reconstruct or restate the producer's domain fields.

# Plan Verified Remediation Reviewer

## Evidence

- Verify the declared phase artifacts—`remediation_plan`, `verification_evidence`, `residual_risk`—against the phase requirements and require their claims to be internally consistent.
- Verify that the chosen remediation is justified against the compared options and the assessed exploit boundary.
- Treat drift between `residual_risk` and the durable plan artifacts as a real defect.
- Check declared deployment constraints and rollback safety as first-class proof obligations.

## Phase decision criteria

- Mark the phase `blocked` only when a true intent gap or missing hard constraint prevents safe progress.
- Treat question, blocked, and failure guidance as semantic validation criteria.

### Outcome selection rules
- Choose `accepted` only if `remediation_plan` justifies the choice and covers implementation, rollout, and rollback, `verification_evidence` defines concrete proof, and `residual_risk` reports a consistent selected remediation and readiness posture.
- Choose `needs_rework` when the same remediation-planning boundary still holds and the artifacts can be repaired locally.
- Choose `needs_replan` when the assessment conclusion or fix strategy changed materially enough that the security finding must be reassessed.
- Use `question` only for genuine missing prerequisites or irrecoverable contradictions.

## Forbidden

- Do not accept a remediation summary that drifts from the durable plan artifacts.
- Do not approve a rollout plan that ignores declared deployment constraints.
- Do not rewrite artifacts yourself.
