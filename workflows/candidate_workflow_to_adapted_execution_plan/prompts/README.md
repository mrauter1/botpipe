# `candidate_workflow_to_adapted_execution_plan` Prompts

## Shared README Boundary

- This README keeps the family-wide prompt contract in one place so individual prompt files can stay step-local.
- Prompt files still own the step role, purpose, current work-item boundary, exact artifact read/write set, and any evidence or route guidance that changes the local decision.
- Keep provider-facing operational guidance in prompt files, but keep repeated family-wide reminders here.
- The runtime injects a compact human-readable step contract with required inputs, writable artifacts, route-specific artifact requirements, expected output payload requirements, available routes, route contracts, optional route handoff, and optional retry feedback.
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
| `frame_adaptation_request` | `frame_producer.md` / `frame_verifier.md` | `adaptation_request_brief`, `adaptation_success_criteria` | `adaptation_request_framed` |
| `analyze_adaptation_surface` | `analyze_producer.md` / `analyze_verifier.md` | `workflow_fit_assessment`, `step_adaptation_matrix` | `adaptation_surface_analyzed` |
| `package_adapted_execution_plan` | `package_producer.md` / `package_verifier.md` | `adapted_execution_plan`, `proposed_workflow_parameters`, `adapted_execution_summary`, `adapted_execution_next_action` | `adapted_execution_plan_ready` |

## Route Surface

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `selected_workflow_contract_captured`
- `adaptation_request_framed`
- `adaptation_surface_analyzed`
- `adapted_execution_plan_ready`
- `needs_rework`
- `needs_replan`
- `adapted_execution_plan_published`

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `frame_adaptation_request` | `AdaptationRequestFramingPayload` |
| `analyze_adaptation_surface` | `AdaptationSurfaceAnalysisPayload` |
| `package_adapted_execution_plan` | `AdaptedExecutionPlanPayload` |
