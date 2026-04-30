# Incident Hardening Prompts

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
| `frame_incident` | `frame_producer.md` / `frame_verifier.md` | `incident_scope_brief`, `response_objectives`, `evidence_intake_register` | `incident_framed` |
| `assemble_evidence_pack` | `evidence_producer.md` / `evidence_verifier.md` | `incident_timeline`, `affected_surface`, `blast_radius`, `observability_gaps`, `evidence_gap_register` | `evidence_pack_ready` |
| `rank_cause_hypotheses` | `analysis_producer.md` / `analysis_verifier.md` | `cause_hypothesis_ranking`, `immediate_mitigation_plan`, `validation_plan`, `incident_summary` | `hypotheses_ranked` |
| `prepare_hardening_program` | `program_producer.md` / `program_verifier.md` | `hardening_program`, `hardening_backlog`, `follow_up_owners`, `stakeholder_communications_draft`, `incident_resolution_package` | `hardening_program_ready` |

## Route Surface

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `incident_framed`
- `evidence_pack_ready`
- `hypotheses_ranked`
- `hardening_program_ready`
- `needs_rework`
- `needs_replan`
- `incident_package_published`

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `frame_incident` | `IncidentFramingPayload` |
| `assemble_evidence_pack` | `IncidentEvidencePayload` |
| `rank_cause_hypotheses` | `IncidentHypothesisPayload` |
| `prepare_hardening_program` | `IncidentHardeningProgramPayload` |
