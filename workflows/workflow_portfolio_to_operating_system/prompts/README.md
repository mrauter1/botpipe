# `workflow_portfolio_to_operating_system` Prompts

- `frame_producer.md`: frames the scoped workflow portfolio, sponsor pressure, and governance decision criteria.
- `frame_verifier.md`: checks that the governance scope and decision criteria are explicit enough for lifecycle analysis.
- `analyze_producer.md`: turns capability and run-health evidence into a lifecycle matrix, gap analysis, and change-candidate manifest.
- `analyze_verifier.md`: checks that the lifecycle recommendations and change candidates are evidence-backed and portfolio-wide.
- `package_producer.md`: publishes the operating-system governance package, machine-readable summary, and explicit next actions.
- `package_verifier.md`: confirms the terminal governance package is aligned, publication-ready, and still stops at governance publication.

## Step To Artifact Map

- `frame_portfolio_governance` writes `portfolio_governance_brief` and `portfolio_decision_criteria`.
- `analyze_portfolio_operating_model` writes `workflow_lifecycle_matrix`, `portfolio_gap_analysis`, and `portfolio_change_candidates`.
- `package_portfolio_operating_system` writes `workflow_portfolio_operating_system`, `portfolio_operating_summary`, and `portfolio_next_actions`.

## Route Grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `portfolio_context_captured`
- `portfolio_governance_framed`
- `portfolio_operating_model_analyzed`
- `portfolio_operating_system_ready`
- `needs_rework`
- `needs_replan`
- `portfolio_operating_system_published`

## Verifier JSON Expectations

- `frame_verifier.md` returns `PortfolioGovernanceFramingPayload`.
- `analyze_verifier.md` returns `PortfolioOperatingModelPayload`.
- `package_verifier.md` returns `PortfolioOperatingSystemPayload`.

## Runtime Boundary

Prompt templates carry the provider-facing operational guidance.
The runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`.
