# Devloop Prompts

These prompts belong to the packaged `devloop` workflow.

Devloop runs a phased software-delivery loop:

1. `plan`: produce and verify `phase_plan.json`.
2. `validate_plan_completion`: deterministically validates the plan JSON and plan checklist.
3. `activate_next_phase`: selects the next phase.
4. `implement`: implements the active phase.
5. `validate_implement_completion`: deterministically validates the implementation checklist.
6. `review_phase_item`: narrowly repairs the active phase-plan item when implementation proves it is not executable as authored.
7. `validate_phase_item_review`: deterministically validates the item review and refreshes active phase state.
8. `test`: validates the active phase.
9. `validate_test_completion`: deterministically validates the test checklist.
10. Repeat from `activate_next_phase` until all phases complete.

## Required phase-plan contract

The planner must write strict JSON to:

```text
{{ task.folder }}/plan/phase_plan.json
```

Do not write YAML. Do not write markdown. Do not wrap the JSON in a code fence.

Required top-level shape:

```json
{
  "version": 1,
  "task_id": "exact runtime task id",
  "request_snapshot_ref": "exact runtime request file path",
  "status": "planned",
  "phases": []
}
```

Each phase must include:

```json
{
  "phase_id": "p01-example",
  "title": "Short phase title",
  "objective": "What this phase accomplishes",
  "status": "planned",
  "scope": {
    "in_scope": ["Concrete included work"],
    "out_of_scope": ["Concrete excluded work"]
  },
  "dependencies": [],
  "criteria": [
    {
      "id": "AC-1",
      "text": "Acceptance criterion"
    }
  ],
  "deliverables": ["Concrete output"],
  "risks": ["Risk or empty list"],
  "rollback": ["Rollback action or empty list"]
}
```

Rules:

- `version` must be `1`.
- `task_id` must match the runtime task id.
- `request_snapshot_ref` must match the runtime request snapshot path.
- Initial root `status` should be `planned`.
- Initial executable phase `status` should be `planned`.
- `phase_id` must be unique, non-empty, no more than 96 UTF-8 bytes.
- Prefer path-safe phase ids such as `p01-frame`, `p02-implement-api`, `p03-tests`.
- If a dependency names another `phase_id`, that dependency must reference an earlier phase.
- Every phase must include at least one criterion and one deliverable.

## Checklist contract

Verifier prompts must write criteria files as markdown checklists.

A criteria file passes the deterministic completion gate only when it:

- exists;
- is not empty;
- contains at least one markdown checkbox;
- has every checkbox checked with `- [x]`.

Use unchecked boxes only when the route should repair or rework.

Valid accepted checklist example:

```markdown
# Plan Criteria

- [x] `phase_plan.json` is strict JSON.
- [x] All phases are ordered and dependency-safe.
- [x] The plan fully covers the request.
```

Invalid/incomplete checklist example:

```markdown
# Plan Criteria

- [x] `phase_plan.json` is strict JSON.
- [ ] The plan fully covers the request.
```

## Route discipline

The runtime injects the authoritative route and artifact contract. Use only routes available in the current step.

Prompt-level route intent:

- Plan verifier:
  - `plan_ready`: plan is valid and checklist is fully checked.
  - `needs_rework`: plan must be rewritten.
- Implement verifier:
  - `implemented`: active phase implementation is complete and checklist is fully checked.
  - `needs_rework`: current implementation or implementation evidence needs local rework.
  - `needs_phase_item_review`: active phase item is impossible, contradictory, missing required dependencies, mis-scoped, or cannot be executed without changing that item.
- Phase item review verifier:
  - `phase_item_reviewed`: active phase item was narrowly repaired and checklist is fully checked.
  - `needs_rework`: item review is incomplete, unsafe, or violates the live phase-plan contract.
- Test verifier:
  - `phase_passed`: active phase is validated and checklist is fully checked.
  - `needs_rework`: validation shows the implementation does not satisfy the active phase and must return to implementation.
