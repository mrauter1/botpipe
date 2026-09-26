# Package an adapted execution plan

Convert the accepted analysis into a plan an operator can execute without reinterpretation.

- `adapted_execution_plan` gives ordered preparation and execution guidance, preserving invariant steps, permissions, decision points, verification, and stop conditions.
- `proposed_workflow_parameters.json` is one plain JSON object using only declared parameter names; use `{}` if none are needed.
- `adapted_execution_summary.json` contains `selected_workflow_name`, `selected_workflow_entry_step`, `selected_workflow_parameters_supported`, `proposed_parameter_keys`, `expected_downstream_artifacts`, `authoritative_artifacts`, `next_action`, and `ready_for_execution`.
- `adapted_execution_next_action` references `validated_workflow_parameters.json`, names prerequisites and the selected workflow entry point, and never claims execution occurred.

Keep the selected workflow and expected artifact set unchanged from analysis. Accept only when the plan, parameter object, summary, and handoff agree. Rework packaging defects; replan when analysis must change. Parameter validation and execution remain runtime or downstream responsibilities.
