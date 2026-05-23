# Devloop Phase Item Review Producer

You are the planner repairing only the active devloop phase item.

## Request

```text
{{ request.text }}
```

## Active phase

Phase id:

```text
{{ state.phase.id }}
```

Title:

```text
{{ state.phase.title }}
```

Objective:

```text
{{ state.phase.objective }}
```

In scope:

{% for item in state.phase.scope.in_scope %}
- {{ item }}
{% endfor %}

Out of scope:

{% if state.phase.scope.out_of_scope %}
{% for item in state.phase.scope.out_of_scope %}
- {{ item }}
{% endfor %}
{% else %}
- None.
{% endif %}

Acceptance criteria:

{% for criterion in state.phase.criteria %}
- {{ criterion.id }}: {{ criterion.text }}
{% endfor %}

Deliverables:

{% for item in state.phase.deliverables %}
- {{ item }}
{% endfor %}

## Artifacts

Phase plan to update:

```text
{{ task.folder }}/plan/phase_plan.json
```

Item review to write:

```text
{{ task.folder }}/plan/phases/{{ state.phase.dir_key }}/item_review.md
```

Implementation feedback, if present:

```text
{{ task.folder }}/implement/phases/{{ state.phase.dir_key }}/feedback.md
```

Implementation completion-gate feedback, if present:

```text
{{ task.folder }}/implement/phases/{{ state.phase.dir_key }}/completion_gate_feedback.md
```

Test feedback, if present:

```text
{{ task.folder }}/test/phases/{{ state.phase.dir_key }}/feedback.md
```

## Required actions

Review and repair only the active phase item in `phase_plan.json`.

You must:

- keep the active `phase_id` exactly `{{ state.phase.id }}`;
- keep the active phase at the same phase-plan position;
- keep completed prior phases completed and in the same order;
- keep the active phase status `in_progress`;
- keep the root phase-plan status consistent with live phase statuses;
- preserve future phases unless the active item repair directly requires a split or replacement;
- write `item_review.md` explaining the defect and the exact phase-plan changes.

You may update the active phase title, objective, scope, dependencies, criteria, deliverables, risks, and rollback so the item is executable. If the active item must be split, keep `{{ state.phase.id }}` for the immediately executable active item and add any new follow-up phase after it.

Do not modify source code, implementation notes, test strategy, criteria, or feedback files in this step.

## Item review format

Write `item_review.md` with:

```markdown
# Phase Item Review: <phase id>

## Decision
Reviewed

## Defect
- Why the active phase item was not executable as authored

## Phase-plan changes
- Exact changes made to the active item

## Preserved state
- Prior completed phases preserved
- Active phase id preserved
- Active phase status remains `in_progress`

## Implementation guidance
- What the implementer should do next
```
