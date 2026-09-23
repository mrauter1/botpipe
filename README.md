# Botpipe

Drive Codex from ordinary Python, and resume long work without paying for
completed turns twice.

```python
from botpipe import Provider
p = Provider()
print(p.generate("Explain what a database index is.").value)
```

Python owns control flow. Providers perform work, sessions carry conversation
history, and the runtime records operations and their outcomes.

## Install

Use Python 3.12 or 3.13 and an installed, authenticated Codex CLI:

```bash
pip install -e .
botpipe doctor
```

Botpipe uses `codex app-server`. It probes the installed binary instead of
pinning a version. Codex manages authentication; Botpipe does not read or store
credentials. Version 2.0 supports Codex on Linux, macOS and Windows.

## One primitive, two presets

```python
from pydantic import BaseModel
from botpipe import Artifact, Codex

class Modules(BaseModel):
    modules: list[str]

p = Codex(workspace=".")
answer = p.generate("Explain dependency inversion.")
facts = p.query("Which modules import the journal?", returns=Modules)
report = Artifact.md("report.md", required=True)
change = p.run("Add CSV export, tests, and a report.", writes=(report,))
```

| Call | Sandbox | Network | Tools | Recovery default |
| --- | --- | --- | --- | --- |
| `run` | Workspace write | Off by default | Codex defaults | Retry after confirmed stop |
| `query` | Read only | Off | Codex tools; ambient MCP off | Retry after confirmed stop |
| `generate` | Read only | Off | None by default | Retry after confirmed stop |

`generate(allowed_tools=("shell",))` opts into named tools. Restrictions use
Codex configuration and its sandbox, followed by an audit of observed tool
calls. Every result records the mechanisms used. Botpipe does not replace
Codex's tools or claim stronger isolation than Codex provides. Read-only and
network-off settings govern commands inside that sandbox, not opted-in remote
MCP or web tools. Audit can detect a disallowed call and retain evidence, but it
cannot undo a remote effect. Workspace-write also permits declared artifact
parents and Codex's native temporary roots.

Every preset defaults to `retry_safe=True`, including async calls. The flag
permits another attempt after Botpipe confirms the previous attempt stopped; it
does not prove idempotence. Set `retry_safe=False` for nonrepeatable external
effects. `Completed` recovery results are adopted, `Unknown` remains unresolved,
and a currently `Running` turn receives only a targeted bounded interrupt and
reconciliation attempt. A historical interrupted status or acceptance of a
native cleanup request does not confirm a stop without durable cleanup evidence.

Reusing `p` continues one conversation. `p.with_config(instructions="Review carefully.")`
shares that conversation; pass `session=Session()` for a separate one or
`session=None` for independent calls. Each call is durable, including calls
outside a workflow.

## Ordinary Python workflows

```python
from botpipe import Botpipe, Provider, ask_human, workflow

@workflow
def implement(request: str):
    coder = Provider()
    plan = coder.query("Propose a concise implementation plan.", input=request)
    approved = ask_human(plan.value + "\nProceed?", returns=bool)
    if approved:
        return coder.run(request).value
    return "Declined"

with Botpipe(workspace=".") as runtime:
    result = runtime.run(implement, "Add CSV export and tests.")
    print(result.status, result.run_id)
```

Loops, conditionals, activities, nested workflows, worklists, `parallel` and
`aparallel` use the same durable journal. Completed operations replay recorded
results. An interrupted provider turn follows its recorded retry policy; an
unresolved writable turn keeps its workspace fenced until recovery or operator
resolution.

```bash
botpipe workflows list
botpipe run ralph_loop "Add CSV export and tests"
botpipe runs list
botpipe runs show RUN_ID
botpipe resume RUN_ID
botpipe resolve RUN_ID OPERATION_ID --retry
botpipe resolve RUN_ID OPERATION_ID --accept
botpipe resolve RUN_ID OPERATION_ID --fail
# Explicitly abandon a stale fence only after confirming the old work stopped.
botpipe resolve RUN_ID OPERATION_ID --clear-fence --workspace PATH
```

## Configuration

```toml
# botpipe.toml
default_provider = "codex"

[codex]
path = "codex"
model = "gpt-5.4"
effort = "medium"
sandbox = "workspace-write"
network = false
retry_safe = true
interrupt_grace_seconds = 10
```

Per-call settings override derived configuration, constructor settings, file
settings, then built-in defaults. An enclosing workflow's policy is a ceiling.
Full access must be explicitly requested.

## Documentation

- [SDK](docs/sdk.md): presets, sessions, typed results, events and configuration.
- [Authoring](docs/authoring.md): durable functions, artifacts, loops and recovery.
- [CLI](docs/cli.md): execution, inspection, resolution and doctor.
- [Architecture](docs/architecture.md): journal, adapter, locks and process lifecycle.
- [Migration](docs/migration.md): the 1.x to 2.0 changes.
- [Codex compatibility](docs/codex-compatibility.md): capabilities and validation.
- [Optimizer](docs/optimizer.md): packaged optimization workflows.

Version 1.x journals are rejected untouched. Use a new state directory for 2.0.
