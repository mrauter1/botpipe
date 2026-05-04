# Task To Workflow Strategy Prompts

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
| `frame_task` | `frame_producer.md` / `frame_verifier.md` | `task_strategy_brief`, `workflow_selection_criteria` | `task_framed` |
| `select_strategy` | `select_producer.md` / `select_verifier.md` | `strategy_decision` | `strategy_selected` |
| `package_strategy` | `package_producer.md` / `package_verifier.md` | `workflow_strategy_package`, `strategy_summary`, `strategy_next_action` | `strategy_package_ready` |

## Route Surface

Runtime control route:

- `question` when provider questions are allowed by the interaction policy

Application routes:

- `inputs_prepared`
- `portfolio_snapshotted`
- `task_framed`
- `candidate_workflow_set_built`
- `strategy_selected`
- `strategy_package_ready`
- `needs_rework`
- `needs_replan`
- `strategy_published`

If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `frame_task` | `TaskFramingPayload` |
| `select_strategy` | `StrategySelectionPayload` |
| `package_strategy` | `StrategyPackagePayload` |
