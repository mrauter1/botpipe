# Release Go/No-Go Prompts

## Shared README Boundary

- This README keeps the family-wide prompt contract in one place so individual prompt files can stay step-local.
- Prompt files still own the step role, purpose, current work-item boundary, exact artifact read/write set, and any evidence or route guidance that changes the local decision.
- Keep provider-facing operational guidance in prompt files, but keep repeated family-wide reminders here.
- The runtime injects a compact human-readable step contract with required inputs, writable artifacts, route-specific required writes, expected output payload requirements, available routes, route metadata, optional route handoff, and optional retry feedback.
- Provider raw output is runtime telemetry. It is persisted for logs, traces, extension events, debugging, and replay, but it is not rendered into provider prompts.
- Provider prose is control metadata unless it is written into a declared artifact.
- Verifier prompts return one JSON object through the selected route and step payload; they do not mutate artifacts unless the step contract says otherwise.

## Keep In Each Prompt

- role and step name
- step purpose and current work-item boundary
- exact artifacts to read, write, or leave untouched
- step-specific evidence requirements, route reminders, and forbidden actions

## Step Surface

| Step | Prompt pair | Writes | Step-complete route |
| --- | --- | --- | --- |
| `frame_release` | `frame_producer.md` / `frame_verifier.md` | `release_scope_brief`, `decision_criteria`, `evidence_intake_register` | `release_framed` |
| `assemble_evidence_pack` | `evidence_producer.md` / `evidence_verifier.md` | `release_inventory`, `test_evidence_pack`, `operational_readiness`, `rollback_readiness`, `blocking_issues` | `evidence_pack_ready` |
| `assess_go_no_go` | `assessment_producer.md` / `assessment_verifier.md` | `go_no_go_assessment`, `risk_register`, `decision_summary` | `assessment_ready` |
| `prepare_decision_package` | `package_producer.md` / `package_verifier.md` | `release_decision_package`, `release_communications_draft` | `decision_package_ready` |

## Route Surface

Helper routes:

- `question` when provider questions are allowed by the interaction policy
- question routes use `outcome.route_fields.questions`; blocked and failed routes use nullable `outcome.route_fields.reason`

Application routes:

- `inputs_prepared`
- `release_framed`
- `evidence_pack_ready`
- `assessment_ready`
- `decision_package_ready`
- `needs_rework`
- `needs_replan`
- `decision_published`

Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `frame_release` | `ReleaseFramingPayload` |
| `assemble_evidence_pack` | `ReleaseEvidencePayload` |
| `assess_go_no_go` | `ReleaseAssessmentPayload` |
| `prepare_decision_package` | `ReleaseDecisionPackagePayload` |
