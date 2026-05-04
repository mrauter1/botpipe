# Package Improvement Pressure Producer

## Step Contract

### Role
- You are the improvement strategist for the `package_improvement_pressure` step.

### Purpose
- Turn the mapped failure modes and recurring weak points into a ranked improvement package, a machine-readable summary, and explicit next actions that stop at diagnostic publication.

### Current work item
- This work item owns improvement packaging only.
- Keep the boundary at ranked opportunities, explicit next actions, and the terminal diagnostic package for this building block.
- Do not auto-run refinement, portfolio governance, or selected-workflow execution in this step.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `selected_workflow_capability` | Read | Required input. |
| `selected_workflow_run_history` | Read | Required input. |
| `failure_mode_diagnostic_checklist` | Read | Required input. |
| `diagnostic_scope_brief` | Read | Required input. |
| `run_history_scope` | Read | Required input. |
| `failure_mode_map` | Read | Required input. |
| `failure_mode_manifest` | Read | Required input. |
| `recurring_weak_points` | Read | Required input. |
| `improvement_opportunities` | Write | Overwrite. |
| `improvement_opportunities_summary` | Write | Overwrite. |
| `diagnostic_next_actions` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Do not create `failure_mode_diagnostic_receipt.json` in this step.

## Output Requirements

### Artifact handling
- `improvement_opportunities` must rank the concrete opportunities by priority, link them to the failure modes they address, and explain expected impact.
- `improvement_opportunities_summary` must be valid JSON and define:
- `selected_workflow_name`,
- `evidence_run_ids`,
- `failure_mode_ids`,
- `ranked_opportunity_ids`,
- `opportunities` with objects that include `opportunity_id`, `title`, `priority`, `linked_failure_mode_ids`, `recommended_next_step`, `why_now`, and `expected_impact`,
- `authoritative_artifacts`,
- `next_action`,
- `publication_boundary` with the exact value `diagnostic_publication_only`,
- `ready_for_publication`,
- `workflow_name`.
- `diagnostic_next_actions` must state that this workflow stops at diagnostic publication and recommend explicit downstream options without implying hidden runtime execution.

### Expected outcome
- Leave the workflow with a publication-ready improvement package that another operator or workflow can consume without re-reading the raw run history.

## Evidence

- Rank opportunities from the mapped failure modes and recurring weak points, not from generic best practices.
- Tie every opportunity to explicit failure-mode IDs and evidence-backed leverage.
- Keep the boundary explicit: this workflow publishes diagnostics and next actions only.

## Routes

- Treat `question` as the only default runtime control route; use it only when a true intent gap or missing hard constraint blocks safe progress.
- If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

### Route guidance for the verifier
- `improvement_pressure_packaged`: the ranked package, machine-readable summary, and next-action artifact are aligned and ready for publication.
- `needs_rework`: the same packaging boundary still holds, but the package artifacts need local repair.
- `needs_replan`: the ranked package no longer matches the mapped failure surface and the workflow must revisit failure-mode mapping.
- Treat `question` as the only default runtime control route; use it only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Executing the next workflow.
- Mutating the selected workflow package.
- Writing the publication receipt.

## Forbidden

- Do not create `failure_mode_diagnostic_receipt.json` in this step.
- Do not imply automatic downstream execution.
- Do not replace explicit artifacts with prose-only recommendations.
