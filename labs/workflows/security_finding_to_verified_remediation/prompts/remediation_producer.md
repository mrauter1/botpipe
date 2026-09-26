# Plan verified remediation

Choose a remediation that restores the required security property and can be deployed within the stated constraints.

- `remediation_plan` compares viable options, selects one, describes the change surface, dependencies, least-privilege and compatibility concerns, rollout stages, monitoring, rollback, and explicit stop conditions.
- `verification_evidence` defines pre-fix reproduction where safe, post-fix negative and regression tests, control inspection, operational observation, and required approvals. Distinguish planned proof from evidence already obtained.
- `residual_risk.json` contains `authoritative_artifacts`, `selected_remediation`, `verification_ready`, `rollout_ready`, and `summary` consistent with the artifacts.

Readiness is true only when prerequisites for the next activity are satisfied; it is not proof that remediation is complete. Accept a safe, testable plan; rework local defects; replan when assessment or selected approach must change. Do not prescribe destructive validation, expose secrets, or silently waive deployment constraints.
