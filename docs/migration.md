# Migrating to Botpipe 2.0

Botpipe 2.0 replaces the earlier execution API with a configured provider facade
and one imperative workflow runtime. Port applications directly; the package
does not ship compatibility wrappers.

| Earlier concept | Botpipe 2.0 |
| --- | --- |
| Vendor chosen implicitly | `Provider()` with a configured default, or an explicit vendor constructor |
| `Session.run(...)` | `Provider(session=session).run(...)` |
| General provider request | `generate`, `query`, `run`, or `decide`, chosen by required capability |
| Provider `retries=` | `output_retries=` for typed output repair |
| `ask(...)` / unscoped resume answer | `ask_human(...)` and an answer targeted by operation ID |
| Provider-free fresh session helper | `Provider(session=None)` or a per-call `session=None` |
| Graph, route, and mutable workflow state | Ordinary Python control flow and typed local values |
| Static graph inspection | Callable contract before execution and observed operations afterward |
| Old journal migration | A fresh 2.0 state directory |

## Provider calls

Before:

```python
session = Session.task("builder")
result = session.run(prompt, input=request, returns=Report, retries=2)
```

After:

```python
session = Session()
builder = Provider(session=session)
result = builder.run(prompt, input=request, returns=Report, output_retries=2)
```

Use `generate` when all evidence is supplied and no command is needed. Grant an
exception only as an exact read-only argv tuple. Use `query` for autonomous
read-only discovery, including enforced read-only commands. Use `run` when the
provider may edit or invoke effects. A reviewer that executes tests or writes a
report therefore remains a `run` call.

`Provider()` creates managed conversation continuity. Configuration roles made
with `with_config` share that session. Pass a new `Session()` for an independent
continuing reviewer and `session=None` for independent calls.

## Runtime and human input

`Botpipe.run()` accepts the workflow callable or discovered reference and its
ordinary arguments. `RunResult.value` is exactly the function return value.
Nested workflows return their ordinary function value.

Human input is explicitly targeted:

```python
questions = client.pending(run_id)
client.answer(run_id, questions[0]["operation_id"], answer)
```

CLI equivalents are `botpipe pending RUN_ID` and
`botpipe answer RUN_ID OPERATION_ID ANSWER`.

## Configuration

Rename the provider key to `default_provider` and put adapter options below the
provider. Model and effort are common settings; adapter command/configuration
belongs under `options`.

```toml
default_provider = "codex"
default_profile = "project"

[providers.codex]
model = "gpt-5.5"
effort = "high"
generate_allow_commands = []

[providers.codex.options]
command = ["codex", "exec"]

[providers.codex.profiles.project]
query_read_roots = ["."]
```

The source precedence is explicit path, `BOTPIPE_CONFIG`, one workspace config,
then `[tool.botpipe]`. Sources are not merged. Explicit collections and maps
replace configured values.

## Execution history

Pre-2.0 journals and persisted state are outside the supported format. Botpipe
does not inspect, import, convert, replay, resume, reconcile, or use them as
optimizer evidence. Keep an old environment if its historical inspection is
needed, and configure a fresh state directory for 2.0.
The default is `.botpipe-v2`, separate from the earlier `.botpipe` location.

Within the 2.0 journal format, compatible source edits remain supported:
committed operations replay, future operations use current code, and an
incompatible recorded input or typed storage contract fails before new effects.
