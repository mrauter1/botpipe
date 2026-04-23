# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260423t173132-c3
- Pair: implement
- Phase ID: security-remediation-workflow-package
- Phase Directory Key: security-remediation-workflow-package
- Phase Title: Ship Security Remediation Workflow
- Scope: phase-local authoritative verifier artifact

## Findings

- `IMP-001` `blocking` `[workflows/security_finding_to_verified_remediation/workflow.py:320-333]` `SecurityFindingToVerifiedRemediation.on_compose_evidence_pack(...)` records `ready_for_downstream_assessment` from the child summary but never requires it to be `true` before emitting `evidence_pack_adopted`. Concrete failure scenario: the child workflow can successfully publish a gap-heavy evidence pack with `ready_for_downstream_assessment=false`; this parent will still advance into `assess_security_finding` and later remediation/closure steps even though the adopted evidence contract explicitly says the pack is not ready for downstream assessment. Minimal fix: gate `evidence_pack_adopted` on `ready_for_downstream_assessment is True` and stop or reroute when the child publishes a not-ready pack.

- `IMP-002` `blocking` `[workflows/security_finding_to_verified_remediation/workflow.py:274-280, workflows/investigation_request_to_evidence_pack/prompts/frame_producer.md:26-28, workflows/investigation_request_to_evidence_pack/prompts/evidence_producer.md:50-54]` The parent forwards `deployment_constraints` into the child workflow as `source_constraints`. The child building block interprets `source_constraints` as evidence-framing and evidence-gathering limits, not rollout/remediation constraints. Concrete failure scenario: an input like `Preserve emergency admin access during rollout.` is treated as a child evidence constraint, so the evidence-pack framing and gap analysis can misclassify rollout guidance as a restriction on what evidence may be gathered or proven. Minimal fix: stop mapping deployment constraints onto the child `source_constraints` channel; keep rollout/deployment constraints in the parent invocation and remediation steps, or add a separate child-side parameter only if true evidence-side constraints are needed.
