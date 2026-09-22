# Authoring workflows

A workflow is an ordinary typed sync or async Python function decorated with
`@workflow`. Python owns conditions, loops, calls, and returns. Provider
operations, activities, human input, worklist snapshots, and artifact capture
form the durable boundaries.

```python
from botpipe import Provider, Session, ask_human, workflow


@workflow(name="release", version="2")
def release(version: str) -> str:
    reviewer = Provider(session=Session())
    review = reviewer.query(
        "Review this release candidate.", input={"version": version}
    )
    if review.value != "approved":
        reason = ask_human("Why should this release proceed?", returns=str)
        return f"held: {reason}"
    return "approved"
```

## Choose the operation

Use `generate` for a response from supplied immutable context. It denies model
commands and autonomous tools by default. A narrowly required read-only command
must be granted as one exact argv tuple with `allow_commands`; a shell string,
argument pattern, or prior turn does not grant authority.

Use `query` when the provider must list, search, read, or run constrained
read-only commands within an authorized scope. An omitted query scope uses the
workspace; an explicit empty scope disables local discovery. Network reads need
a separately configured read service.

Use `run` when the provider must edit a workspace, invoke effectful tools, or
produce declared files. Use `@activity` for application-owned I/O such as API
calls. `activity(retry_safe=False)` ensures an interrupted effect waits for
operator reconciliation before another attempt.

`generate` and `query` do not accept `writes`. A provider capability mismatch
raises `CapabilityError`; Botpipe does not substitute another backend.

## Sessions and roles

Every conversation-capable `Provider()` gets its own managed session. Variants
created by `with_config` share that exact lazily initialized session and pinned
backend selection.

```python
base = Provider()
planner = base.with_config(instructions="Plan concrete steps.")
builder = base.with_config(instructions="Implement and verify.")

plan = planner.query(request, returns=Plan)
change = builder.run("Implement the plan.", input=plan.value)
```

Pass `session=Session()` for a separate continuing conversation. Pass
`session=None` to the constructor or one call for independent calls. Give
parallel branches separate sessions; editing branches also need isolated
workspaces and non-conflicting output paths.

## Types, results, and artifacts

Use module-level Pydantic models, dataclasses, enums, paths, and JSON-compatible
collections for durable contracts. Provider output and human answers are
validated before their normalized state is committed. Output repairs use the
bounded `output_retries` argument; transport retry and uncertain-effect
reconciliation are separate mechanisms.

Declare provider destinations with `Artifact.json`, `.md`, `.text`, or `.raw`
in `writes=`. Mark an output required when later behavior depends on it.
`Result.artifacts` contains that operation's immutable versions. A live
workspace file is not historical evidence.

Use `Worklist.from_artifact` when code needs durable item selection and
completion. Resume retains the recorded item order and payload even if a live
source later changes.

## Human input and recovery

`ask_human(question, returns=Type)` suspends a workflow. Each pending request
has an operation ID, so concurrent questions remain targetable:

```python
pending = client.pending(run_id)
result = client.answer(run_id, pending[0]["operation_id"], "yes")
```

An invalid value keeps the same request pending with a diagnostic. Resume does
not guess which question an answer belongs to.

An operation that may have started an effect without a committed outcome is
`interrupted`. Inspect it and call `resolve(run_id, operation_id, retry=True)`
or supply the observed `response`. Repeating an uncertain effect always needs
explicit authorization. Artifact reconciliation additionally requires the full
declared digest/absence map.

## Source edits and persistence

Completed operations replay their saved outcomes while future operations use
current code. Keep the recorded operation prefix, identities, inputs, and typed
storage contracts compatible. A completed root returns its saved result.

Botpipe 2.0 reads only its own journal format. Start with a fresh state directory
when migrating an application from an earlier release; historical journals are
not imported or converted.
