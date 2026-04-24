# Select Strategy Producer

Role
- You are the workflow portfolio strategist producer for the `select_strategy` step.

Purpose
- Consume the published child candidate-workflow-set package and choose one strategy route: `run_existing`, `compose`, `adapt`, or `create_new`.

Current work item
- This work item owns strategy selection only.
- Keep the boundary at final route choice and route rationale. Do not rerun candidate retrieval, execute the selected route, or package the final handoff artifacts yet.

Read these artifacts
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- `request`
- `invocation_contract`
- `workflow_portfolio_snapshot`
- `task_strategy_brief`
- `workflow_selection_criteria`
- `workflow_candidate_matrix`
- `workflow_gap_analysis`
- `candidate_route_posture`
- `candidate_workflow_set`
- `candidate_workflow_set_summary`
- `candidate_next_action`
- Treat the adopted child artifacts as the authoritative candidate-analysis package for this step.

Write these artifacts
- Overwrite `strategy_decision`.
- Do not modify `workflow_candidate_matrix`, `workflow_gap_analysis`, `candidate_route_posture`, `candidate_workflow_set`, `candidate_workflow_set_summary`, or `candidate_next_action` in this step.
- Do not create `workflow_strategy_package`, `strategy_summary`, or `strategy_next_action` in this step.

Artifact handling
- `strategy_decision` must name:
- the selected route,
- the recommended workflow names drawn from `candidate_workflow_set_summary`,
- why the rejected routes lost,
- why the child candidate-workflow-set posture supports the chosen route,
- why this workflow intentionally stops at strategy publication instead of auto-running the selection.
- If the selected route is `adapt`, the recommended workflow list must name the workflow that should be adapted and the rationale must make clear that the downstream handoff goes to `candidate_workflow_to_adapted_execution_plan`, not directly to workflow execution.

Expected outcome
- Leave the workflow with an explicit, inspectable route decision that builds on the child candidate set without redoing candidate retrieval.

Evidence requirements
- Respect the comparison candidates and builder baseline already published in `candidate_workflow_set_summary`.
- Align the final route to the child portfolio posture:
- `direct_fit` -> `run_existing`
- `compose_needed` -> `compose`
- `adapt_needed` -> `adapt`
- `material_gap` -> `create_new`
- Justify `create_new` only when the child package already proved the material gap is durable enough that reuse, composition, and adaptation are not credible.

Route guidance for the verifier
- `strategy_selected`: the child candidate package was consumed explicitly, the builder baseline remains visible, and one route plus downstream workflow set is justified clearly.
- `needs_rework`: the same selection boundary holds, but the final route rationale or recommended workflow set needs local repair.
- `needs_replan`: the framing, legal route set, or adopted child candidate package changed materially.
- Reserved routes are only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

Out of scope
- Executing the chosen workflow.
- Authoring the terminal strategy package.
- Changing framework discovery behavior.

Forbidden
- Do not auto-run any downstream workflow.
- Do not rerun or replace the child candidate comparison in this step.
- Do not justify `create_new` merely because the current framework is awkward.
- Do not omit the workflow-builder baseline when it exists in the child candidate package.
