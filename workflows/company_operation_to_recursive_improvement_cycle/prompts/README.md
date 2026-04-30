# `company_operation_to_recursive_improvement_cycle` Prompts

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
| `frame_company_operation` | `frame_producer.md` / `frame_verifier.md` | `company_operation_brief`, `recursive_improvement_criteria` | `company_operation_framed` |
| `analyze_recursive_improvement_pressures` | `analyze_producer.md` / `analyze_verifier.md` | `company_pressure_map`, `recursive_improvement_priority_matrix`, `recursive_improvement_candidates` | `recursive_improvement_pressures_analyzed` |
| `package_recursive_improvement_cycle` | `package_producer.md` / `package_verifier.md` | `recursive_improvement_cycle`, `recursive_improvement_summary`, `recursive_improvement_next_actions` | `recursive_improvement_cycle_ready` |

## Route Surface

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `company_operation_context_captured`
- `company_operation_framed`
- `recursive_improvement_pressures_analyzed`
- `recursive_improvement_cycle_ready`
- `needs_rework`
- `needs_replan`
- `recursive_improvement_cycle_published`

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `frame_company_operation` | `CompanyOperationFramingPayload` |
| `analyze_recursive_improvement_pressures` | `RecursiveImprovementAnalysisPayload` |
| `package_recursive_improvement_cycle` | `RecursiveImprovementCyclePayload` |
