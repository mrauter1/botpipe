# Adapted Execution Plan Checklist

- Confirm the selected workflow remains explicit and matches the selected-workflow capability snapshot.
- Confirm the adaptation request brief names the trigger, sponsor, terminal outcome, and why adaptation planning is the current work item.
- Confirm the success criteria define what stays fixed, what may be parameterized, and which downstream artifacts matter.
- Confirm the workflow fit assessment explains why the selected workflow still fits and what execution risks remain.
- Confirm the step adaptation matrix reflects the selected workflow's real step surface rather than inventing a new topology.
- Confirm `proposed_workflow_parameters.json` is a plain JSON object keyed by actual selected-workflow parameter names, or `{}` when the workflow declares no parameters.
- Confirm `adapted_execution_summary.json` includes the selected workflow name, entry step, parameter-support flag, proposed parameter keys, expected downstream artifacts, authoritative artifacts, next action, and `ready_for_execution`.
- Confirm `authoritative_artifacts` names `adapted_execution_plan`, `adapted_execution_summary`, `adapted_execution_next_action`, and `validated_workflow_parameters`.
- Confirm `adapted_execution_next_action.md` references `validated_workflow_parameters.json` by name and does not imply the downstream workflow already ran.
- Confirm the package stops at plan publication and does not mutate or auto-run the selected workflow.
