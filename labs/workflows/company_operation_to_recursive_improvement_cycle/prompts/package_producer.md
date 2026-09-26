# Publish the improvement cycle

Package the accepted priorities as a bounded set of owned next actions, not an automatic recursive loop.

- `recursive_improvement_cycle` explains scope, evidence, ranked candidates, sequencing, dependencies, review triggers, and stop conditions; name every candidate ID.
- `recursive_improvement_summary.json` contains `workflow_name`, `focus_task_ids`, `focus_workflows`, `candidate_ids`, `priority_item_ids`, `priority_categories`, `priority_category_counts`, `authoritative_artifacts`, `next_action`, `publication_boundary`, and `ready_for_publication`. The boundary is `recursive_improvement_publication_only`.
- `recursive_improvement_next_actions` assigns or requests ownership and states what evidence should be gathered before each follow-on decision.

Preserve scoped IDs, rankings, and categories exactly. Accept only when all artifacts agree and the actions can terminate when goals are met. Rework packaging drift; replan changed priorities. Do not execute recommendations or claim perpetual recursion is desirable.
