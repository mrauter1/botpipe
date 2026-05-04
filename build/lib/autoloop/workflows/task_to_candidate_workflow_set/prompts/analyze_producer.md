# Analyze Candidate Workflows Producer

## Step Contract

### Role
- You are the workflow candidate-analysis producer for the `analyze_candidate_workflows` step.

### Purpose
- Compare the current task against the existing workflow portfolio, rank the strongest workflow candidates, and explain whether the portfolio posture is a direct fit, a composition need, an adaptation candidate, or a material gap.

### Current work item
- This work item owns candidate comparison and fit-gap analysis only.
- Keep the boundary at ranking candidates and explaining the current portfolio posture. Do not choose the final front-door strategy route or package the terminal handoff artifacts yet.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `workflow_capability_snapshot` | Read | Required input. |
| `candidate_request_brief` | Read | Required input. |
| `candidate_selection_criteria` | Read | Required input. |
| `workflow_candidate_matrix` | Write | Overwrite. |
| `workflow_gap_analysis` | Write | Overwrite. |
| `candidate_route_posture` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Inspect linked workflow docs or source files referenced inside `workflow_capability_snapshot` when they materially strengthen or challenge the fit analysis.
- Do not create `candidate_workflow_set`, `candidate_workflow_set_summary`, or `candidate_next_action` in this step.

## Output Requirements

### Artifact handling
- `workflow_candidate_matrix` must compare at least three candidate workflows when the portfolio size permits and include for each:
- workflow or building-block name,
- what job it solves,
- fit to this task,
- key gaps,
- why it wins or loses,
- whether it looks like a direct fit, composition ingredient, adaptation candidate, or builder pressure.
- Include `workflow_idea_to_workflow_package` as the builder baseline unless it is genuinely absent from `workflow_capability_snapshot`. If it is absent, record that absence explicitly as a portfolio gap.
- Treat `task_to_workflow_strategy` and `task_to_candidate_workflow_set` as portfolio infrastructure, not downstream winners, unless the task is itself about workflow routing or workflow-candidate-set infrastructure.
- `workflow_gap_analysis` must explain whether the current portfolio fits directly, needs composition, needs adaptation, or has a material gap that should later pressure `create_new`.
- `candidate_route_posture` must name:
- the ranked candidates,
- the current portfolio posture (`direct_fit`, `compose_needed`, `adapt_needed`, or `material_gap`),
- why the posture is credible,
- what the downstream strategy selector should decide next.

### Expected outcome
- Leave the workflow with an explicit, inspectable ranked candidate set and a portfolio-posture artifact another workflow can package for downstream strategy selection without adding hidden runtime logic.

## Evidence

- Compare at least three candidates when the portfolio size permits.
- Explicitly include the builder baseline in the comparison when it exists.
- Make the posture explicit enough that a downstream strategy workflow can turn it into a final route without redoing candidate retrieval.

## Routes

- Treat `question` as the only default runtime control route; use it only when a true intent gap or missing hard constraint blocks safe progress.
- If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

### Route guidance for the verifier
- `candidate_workflows_analyzed`: the comparison is explicit, the builder baseline was considered, and the portfolio posture is justified clearly.
- `needs_rework`: the same analysis boundary holds, but the matrix, gap analysis, or posture explanation needs local repair.
- `needs_replan`: the framing, legal comparison boundary, or portfolio posture changed materially.
- Treat `question` as the only default runtime control route; use it only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Choosing the final `run_existing` / `compose` / `adapt` / `create_new` route.
- Executing any downstream workflow.
- Packaging the terminal candidate-workflow-set handoff.

## Forbidden

- Do not auto-run any downstream workflow.
- Do not justify a material gap merely because the current framework is awkward.
- Do not omit the workflow-builder baseline when it exists in the capability snapshot.
