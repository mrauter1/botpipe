# Package the selected strategy

Publish the accepted route without reopening the comparison. On acceptance, write the declared artifacts and return the injected typed result.

## Deliverables

- `workflow_strategy_package` explains the task, evidence considered, selected route, recommended workflows, rejected alternatives, assumptions, and handoff.
- `strategy_summary.json` contains `selected_strategy`, `recommended_workflows`, `comparison_candidates`, `builder_baseline_workflow`, `builder_considered`, `create_new_required`, `authoritative_artifacts`, `rejected_routes`, `next_action`, and `ready_for_handoff`.
- `strategy_next_action` names the next operator or workflow, inputs to carry forward, prerequisites, and the evidence that will show completion.
- For `adapt`, the next action invokes `candidate_workflow_to_adapted_execution_plan` with the chosen workflow and current task facts.

Preserve the accepted selection and child candidate facts exactly. Candidate breadth should reflect real alternatives in the catalog; never pad the comparison. Accept only when the prose, JSON, and next action agree. Rework packaging defects locally; replan if packaging exposes a changed selection. Do not execute the selected route or imply that it ran.
