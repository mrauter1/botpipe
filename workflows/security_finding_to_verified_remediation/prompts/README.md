# Security Remediation Prompts

## Shared README Boundary

- This README keeps the family-wide prompt contract in one place so individual prompt files can stay step-local.
- Prompt files still own the step role, purpose, current work-item boundary, exact artifact read/write set, and any evidence or route guidance that changes the local decision.
- Keep provider-facing operational guidance in prompt files, but keep repeated family-wide reminders here.
- The runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`.
- Provider prose is control metadata unless it is written into a declared artifact.
- `compose_evidence_pack` is explicit child-workflow composition with no prompt files in this package; it must stay workflow-owned and deterministic.
- Verifier prompts return one JSON object through the selected route and step payload; they do not mutate artifacts unless the step contract says otherwise.

## Keep In Each Prompt

- role and step name
- step purpose and current work-item boundary
- exact artifacts to read, write, or leave untouched
- step-specific evidence requirements, route reminders, and forbidden actions

## Step Surface

| Step | Prompt pair | Writes | Step-complete route |
| --- | --- | --- | --- |
| `compose_evidence_pack` | `System step (no prompt files)` | `finding_scope_brief`, `security_evidence_pack`, `security_evidence_pack_summary`, `security_evidence_gap_register`, `security_evidence_pack_receipt` | `evidence_pack_adopted` |
| `assess_security_finding` | `assessment_producer.md` / `assessment_verifier.md` | `exploit_summary`, `affected_surface`, `root_cause_analysis`, `remediation_options`, `assessment_summary` | `finding_assessed` |
| `plan_verified_remediation` | `remediation_producer.md` / `remediation_verifier.md` | `selected_remediation_plan`, `verification_plan`, `rollout_plan`, `rollback_safety_plan`, `remediation_summary` | `remediation_planned` |
| `prepare_closure_package` | `closure_producer.md` / `closure_verifier.md` | `security_remediation_package`, `stakeholder_communication_draft`, `closure_evidence_requirements` | `closure_package_ready` |

## Route Surface

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `evidence_pack_adopted`
- `finding_assessed`
- `remediation_planned`
- `closure_package_ready`
- `needs_rework`
- `needs_replan`
- `remediation_published`

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `assess_security_finding` | `SecurityAssessmentPayload` |
| `plan_verified_remediation` | `VerifiedRemediationPayload` |
| `prepare_closure_package` | `SecurityClosurePackagePayload` |
