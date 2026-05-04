# `workflow_to_eval_suite` Prompts

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
| `frame_evaluation_target` | `frame_producer.md` / `frame_verifier.md` | `evaluation_request_brief`, `evaluation_dimensions` | `evaluation_target_framed` |
| `design_eval_cases` | `design_producer.md` / `design_verifier.md` | `benchmark_case_matrix`, `edge_case_matrix`, `adversarial_case_matrix`, `eval_case_manifest`, `eval_rubric` | `eval_cases_designed` |
| `package_workflow_eval_suite` | `package_producer.md` / `package_verifier.md` | `workflow_eval_suite`, `workflow_eval_suite_summary`, `workflow_eval_next_action` | `workflow_eval_suite_ready` |

## Route Surface

Runtime control route:

- `question` when provider questions are allowed by the interaction policy

Application routes:

- `inputs_prepared`
- `selected_workflow_contract_captured`
- `evaluation_target_framed`
- `eval_cases_designed`
- `workflow_eval_suite_ready`
- `needs_rework`
- `needs_replan`
- `workflow_eval_suite_published`

If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `frame_evaluation_target` | `EvaluationTargetFramingPayload` |
| `design_eval_cases` | `EvalCaseDesignPayload` |
| `package_workflow_eval_suite` | `WorkflowEvalSuitePayload` |
