# `workflow_to_eval_suite` Prompts

- `frame_producer.md`: frames one selected workflow plus evaluation intent as an explicit evaluation-authoring problem.
- `frame_verifier.md`: checks that the evaluation target and acceptance dimensions are explicit enough for case and rubric design.
- `design_producer.md`: authors benchmark, edge, and adversarial case coverage plus the proposed eval-case manifest and rubric.
- `design_verifier.md`: checks that the case coverage, manifest, and rubric are coherent and packaging-ready.
- `package_producer.md`: packages the terminal eval-suite document, machine-readable summary, and next-action artifact.
- `package_verifier.md`: confirms the terminal suite package is aligned and ready for deterministic publication of the validated manifest and receipt.

## Step To Artifact Map

- `frame_evaluation_target` writes `evaluation_request_brief` and `evaluation_dimensions`.
- `design_eval_cases` writes `benchmark_case_matrix`, `edge_case_matrix`, `adversarial_case_matrix`, `eval_case_manifest`, and `eval_rubric`.
- `package_workflow_eval_suite` writes `workflow_eval_suite`, `workflow_eval_suite_summary`, and `workflow_eval_next_action`.

## Route Grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `selected_workflow_contract_captured`
- `evaluation_target_framed`
- `eval_cases_designed`
- `workflow_eval_suite_ready`
- `needs_rework`
- `needs_replan`
- `workflow_eval_suite_published`

## Verifier JSON Expectations

- `frame_verifier.md` returns `EvaluationTargetFramingPayload`.
- `design_verifier.md` returns `EvalCaseDesignPayload`.
- `package_verifier.md` returns `WorkflowEvalSuitePayload`.

## Runtime Boundary

Prompt templates carry the provider-facing operational guidance.
The runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`.
