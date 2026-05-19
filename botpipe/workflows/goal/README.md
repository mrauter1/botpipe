# Goal workflow

`goal` is a packaged Botpipe workflow inspired by Codex CLI `/goal`.

It gives a Botpipe task a durable target that can be viewed, paused,
resumed, or cleared across multiple runs that use the same task id. This maps
Codex's active thread goal to Botpipe's task scope.

The workflow name is `goal`; `/goal` is the command-style message handled by the
workflow.

## Commands

```bash
# Set or replace the active goal for a task.
botpipe run goal "/goal Finish the migration and keep tests green" \
  --task migration \
  --workspace . \
  --no-git

# View the current goal attached to the task.
botpipe run goal "/goal" --task migration --workspace . --no-git

# Pause, resume, or clear the task goal.
botpipe run goal "/goal pause" --task migration --workspace . --no-git
botpipe run goal "/goal resume" --task migration --workspace . --no-git
botpipe run goal "/goal clear" --task migration --workspace . --no-git
```

The workflow also accepts the objective without the slash-command prefix:

```bash
botpipe run goal "Finish the migration and keep tests green" --task migration --no-git
```

## Artifacts

The durable goal state is written to:

```text
{{ task.folder }}/goal/goal.json
```

A human-readable status report is written to:

```text
{{ workflow.folder }}/goal_status.md
```

## Semantics

- `/goal <objective>` sets the active goal.
- `/goal` or `/goal status` views the current goal.
- `/goal pause` marks the current goal as paused.
- `/goal resume` marks the current goal as active again.
- `/goal clear` removes the current goal.
- Objectives must be non-empty and at most 4,000 characters.
- Reusing the same `--task` value is what keeps the goal attached to the same
  Botpipe task.
