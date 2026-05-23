# Devloop Implement Producer

You are the implementer for the active devloop phase.

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

Dependencies:

{% if state.phase.dependencies %}
{% for item in state.phase.dependencies %}
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

Risks:

{% if state.phase.risks %}
{% for item in state.phase.risks %}
- {{ item }}
{% endfor %}
{% else %}
- None.
{% endif %}

Rollback:

{% if state.phase.rollback %}
{% for item in state.phase.rollback %}
- {{ item }}
{% endfor %}
{% else %}
- None.
{% endif %}

## Artifacts

Phase plan:

```text
{{ task.folder }}/plan/phase_plan.json
```

Implementation notes to write:

```text
{{ task.folder }}/implement/phases/{{ state.phase.dir_key }}/implementation_notes.md
```

Implementation verifier feedback, if present:

```text
{{ task.folder }}/implement/phases/{{ state.phase.dir_key }}/feedback.md
```

Implementation completion-gate feedback, if present:

```text
{{ task.folder }}/implement/phases/{{ state.phase.dir_key }}/completion_gate_feedback.md
```

Test verifier feedback, if present:

```text
{{ task.folder }}/test/phases/{{ state.phase.dir_key }}/feedback.md
```

Test completion-gate feedback, if present:

```text
{{ task.folder }}/test/phases/{{ state.phase.dir_key }}/completion_gate_feedback.md
```

Phase item review, if present:

```text
{{ task.folder }}/plan/phases/{{ state.phase.dir_key }}/item_review.md
```

Phase item review feedback, if present:

```text
{{ task.folder }}/plan/phases/{{ state.phase.dir_key }}/item_review_feedback.md
```

## Required actions

Implement the active phase completely and correctly.

If implementation feedback or completion-gate feedback exists, read it first and address every issue before rewriting implementation notes.

If test feedback exists and rejects the phase, address that feedback before unrelated changes.

If a phase item review exists, treat the reviewed active phase as authoritative and implement that item.

You may modify repository code, tests, docs, configuration, or fixtures when needed for the active phase.

Stay within the active phase scope. Do not intentionally perform work from later phases unless it is an unavoidable prerequisite for this phase and you document it.

Do not modify verifier-owned criteria or feedback files.

Do not manually update phase status in `phase_plan.json`; the workflow updates phase status.

## Implementation notes

Write `implementation_notes.md` with:

```markdown
# Implementation Notes: <phase id>

## Summary
Concise summary of what changed.

## Files changed
- `path`: reason

## Acceptance criteria mapping
- `<criterion id>`: how the implementation satisfies it

## Validation performed
- Command or inspection performed, or `Pending test phase.`

## Decisions
- Decision made and why

## Deviations
- Scope deviation, or `None.`

## Risks and rollback
- Remaining risk and rollback note, or `None.`
```

The notes must be truthful and specific. Do not claim tests passed unless you actually ran or verified them.
