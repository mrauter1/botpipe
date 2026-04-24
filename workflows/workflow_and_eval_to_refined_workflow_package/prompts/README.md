# `workflow_and_eval_to_refined_workflow_package` Prompts

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
| `frame_refinement_request` | `frame_producer.md` / `frame_verifier.md` | `refinement_request_brief`, `refinement_acceptance_criteria` | `refinement_request_framed` |
| `design_refinement_plan` | `design_producer.md` / `design_verifier.md` | `refinement_strategy`, `workflow_change_plan`, `regression_guardrails` | `refinement_plan_designed` |
| `implement_refined_workflow` | `implement_producer.md` / `implement_verifier.md` | `candidate_workflow_surface`, `refinement_build_report`, `candidate_diff_summary` | `workflow_refinement_applied` |
| `evaluate_refined_workflow` | `evaluate_producer.md` / `evaluate_verifier.md` | `refinement_verification_report`, `evaluation_delta_report`, `promotion_record`, `rollback_plan` | `workflow_refinement_evaluated` |

## Route Surface

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `refinement_context_captured`
- `refinement_request_framed`
- `refinement_plan_designed`
- `workflow_refinement_applied`
- `workflow_refinement_evaluated`
- `workflow_refinement_published`
- `needs_rework`
- `needs_replan`

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `frame_refinement_request` | `RefinementRequestFramingPayload` |
| `design_refinement_plan` | `WorkflowRefinementPlanPayload` |
| `implement_refined_workflow` | `WorkflowRefinementBuildPayload` |
| `evaluate_refined_workflow` | `WorkflowRefinementEvaluationPayload` |
