{% if state.review is none %}
## Missing legacy review assignment

This verifier was resumed from a persisted checkpoint that has no runtime review assignment. Do not inspect, evaluate, or accept the candidate. Write exactly this strict JSON object to the stage review-report path specified above:

```json
{
  "review_id": "unassigned",
  "criteria": [],
  "findings": [
    {
      "verdict": "failed",
      "evidence": ["Persisted checkpoint has no current runtime review request."],
      "reason": "A fresh producer/verifier execution is required."
    }
  ],
  "summary": "Review assignment unavailable; rerun this stage."
}
```

Write JSON only: no markdown fence, comments, YAML, extra fields, or trailing prose. This is a diagnostic rejection and cannot accept the candidate. If the provider response schema also requires a route, select the stage's ordinary repair or rework route. Do not request phase-item repair. The runtime will reject the missing assignment, record the completion-gate diagnostic, and rerun the producer/verifier pair with a fresh assignment even if the provider erroneously reports success.

{% else %}
## Runtime review contract

The runtime created this review assignment:

- Review id: `{{ state.review.id }}`
- Step: `{{ state.review.step }}`
- Phase id: {% if state.review.phase_id is not none %}`{{ state.review.phase_id }}`{% else %}`null`{% endif %}

Authoritative criteria:

{% for criterion in state.review.criteria %}
- `{{ criterion.id }}`: {{ criterion.text }}
{% endfor %}

Write one strict JSON object with this shape:

```json
{
  "review_id": {{ state.review.id | tojson }},
  "criteria": [
{% for criterion in state.review.criteria %}
    {
      "id": {{ criterion.id | tojson }},
      "verdict": "passed",
      "evidence": ["Specific observed evidence."],
      "reason": "Why the evidence supports this verdict."
    }{% if not loop.last %},{% endif %}
{% endfor %}
  ],
  "findings": [],
  "summary": "",
  "repair_target": "candidate"
}
```

Contract rules:

- `review_id` must exactly equal `{{ state.review.id }}`. It identifies this candidate review and must not be copied from an earlier candidate attempt.
- `criteria` must contain every authoritative criterion id above exactly once, with no missing, duplicate, or additional ids.
- Each criterion `verdict` must be `passed`, `failed`, or `blocked`.
- Each criterion must have a `reason`. A passed criterion must have non-empty, concrete `evidence`, and its reason must explain how that evidence establishes the criterion.
- Use `failed` when inspected evidence shows the candidate does not satisfy a criterion. Use `blocked` when necessary evidence is unavailable or the criterion cannot be assessed; report the uncertainty instead of guessing.
- `findings` may be empty. Each finding uses `{ "verdict", "evidence", "reason" }` with the same verdict values and a non-empty reason; passed findings also require non-empty evidence. Use passed findings only for useful information outside the criteria. Any failed or blocked finding prevents acceptance even when every criterion passed.
- `summary` is free-form and may be empty. Do not add a top-level verdict or route decision; the runtime derives the outcome from criteria and findings.
- `repair_target` is optional and defaults to `candidate`. Its only other allowed value is `phase_item`, which is valid only for an implementation review with a failed criterion or finding when the authored active phase item itself requires repair. Do not use `phase_item` for a passed or blocked report, an ordinary implementation defect, or any other review step.
- Evidence must name concrete files, values, observations, diffs, or command results. Do not use the criterion text itself as evidence.
- When an automated check is required and applicable, run it and cite its actual result or relevant output. Do not invent a command requirement where the task or stage has none. If a required check cannot run, report that uncertainty as blocked.
- On rework, inspect the changed candidate and provide new evidence from the new review. Do not copy an earlier report's conclusions as evidence.
- Use only the report fields shown above. Write JSON only: no markdown fence, comments, YAML, or trailing prose.

Do not modify the candidate or producer-owned artifacts in this verifier step. Your only write is the review report specified above.
{% endif %}
