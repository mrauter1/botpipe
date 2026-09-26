# Package the evaluation suite

Publish the validated case design and rubric for later execution.

- `workflow_eval_suite` explains the target, evaluation dimensions, coverage rationale, known omissions, scoring process, and correct use of `validated_eval_case_manifest.json` and `eval_rubric.md`.
- `workflow_eval_suite_summary.json` contains `selected_workflow_name`, `selected_workflow_entry_step`, `selected_workflow_parameters_supported`, `case_count`, `case_ids`, `case_kinds`, `covered_expected_artifacts`, `authoritative_artifacts`, `next_action`, `ready_for_publication`, `evaluation_suite_id`, and `source_candidate_id`.
- `workflow_eval_next_action` names who should run the suite, prerequisites, how results should be recorded, and references the validated manifest and rubric by name.

Copy the validated manifest ordering, suite identity, and optimizer candidate identity exactly. Accept only when all artifacts agree. Rework packaging drift; replan when case design changed. Do not execute the workflow or claim improvement.
