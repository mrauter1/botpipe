# `workflow_portfolio_to_operating_system` Prompts

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
| `frame_portfolio_governance` | `frame_producer.md` / `frame_verifier.md` | `portfolio_governance_brief`, `portfolio_decision_criteria` | `portfolio_governance_framed` |
| `analyze_portfolio_operating_model` | `analyze_producer.md` / `analyze_verifier.md` | `workflow_lifecycle_matrix`, `portfolio_gap_analysis`, `portfolio_change_candidates` | `portfolio_operating_model_analyzed` |
| `package_portfolio_operating_system` | `package_producer.md` / `package_verifier.md` | `workflow_portfolio_operating_system`, `portfolio_operating_summary`, `portfolio_next_actions` | `portfolio_operating_system_ready` |

## Route Surface

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

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `frame_portfolio_governance` | `PortfolioGovernanceFramingPayload` |
| `analyze_portfolio_operating_model` | `PortfolioOperatingModelPayload` |
| `package_portfolio_operating_system` | `PortfolioOperatingSystemPayload` |
