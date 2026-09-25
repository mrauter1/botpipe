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

From a Botpipe checkout, use Python 3.12 or 3.13 and an installed, authenticated
Codex CLI:

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
facts = p.query("Which modules implement the run ledger?", returns=Modules)
report = Artifact.md("report.md", required=True)
change = p.run("Add CSV export, tests, and a report.", writes=(report,))
```

| Call | Sandbox | Network | Tools | Recovery default |
| --- | --- | --- | --- | --- |
| `run` | Workspace write | Off by default | Codex defaults | Retry after confirmed stop |
| `query` | Read only | Off | Codex defaults, without ambient MCP | Retry after confirmed stop |
| `generate` | Read only | Off | None by default | Retry after confirmed stop |

`query(tools=("shell",))` and `generate(allowed_tools=("shell",))` select an
explicit tool allowlist. Restrictions use
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

Reusing `p` continues one conversation. A variant made with
`p.with_config(instructions="Review carefully.")` shares that conversation;
pass `session=Session()` for a separate conversation or `session=None` for an
independent call. Each complete provider operation gets a temporary app-server,
kept through validation and output repair and then disposed before the session
can be used again. Later operations resume the durable conversation in a new
app-server. Each call is durable, including calls outside a workflow.
Botpipe does not promise that background children or live tool handles survive
between operations. Normal disposal confirms that the app-server parent exited;
child survival remains unguaranteed. If a completed operation's server cannot be
disposed, its result remains completed and is never redispatched; the session
stays blocked until shutdown is retried or explicitly resolved.

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
`aparallel` use the same durable run ledger. Completed operations replay recorded
results. Parallel branches with distinct sessions may run writable calls in the
same repository at the same time; calls sharing a session serialize. An
interrupted provider turn follows its recorded retry policy, and unresolved work
remains attached to that operation and run until recovery or operator resolution.
It does not reserve the workspace globally.

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

Botpipe never prepares a transactional workspace snapshot or moves, backs up,
restores, or rolls back repository files around a provider call. Retries operate
on the repository's current state. Declared `writes` are validated and captured
immutably when an operation completes; capture is not exclusive-writer
attribution or an atomic snapshot of the repository.

## Readable history

Each run is a directory under the state root:

```text
tasks/<task-id>/runs/<run-id>/
├── ledger.jsonl
├── input.json
├── request.md                 # when the invocation has a textual request
└── operations/<safe-operation-component>/attempts/<attempt>/
    ├── prompt.md
    ├── request.json
    └── response.md
```

`ledger.jsonl` is the authoritative chronological history. `input.json` keeps
the encoded positional and keyword arguments, while optional `request.md` makes
the original textual request immediately readable. The ledger's numbered records
cover run state, operations, attempts, dispatch reservations, responses,
validation, recovery and resolutions. Large typed payloads remain lossless in
referenced JSON files. Provider prompts and textual responses are plain UTF-8.
Use `botpipe runs show RUN_ID` for the folded view or `botpipe runs logs RUN_ID`
for JSONL events. Reading a run never contacts Codex.
The [checked-in readable-history example](docs/examples/readable-history/README.md)
shows a generated repair, accepted human answer, interrupted activity, and
operator resolution.

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

Model names pass through to Codex, so replace the example model with one your
installation supports. Per-call settings override constructor settings, which
override file settings and built-in defaults. An enclosing workflow's policy is
a ceiling. Full access must be explicitly requested.

`[codex].timeout` limits one provider call. The separate top-level `timeout`
provides the default provider-dispatch and session-wait bound.

## Documentation

- [SDK](docs/sdk.md): presets, sessions, typed results, events and configuration.
- [Authoring](docs/authoring.md): durable functions, artifacts, loops and recovery.
- [CLI](docs/cli.md): execution, inspection, resolution and doctor.
- [Architecture](docs/architecture.md): ledger, sessions, locks and process lifecycle.
- [Codex compatibility](docs/codex-compatibility.md): capabilities and validation.
- [Testing](docs/testing.md): behavioral coverage, parallel runs and CI timings.
- [Workflow improvement](docs/optimizer.md): diagnose, implement, and evaluate a bounded change.

Botpipe uses one current file-native format. It does not import or migrate older
state formats.
