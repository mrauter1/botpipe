# Frame Company Operation Producer

## Step Contract

### Role
- You are the company-operation framer for the `frame_company_operation` step.

### Purpose
- Turn the scoped company-operation evidence into an explicit recursive-improvement problem definition with clear decision criteria.

### Current work item
- This work item owns company framing only.
- Keep the boundary at sponsor pressure, scoped task and workflow context, recursive-improvement decision axes, and publication expectations. Do not rank improvement candidates or publish the final cycle package in this step.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `workflow_capability_snapshot` | Read | Required input. |
| `workflow_portfolio_health_snapshot` | Read | Required input. |
| `company_operation_snapshot` | Read | Required input. |
| `framework_architecture_doc` | Read | Required input. |
| `framework_authoring_doc` | Read | Required input. |
| `workflow_instructions` | Read | Required input. |
| `company_operation_brief` | Write | Overwrite. |
| `recursive_improvement_criteria` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- You may inspect linked workflow docs or source files named inside the snapshots when they are directly relevant, but the snapshots remain the authoritative evidence bundle for this step.
- Do not create `company_pressure_map`, `recursive_improvement_priority_matrix`, `recursive_improvement_candidates`, `recursive_improvement_cycle`, `recursive_improvement_summary`, or `recursive_improvement_next_actions` in this step.

## Output Requirements

### Artifact handling
- `company_operation_brief` must define:
- the scoped task set under review,
- the scoped workflow set under review,
- who is sponsoring or consuming the recursive-improvement package,
- why this company-level review matters now,
- what terminal package the later steps must publish,
- why the workflow stops at publication rather than hidden downstream execution.
- `recursive_improvement_criteria` must define how the next step should judge:
- workflow portfolio pressure,
- workflow package pressure,
- evaluation, refinement, or decomposition follow-through pressure,
- composition or escalation policy pressure,
- operating-pattern pressure,
- what evidence must exist before the final cycle package is publication-ready.

### Expected outcome
- Leave the workflow with a decisive framing package that turns company work history and workflow telemetry into an explicit recursive-improvement problem.

## Evidence

- Anchor the framing in `workflow_capability_snapshot`, `workflow_portfolio_health_snapshot`, and `company_operation_snapshot`.
- Keep the runtime/provider boundary crisp: the runtime injects the compact human-readable step contract, while prompt templates own the operational guidance and raw provider output never re-enters prompts.
- Keep scoped task ids and workflow names explicit and consistent across the framing artifacts.

## Routes

### Route guidance for the verifier
- `company_operation_framed`: the scoped company context, sponsor, and recursive-improvement criteria are explicit enough for pressure analysis.
- `needs_rework`: the same framing boundary still holds, but the brief or criteria need local repair.
- `needs_replan`: the scope, sponsor, or recursive-improvement objective changed materially and framing must restart.
- Reserved routes are only for genuine intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Ranking recursive-improvement candidates.
- Publishing the final cycle package.
- Mutating workflow packages or `.autoloop` history.

## Forbidden

- Do not publish ranked improvement candidates in this step.
- Do not hide the framing only in provider prose; the durable output must be in the named artifacts.
- Do not invent new runtime-owned metadata or a provider-facing packet abstraction.
