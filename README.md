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

| Call | Sandbox | Network | Tools | Interrupted effects |
| --- | --- | --- | --- | --- |
| `run` | Workspace write | Off by default | Codex defaults | Require reconciliation |
| `query` | Read only | Off | Codex tools; ambient MCP off | Retry automatically |
| `generate` | Read only | Off | None by default | Retry automatically |

`generate(allowed_tools=("shell",))` opts into named tools. Restrictions use
Codex configuration and its sandbox, followed by an audit of observed tool
calls. Every result records the mechanisms used. Botpipe does not replace
Codex's tools or claim stronger isolation than Codex provides.

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
results. An interrupted writable provider turn stays unresolved until its
outcome is recovered or an operator resolves it.

```bash
botpipe workflows list
botpipe run ralph_loop "Add CSV export and tests"
botpipe runs list
botpipe runs show RUN_ID
botpipe resume RUN_ID
botpipe resolve RUN_ID OPERATION_ID --retry
botpipe resolve RUN_ID OPERATION_ID --accept
botpipe resolve RUN_ID OPERATION_ID --fail
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
