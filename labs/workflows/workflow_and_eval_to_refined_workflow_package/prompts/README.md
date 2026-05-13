# `workflow_and_eval_to_refined_workflow_package` Prompts

## Shared README Boundary

- This README keeps the family-wide prompt contract in one place so individual prompt files can stay step-local.
- Prompt files still own the step role, purpose, current work-item boundary, exact artifact read/write set, and any evidence or route guidance that changes the local decision.
- Keep provider-facing operational guidance in prompt files, but keep repeated family-wide reminders here.
- The runtime injects a compact human-readable step contract with required inputs, writable artifacts, route-specific required writes, expected output payload requirements, available routes, route metadata, optional route handoff, and optional retry feedback.
- Provider raw output is runtime telemetry. It is persisted for logs, traces, extension events, debugging, and replay, but it is not rendered into provider prompts.
- Provider prose is control metadata unless it is written into a declared artifact.
- Verifier prompts return one JSON object through the selected route and step payload; they do not mutate artifacts unless the step contract says otherwise.
- When `baseline_refinement_evidence.md` is present, treat optimization candidates as candidate-only input rather than proof of improvement.
- `optimization_ablation_results` are stronger evidence than candidate estimates when both exist.
- Token optimization ideas must preserve semantics before any later materialization.
- `adversarial_case_candidates` should usually feed `workflow_to_eval_suite`; this workflow does not auto-materialize them.

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

Helper routes:

- `question` when provider questions are allowed by the interaction policy
- question routes use `outcome.route_fields.questions`; blocked and failed routes use nullable `outcome.route_fields.reason`

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

Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `frame_refinement_request` | `RefinementRequestFramingPayload` |
| `design_refinement_plan` | `WorkflowRefinementPlanPayload` |
| `implement_refined_workflow` | `WorkflowRefinementBuildPayload` |
| `evaluate_refined_workflow` | `WorkflowRefinementEvaluationPayload` |
