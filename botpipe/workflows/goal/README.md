# Goal workflow

`goal` is a packaged Botpipe workflow inspired by Codex CLI `/goal`.

It gives a Botpipe task a durable objective and then runs an executable goal
loop: plan a todo list, execute each todo item, verify each item, verify the
whole goal against acceptance criteria, and continue until the final verifier
accepts the goal or the runtime stops because of limits, failure, pause, or
operator intervention.

The workflow name is `goal`; `/goal` is the command-style message handled by the
workflow.

## Commands

```bash
# Set or replace the active goal for a task, then start execution.
botpipe run goal "/goal Finish the migration and keep tests green" \
  --task migration \
  --workspace .

# Add explicit acceptance criteria in the message body.
botpipe run goal $'/goal Finish the migration\nAcceptance Criteria:\n- tests pass\n- docs are updated' \
  --task migration \
  --workspace .

# View the current goal attached to the task.
botpipe run goal "/goal" --task migration --workspace . --no-git

# Pause, resume, or clear the task goal.
botpipe run goal "/goal pause" --task migration --workspace . --no-git
botpipe run goal "/goal resume" --task migration --workspace .
botpipe run goal "/goal clear" --task migration --workspace . --no-git
```

The workflow also accepts the objective without the slash-command prefix:

```bash
botpipe run goal "Finish the migration and keep tests green" --task migration
```

## Execution loop

When `/goal <objective>` or `/goal resume` routes to execution, Botpipe runs:

1. `configure`: parse the command and persist `goal.json`.
2. `plan`: provider creates `goal_plan.json`, a concrete todo list.
3. `plan` verifier: accepts the todo list or sends it back for rework.
4. `select_next_item`: deterministic Python step selects the next unfinished item.
5. `execute_item`: provider executes the current todo item in the workspace.
6. `execute_item` verifier: accepts the item or loops for rework.
7. `mark_item_done`: deterministic Python step marks the item done in `goal_plan.json`.
8. Repeat item selection until all todo items are done.
9. `verify_goal`: provider performs a final integration pass and writes evidence.
10. `verify_goal` verifier: accepts the full goal, or routes back to `plan` for more work.
11. `finalize_goal`: marks the durable goal state as `met`.

## Artifacts

The durable task-attached goal state is written to:

```text
{{ task.folder }}/goal/goal.json
```

The executable todo plan is written to:

```text
{{ workflow.folder }}/goal_plan.json
```

The currently selected item is written to:

```text
{{ workflow.folder }}/current_item.json
```

Human-readable status and verification artifacts are written to:

```text
{{ workflow.folder }}/goal_status.md
{{ workflow.folder }}/plan_review.md
{{ workflow.folder }}/items/{{ state.current_item_dir_key }}/implementation_review.md
{{ workflow.folder }}/goal_evidence.md
{{ workflow.folder }}/goal_review.md
```

## Semantics

- `/goal <objective>` sets the goal and starts execution.
- `/goal` or `/goal status` views the current goal without executing providers.
- `/goal pause` marks the current goal as paused without executing providers.
- `/goal resume` marks the current goal as active and starts execution.
- `/goal clear` removes the current goal without executing providers.
- Objectives must be non-empty and at most 4,000 characters.
- Explicit criteria can be supplied under a `Criteria:` or `Acceptance Criteria:` heading.
- If no criteria are supplied, the workflow uses default completion criteria.
- Reusing the same `--task` value keeps the goal attached to the same Botpipe task.
