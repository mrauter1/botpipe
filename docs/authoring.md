# Authoring workflows

A workflow is an ordinary sync or async Python function decorated with
`@workflow`.

```python
from botpipe import Session, ask, workflow


@workflow(name="release", version="2")
def release(version: str) -> str:
    review = Session.task("review").run(
        "Review this release candidate.", input={"version": version}
    )
    if review.value != "approved":
        reason = ask("Why should this release proceed?", returns=str)
        return f"held: {reason}"
    return "approved"
```

Use normal Python for decisions and loops. Do not model routes, transitions, or
mutable workflow state separately.

## Inputs and returns

Use annotations. Pydantic models, dataclasses, paths, and JSON-compatible
collections make the durable contract explicit. CLI invocation validates inputs
before a run starts.

```python
class Change(BaseModel):
    request: str
    test_command: str = "pytest -q"

@workflow
async def implement(change: Change) -> Report: ...
```

Changing a workflow's source or durable contract while a run is active causes a
version/source mismatch on resume. Start a new run for new behavior.

## Sessions

`Session()` creates a workflow-scoped conversation. `Session.task(key)` persists
continuity for a task, while `Session.work_item(item, key)` isolates continuity
per durable work item. `Session.fresh()` explicitly starts without prior provider
conversation.

```python
session = Session.task("implementation")
plan = session.run("Inspect the repository and make a plan.", returns=Plan)
done = session.run("Implement the plan and run its checks.", input=plan.value)
```

Provider operations on one mutable session are serialized. Give independent
parallel branches separate sessions.

## Prompts and effects

Plain strings are inline prompts. Use `Prompt.file(path)` for a source-controlled
prompt relative to the workflow file. Templates render with strict Jinja rules.

Declare provider-written outputs with `writes=` and material inputs with
`reads=`. Use `@activity` for other external I/O. This keeps replay honest: a
filesystem read, HTTP request, subprocess, random value, or clock value that can
change workflow behavior belongs behind an operation.

## Artifacts and worklists

```python
report = Artifact.md("reports/final.md", required=True)
result = Session.task().run("Write the final report.", writes=(report,))
print(result.artifacts.report.read_text())
```

Captured artifacts are immutable snapshots. `source_path` identifies the
provider destination; `path` identifies the durable snapshot.

`Worklist.from_artifact()` snapshots its selected items before iteration.
Resume uses that historical selection even if the live source later changes.
Completing an item produces a new logical artifact version.

## Nested and parallel work

Call a decorated workflow normally to create a durable child. Use
`parallel(lambda: ..., lambda: ...)` for independent work; results retain input
order. Shared-workspace parallel sessions must be read-only. Give an editing
branch its own `Session.run(..., workspace=isolated_path)`, separate session, and
non-conflicting output paths.

## Human input and interruption

`ask(question, returns=Type)` pauses with `awaiting_input`. Resume through the
SDK or CLI with a typed answer. The answer is validated against `Type` before it
is recorded. A rejected answer leaves the same request pending and includes a
`diagnostic` in `pending_input`, so it can be corrected with another resume.
An uncertain unsafe activity pauses as
`interrupted`; inspect it and call `resolve(..., retry=True)` or
`resolve(..., response=value)` explicitly.

If a provider completed before its artifact inventory was saved, inspect its
declared files and approve their exact contents before resuming. For example,
`client.resolve(run_id, operation_id, artifact_digests={"report": digest})`
accepts the inspected SHA-256 digest for `report`. Include every declared name;
use `None` only for an absent optional artifact. The CLI equivalent is
`botpipe resolve RUN OP --artifact-digests '{"report":"<sha256>"}'`.
This records operator provenance and does not bypass a running or unknown writer.
