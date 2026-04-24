# `workflow_package_to_composable_building_blocks` Prompts

- `frame_producer.md`: frames one selected workflow plus decomposition evidence as an explicit extraction request.
- `frame_verifier.md`: checks that the decomposition boundary and acceptance surface are explicit enough for planning.
- `design_producer.md`: designs the extraction strategy, building-block interfaces, parent rewrite plan, and regression guardrails.
- `design_verifier.md`: checks that the decomposition plan is concrete, bounded, and still candidate-only.
- `implement_producer.md`: builds the candidate decomposition surface and declared building-block index without mutating the authoritative selected workflow package.
- `implement_verifier.md`: checks that the candidate surface and build artifacts are explicit enough for deterministic manifest derivation and evaluation.
- `evaluate_producer.md`: writes the decomposition verification report, migration guide, promotion record, and rollback plan.
- `evaluate_verifier.md`: checks that the evaluation package is publication-ready and still stops before promotion.

## Step To Artifact Map

- `frame_decomposition_request` writes `decomposition_request_brief` and `decomposition_acceptance_criteria`.
- `design_decomposition_plan` writes `extraction_strategy`, `building_block_interface_contracts`, `parent_rewrite_plan`, and `regression_guardrails`.
- `implement_candidate_decomposition` writes `candidate_decomposition_surface`, `candidate_building_block_index`, `decomposition_build_report`, and `candidate_diff_summary`.
- `implement_candidate_decomposition` also leads to deterministic publication of `candidate_decomposition_manifest.json` from the candidate surface and declared building-block index after verification.
- `evaluate_candidate_decomposition` writes `decomposition_verification_report`, `composition_migration_guide`, `promotion_record`, and `rollback_plan`.

## Route Grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `decomposition_context_captured`
- `decomposition_request_framed`
- `decomposition_plan_designed`
- `candidate_decomposition_built`
- `candidate_decomposition_evaluated`
- `candidate_decomposition_published`
- `needs_rework`
- `needs_replan`

## Verifier JSON Expectations

- `frame_verifier.md` returns `DecompositionRequestFramingPayload`.
- `design_verifier.md` returns `DecompositionPlanPayload`.
- `implement_verifier.md` returns `CandidateDecompositionBuildPayload`.
- `evaluate_verifier.md` returns `CandidateDecompositionEvaluationPayload`.

## Runtime Boundary

Prompt templates carry the provider-facing operational guidance.
The runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`.
