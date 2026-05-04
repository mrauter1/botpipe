# Package Portfolio Operating System Producer

## Step Contract

### Role
- You are the portfolio operating-system packager for the `package_portfolio_operating_system` step.

### Purpose
- Turn the lifecycle analysis into a terminal governance package, a machine-readable summary, and explicit next actions that stop at operating-system publication.

### Current work item
- This work item owns governance packaging only.
- Keep the boundary at publication-ready governance artifacts and explicit next actions. Do not execute downstream workflows in this step.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `workflow_capability_snapshot` | Read | Required input. |
| `workflow_portfolio_health_snapshot` | Read | Required input. |
| `portfolio_operating_system_checklist` | Read | Required input. |
| `portfolio_governance_brief` | Read | Required input. |
| `portfolio_decision_criteria` | Read | Required input. |
| `workflow_lifecycle_matrix` | Read | Required input. |
| `portfolio_gap_analysis` | Read | Required input. |
| `portfolio_change_candidates` | Read | Required input. |
| `workflow_portfolio_operating_system` | Write | Overwrite. |
| `portfolio_operating_summary` | Write | Overwrite. |
| `portfolio_next_actions` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Do not create `portfolio_operating_system_receipt.json` in this step.

## Output Requirements

### Artifact handling
- `workflow_portfolio_operating_system` must be markdown and include explicit sections for:
- `## Keep`
- `## Refine`
- `## Decompose`
- `## Merge`
- `## Retire`
- `## Create Next`
- plus an explicit handoff boundary that states `operating_system_publication_only`.
- `portfolio_operating_summary` must be valid JSON and define:
- `focus_workflows`,
- `analyzed_workflows`,
- `lifecycle_recommendations`,
- `governance_posture_counts`,
- `change_candidate_ids`,
- `priority_workflows`,
- `authoritative_artifacts`,
- `next_action`,
- `publication_boundary` with the exact value `operating_system_publication_only`,
- `ready_for_publication`,
- `workflow_name`.
- `portfolio_next_actions` must make the next human or workflow handoff explicit while keeping the boundary at recommendations only.

### Expected outcome
- Leave the workflow with a publication-ready governance package that another operator or workflow can consume without re-reading the raw portfolio evidence.

## Evidence

- Keep the package aligned with `workflow_lifecycle_matrix` and `portfolio_change_candidates`.
- Make create-next, merge, and retire decisions explicit even when the answer is "none this cycle".
- Keep the boundary explicit: this workflow publishes governance and next actions only.

## Routes

- Treat `question` as the only default runtime control route; use it only when a true intent gap or missing hard constraint blocks safe progress.
- If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

### Route guidance for the verifier
- `portfolio_operating_system_ready`: the governance package, JSON summary, and next-actions artifact are aligned and ready for deterministic publication.
- `needs_rework`: the same packaging boundary still holds, but one or more packaging artifacts need local repair.
- `needs_replan`: the package no longer matches the analyzed operating model and lifecycle analysis must be revisited.
- Treat `question` as the only default runtime control route; use it only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Executing the next workflow.
- Mutating workflow packages.
- Writing the publication receipt.

## Forbidden

- Do not create `portfolio_operating_system_receipt.json` in this step.
- Do not imply automatic downstream execution.
- Do not replace explicit artifacts with prose-only recommendations.
