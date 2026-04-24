# `company_operation_to_recursive_improvement_cycle` Prompts

- `frame_producer.md`: frames the scoped company-operation evidence, sponsor pressure, and recursive-improvement criteria.
- `frame_verifier.md`: checks that the company scope and recursive-improvement criteria are explicit enough for pressure analysis.
- `analyze_producer.md`: turns company-operation evidence into a pressure map, priority matrix, and machine-readable recursive-improvement candidate set.
- `analyze_verifier.md`: checks that the ranked recursive-improvement candidates are evidence-backed, scope-safe, and category-explicit.
- `package_producer.md`: publishes the recursive-improvement cycle package, machine-readable summary, and explicit next actions.
- `package_verifier.md`: confirms the cycle package is aligned, publication-ready, and still stops at publication rather than hidden downstream execution.

## Step To Artifact Map

- `frame_company_operation` writes `company_operation_brief` and `recursive_improvement_criteria`.
- `analyze_recursive_improvement_pressures` writes `company_pressure_map`, `recursive_improvement_priority_matrix`, and `recursive_improvement_candidates`.
- `package_recursive_improvement_cycle` writes `recursive_improvement_cycle`, `recursive_improvement_summary`, and `recursive_improvement_next_actions`.

## Route Grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `company_operation_context_captured`
- `company_operation_framed`
- `recursive_improvement_pressures_analyzed`
- `recursive_improvement_cycle_ready`
- `needs_rework`
- `needs_replan`
- `recursive_improvement_cycle_published`

## Verifier JSON Expectations

- `frame_verifier.md` returns `CompanyOperationFramingPayload`.
- `analyze_verifier.md` returns `RecursiveImprovementAnalysisPayload`.
- `package_verifier.md` returns `RecursiveImprovementCyclePayload`.

## Runtime Boundary

Prompt templates carry the provider-facing operational guidance.
The runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`.
