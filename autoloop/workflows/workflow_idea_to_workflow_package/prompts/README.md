# Workflow Builder Prompts

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
| `frame_candidate` | `frame_producer.md` / `frame_verifier.md` | `candidate_comparison`, `selected_workflow_brief` | `candidate_selected` |
| `design_package` | `design_producer.md` / `design_verifier.md` | `workflow_package_spec`, `step_contracts`, `prompt_contract_matrix`, `verification_plan` | `design_accepted` |
| `build_package` | `build_producer.md` / `build_verifier.md` | `generated_package_root`, `generated_single_file`, `generated_flow`, `generated_specs`, `generated_init`, `generated_manifest`, `generated_prompts_dir`, `generated_assets_dir`, `generated_prompt_index`, `generated_layout`, `generated_doc`, `generated_test`, `build_report` | `package_built` |
| `evaluate_package` | `evaluate_producer.md` / `evaluate_verifier.md` | `verification_report`, `promotion_record`, `rollback_plan` | `evaluation_passed` |

## Route Surface

Helper routes:

- `question` when provider questions are allowed by the interaction policy
- question routes use `outcome.route_fields.questions`; blocked and failed routes use nullable `outcome.route_fields.reason`

Application routes:

- `candidate_selected`
- `design_accepted`
- `package_built`
- `evaluation_passed`
- `needs_rework`
- `needs_replan`
- `package_published`

Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `frame_candidate` | `CandidateSelectionPayload` |
| `design_package` | `WorkflowDesignPayload` |
| `build_package` | `WorkflowBuildPayload` |
| `evaluate_package` | `WorkflowEvaluationPayload` |
