# `workflow_and_eval_to_refined_workflow_package` Prompts

- `frame_producer.md`: frames one selected workflow plus baseline evaluation evidence as an explicit refinement request.
- `frame_verifier.md`: checks that the refinement boundary and acceptance surface are explicit enough for file-level change planning.
- `design_producer.md`: designs the refinement strategy, workflow change plan, and regression guardrails.
- `design_verifier.md`: checks that the change plan is concrete, scoped, and evidence-driven.
- `implement_producer.md`: builds the candidate workflow surface and the supporting build artifacts without mutating the authoritative selected workflow.
- `implement_verifier.md`: checks that the candidate surface and build artifacts are explicit enough for evaluation.
- `evaluate_producer.md`: writes the refinement verification report, evaluation delta, promotion record, and rollback plan.
- `evaluate_verifier.md`: checks that the evaluation package is publication-ready and still stops before promotion.

## Step To Artifact Map

- `frame_refinement_request` writes `refinement_request_brief` and `refinement_acceptance_criteria`.
- `design_refinement_plan` writes `refinement_strategy`, `workflow_change_plan`, and `regression_guardrails`.
- `implement_refined_workflow` writes `candidate_workflow_surface`, `refinement_build_report`, and `candidate_diff_summary`.
- `implement_refined_workflow` also leads to deterministic publication of `candidate_workflow_manifest.json` from the candidate surface after verification.
- `evaluate_refined_workflow` writes `refinement_verification_report`, `evaluation_delta_report`, `promotion_record`, and `rollback_plan`.

## Route Grammar

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

## Verifier JSON Expectations

- `frame_verifier.md` returns `RefinementRequestFramingPayload`.
- `design_verifier.md` returns `WorkflowRefinementPlanPayload`.
- `implement_verifier.md` returns `WorkflowRefinementBuildPayload`.
- `evaluate_verifier.md` returns `WorkflowRefinementEvaluationPayload`.

## Runtime Boundary

Prompt templates carry the provider-facing operational guidance.
The runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`.
