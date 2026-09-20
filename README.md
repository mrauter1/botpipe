# Botpipe

Botpipe runs ordinary Python functions as durable agent workflows. The function
owns control flow; Botpipe records provider calls, activities, nested workflows,
human input, artifacts, and their outcomes so a resumed run reuses completed
work.

> **Invariant:** Python owns control flow. Every material observation or external
> effect goes through a recorded Botpipe operation.

## Install

Botpipe requires Python 3.12 or newer.

```bash
pip install -e .
```

The default provider is Codex CLI. Select a different installed provider with
`Botpipe(provider=...)`, `--provider`, or `botpipe.toml`.

## A real workflow

The packaged Ralph loop is ordinary Python. This is its current workflow body;
the prompt constants and typed review contract live beside it in the same
module.

```python
from botpipe import Artifact, Botpipe, Session, Worklist, workflow
from botpipe.workflows.ralph_loop.workflow import (
    IMPLEMENT,
    PLAN,
    REVIEW_IMPLEMENTATION,
    REVIEW_PLAN,
    ReviewDecision,
)


@workflow(name="ralph_loop", version="1")
def ralph_loop(request: str):
    work = Artifact.json("work.json", required=True)
    plan_review = Artifact.md("plan_review.md", required=True)
    planner = Session(key="planner")
    plan_reviewer = Session(key="plan-reviewer")
    feedback = ()

    while True:
        plan = planner.run(PLAN, input=request, reads=feedback, writes=(work,))
        review = plan_reviewer.run(
            REVIEW_PLAN,
            input=request,
            reads=(plan.artifacts.work,),
            writes=(plan_review,),
            returns=ReviewDecision,
        )
        if review.value.verdict == "accepted":
            break
        feedback = (review.artifacts.plan_review,)

    items = Worklist.from_artifact(plan.artifacts.work, collection="items")
    for item in items:
        session = Session.work_item(item)
        item_review = Artifact.md(
            f"items/{item.dir_key}/implementation_review.md",
            required=True,
        )
        feedback = ()
        while True:
            session.run(
                IMPLEMENT,
                input=item.payload,
                reads=(items.artifact, *feedback),
            )
            review = session.run(
                REVIEW_IMPLEMENTATION,
                input=item.payload,
                reads=(items.artifact,),
                writes=(item_review,),
                returns=ReviewDecision,
            )
            if review.value.verdict == "accepted":
                items.complete(item)
                break
            feedback = (review.artifacts.implementation_review,)

    return items.artifact


result = Botpipe(workspace=".").run(
    ralph_loop,
    "Add CSV export support and cover it with tests.",
    task_id="csv-export",
)
print(result.status, result.run_id)
```

Strings are inline prompts. `Prompt.file("review.md")` loads a file relative to
the workflow source. Jinja rendering is strict and receives the operation input
and run information.

## Command line

Workflow references may be catalog names, `package.module:function`, or
`path/to/file.py:function`.

```bash
botpipe workflows list --workspace .
botpipe workflows show my_package.flow:fix_issue --workspace .

botpipe run my_package.flow:fix_issue \
  --input '{"request":{"issue":"CSV export loses UTF-8 characters"}}' \
  --task-id csv-utf8 --workspace .

botpipe runs list --status awaiting_input --workspace .
botpipe runs show RUN_ID --workspace .
botpipe runs logs RUN_ID --workspace .
botpipe resume RUN_ID --answer 'yes' --workspace .

# An uncertain external effect is never retried silently.
botpipe resolve RUN_ID OPERATION_ID --retry --workspace .
# Or record the response that actually occurred, then resume.
botpipe resolve RUN_ID OPERATION_ID --response '{"id":"remote-42"}' --workspace .
```

The familiar plain request form remains available for a workflow whose first
parameter is a string:

```bash
botpipe run ralph_loop "Implement CSV export and test it" --workspace .
```

## Configuration

Botpipe reads `botpipe.toml`, `.botpipe.toml`, or `[tool.botpipe]` in
`pyproject.toml`. Explicit CLI options win.

```toml
provider = "codex"
max_operations = 500
timeout = 1800

[provider_config]
command = ["codex", "exec"]

[policy]
model = "gpt-5.5"
effort = "high"
sandbox_mode = "workspace_write"
network = "none"
```

Provider policies describe intended and enforceable access. A provider must
reject controls it cannot honor; Botpipe does not turn a prompt instruction into
a security boundary.

## Durable behavior

- `@workflow` wraps sync or async functions. Calling another decorated workflow
  creates a durable child scope.
- `Session.run()` records a provider operation. The same mutable session is
  serialized; use separate sessions for parallel work.
- `@activity` records custom Python I/O. Interrupted unsafe activities stop for
  explicit operator reconciliation.
- `ask()` records a typed human-input request. Resume with an answer.
- `parallel()` gives every callable a stable independent scope and preserves
  result order.
- Completed operation results are immutable. Resume checks workflow source,
  prompt, schema, and operation identity before replay.
- Botpipe provides durable replay, not an exactly-once claim for external
  systems.

See [Authoring](docs/authoring.md), [SDK](docs/sdk.md),
[Architecture](docs/architecture.md), [CLI](docs/cli.md), and the
[major-version migration guide](docs/migration.md).

## Development

```bash
python -m pytest -q
```

Botpipe is licensed under Apache-2.0.
