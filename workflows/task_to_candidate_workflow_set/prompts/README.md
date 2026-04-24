# `task_to_candidate_workflow_set` Prompts

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
| `frame_candidate_request` | `frame_producer.md` / `frame_verifier.md` | `candidate_request_brief`, `candidate_selection_criteria` | `candidate_request_framed` |
| `analyze_candidate_workflows` | `analyze_producer.md` / `analyze_verifier.md` | `workflow_candidate_matrix`, `workflow_gap_analysis`, `candidate_route_posture` | `candidate_workflows_analyzed` |
| `package_candidate_workflow_set` | `package_producer.md` / `package_verifier.md` | `candidate_workflow_set`, `candidate_workflow_set_summary`, `candidate_next_action` | `candidate_workflow_set_ready` |

## Route Surface

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `workflow_capabilities_captured`
- `candidate_request_framed`
- `candidate_workflows_analyzed`
- `candidate_workflow_set_ready`
- `needs_rework`
- `needs_replan`
- `candidate_workflow_set_published`

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `frame_candidate_request` | `CandidateRequestFramingPayload` |
| `analyze_candidate_workflows` | `CandidateWorkflowAnalysisPayload` |
| `package_candidate_workflow_set` | `CandidateWorkflowSetPayload` |
