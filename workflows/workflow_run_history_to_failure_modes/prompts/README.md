# `workflow_run_history_to_failure_modes` Prompts

## Shared README Boundary

- This README keeps the family-wide prompt contract in one place so individual prompt files can stay step-local.
- Prompt files still own the step role, purpose, current work-item boundary, exact artifact read/write set, and any evidence or route guidance that changes the local decision.
- Keep provider-facing operational guidance in prompt files, but keep repeated family-wide reminders here.
- The runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`.
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
| `frame_diagnostic_scope` | `frame_producer.md` / `frame_verifier.md` | `diagnostic_scope_brief`, `run_history_scope` | `diagnostic_scope_framed` |
| `map_failure_modes` | `analyze_producer.md` / `analyze_verifier.md` | `failure_mode_map`, `failure_mode_manifest`, `recurring_weak_points` | `failure_modes_mapped` |
| `package_improvement_pressure` | `package_producer.md` / `package_verifier.md` | `improvement_opportunities`, `improvement_opportunities_summary`, `diagnostic_next_actions` | `improvement_pressure_packaged` |

## Route Surface

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `run_history_context_captured`
- `diagnostic_scope_framed`
- `failure_modes_mapped`
- `improvement_pressure_packaged`
- `needs_rework`
- `needs_replan`
- `failure_mode_diagnostics_published`

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `frame_diagnostic_scope` | `DiagnosticScopePayload` |
| `map_failure_modes` | `FailureModeMapPayload` |
| `package_improvement_pressure` | `ImprovementPressurePayload` |
