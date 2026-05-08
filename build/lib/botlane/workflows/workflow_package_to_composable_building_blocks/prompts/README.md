# `workflow_package_to_composable_building_blocks` Prompts

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
| `frame_decomposition_request` | `frame_producer.md` / `frame_verifier.md` | `decomposition_request_brief`, `decomposition_acceptance_criteria` | `decomposition_request_framed` |
| `design_decomposition_plan` | `design_producer.md` / `design_verifier.md` | `extraction_strategy`, `building_block_interface_contracts`, `parent_rewrite_plan`, `regression_guardrails` | `decomposition_plan_designed` |
| `implement_candidate_decomposition` | `implement_producer.md` / `implement_verifier.md` | `candidate_decomposition_surface`, `candidate_building_block_index`, `decomposition_build_report`, `candidate_diff_summary` | `candidate_decomposition_built` |
| `evaluate_candidate_decomposition` | `evaluate_producer.md` / `evaluate_verifier.md` | `decomposition_verification_report`, `composition_migration_guide`, `promotion_record`, `rollback_plan` | `candidate_decomposition_evaluated` |

## Route Surface

Helper routes:

- `question` when provider questions are allowed by the interaction policy
- question routes use `outcome.route_fields.questions`; blocked and failed routes use nullable `outcome.route_fields.reason`

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

Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `frame_decomposition_request` | `DecompositionRequestFramingPayload` |
| `design_decomposition_plan` | `DecompositionPlanPayload` |
| `implement_candidate_decomposition` | `CandidateDecompositionBuildPayload` |
| `evaluate_candidate_decomposition` | `CandidateDecompositionEvaluationPayload` |
