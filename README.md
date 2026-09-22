# Botpipe

Botpipe is a provider-first Python SDK and durable workflow runtime. Providers
perform work, sessions carry conversation continuity, ordinary Python expresses
the process, and Botpipe records operations and outcomes for inspection and
recovery.

Botpipe 2.0 is a clean break. It does not read, migrate, replay, or analyze
execution journals created by earlier versions.

This rewrite is a development build. The [native capability matrix](docs/native-capability-evidence.md)
records supported interfaces and outstanding release gates. Unsupported
operations fail before dispatch; the full native conformance baseline has not
passed.

## Install

Botpipe requires Python 3.12 or newer.

```bash
pip install botpipe
```

## First call

Select a default provider in `botpipe.toml`:

```toml
default_provider = "claude"
```

Then use the ordinary `Provider()` facade:

```python
from botpipe import Provider

provider = Provider()
answer = provider.generate("Explain the purpose of a database index.")
print(answer.value)
```

There is no implicit vendor fallback. If no default is configured, a default
provider operation raises `ConfigurationError` before dispatch. Explicit
constructors such as `Codex()`, `ClaudeCode()`, `Pi()`, and `Jev()` select that
backend deliberately.

The example requires the Claude CLI profile documented in the capability
matrix. Codex's current CLI profile supports `run`; it does not support
tool-free `generate`. The query and exact-command examples below require a
mediated SDK profile and a host that passes its isolation checks.

## Operations and sessions

`generate`, `query`, and `run` state the authority a call needs:

- `generate` uses supplied context and has no commands or autonomous tools by
  default. `allow_commands` may grant exact read-only argv tuples.
- `query` may discover information through enforced read-only operations within
  its effective scope. It cannot write to the provider workspace or mutate a
  remote service.
- `run` may make changes within the effective policy and declared workspace.
- `decide` uses a provider's native structured decision contract.
- `ask_human` requests typed human input from a workflow.

Conversation-capable providers use a private managed session by default:

```python
from botpipe import Provider, Session

base = Provider()
base.generate("Remember that the service uses PostgreSQL.")
answer = base.generate("Which database does the service use?")

reviewer = base.with_config(instructions="Review critically.")
independent_reviewer = base.with_config(session=Session())
stateless = Provider(session=None)
one_off = base.generate("Explain indexes.", session=None)
```

Construction and `with_config` do no I/O. Backend selection is resolved lazily
at first effective use, then pinned across the provider family. Derivation is
immutable: omitted values inherit, explicit nullable values clear, and
collections replace.

Exact command grants do not grant write authority:

```python
status = Provider().generate(
    "Summarize the repository status.",
    allow_commands=(("git", "status", "--short"),),
)
```

## A complete workflow

```python
from pydantic import BaseModel
from botpipe import Artifact, Botpipe, Provider, Session, ask_human, parallel, workflow


class Plan(BaseModel):
    steps: list[str]


@workflow(name="implement_change", version="2")
def implement_change(request: str):
    base = Provider()
    planner = base.with_config(instructions="Create a concrete plan.")
    builder = base.with_config(instructions="Implement and verify the plan.")
    plan = planner.query(request, returns=Plan)
    change = builder.run(
        "Implement this plan and write the verification report.",
        input=plan.value,
        writes=(Artifact.md("verification.md", required=True),),
    )
    correctness, clarity = parallel(
        lambda: base.with_config(session=Session()).query(
            "Review correctness.", input=change.value
        ),
        lambda: base.with_config(session=Session()).generate(
            "Review clarity from the supplied result.", input=change.value
        ),
    )
    if correctness.value != "approved":
        reason = ask_human("Why should this change proceed?", returns=str)
        return {"status": "held", "reason": reason}
    return {
        "status": "approved",
        "clarity": clarity.value,
        "report": change.artifacts["verification"],
    }


client = Botpipe(workspace=".")
result = client.run(implement_change, "Add CSV export", task_id="csv-export")
print(result.status, result.run_id)
```

`Result[T]` always exposes `value`, operation artifacts, usage, `run_id`, and
`operation_id`. `RunResult[T].value` is exactly what the workflow returned.
Multiple provider-written outputs remain separate immutable artifact handles;
run-wide aggregation keeps producing scope, operation, name, and version.

## Configuration

Botpipe selects one source: explicit SDK/CLI `--config`, then
`BOTPIPE_CONFIG`, then a workspace `botpipe.toml` (JSON/YAML equivalents are
also recognized), then `[tool.botpipe]` in `pyproject.toml`. It never recursively
merges competing files. Relative paths are resolved from the workspace.

```toml
default_provider = "claude"
default_profile = "project"
state_dir = ".botpipe-v2"
max_operations = 500
timeout = 1800

[policy]
sandbox_mode = "workspace_write"
network = "none"

[providers.claude]
query_read_roots = ["."]
generate_allow_commands = [["git", "status", "--short"]]

[providers.claude.options]
interface = "agent_sdk"

[providers.claude.profiles.project]
generate_allow_commands = []
```

This mediated profile requires `pip install 'botpipe[claude-sdk]'`, native
authentication, and the supported local sandbox described in the matrix.

An omitted `query_read_roots` uses the workspace default. An explicit empty
array disables local discovery. CLI/application overrides replace configured
maps and collections rather than recursively merging them. Credentials never
belong in serializable settings, including provider `options` or embedded URL
user information; use environment credentials, a credential-source reference,
or an injected live adapter.

## Command line

```bash
botpipe workflows list --workspace .
botpipe workflows show package.flow:implement --workspace .
botpipe run package.flow:implement "Add CSV export" --task-id csv --workspace .
botpipe runs list --status awaiting_input --workspace .
botpipe runs show RUN_ID --workspace .
botpipe runs logs RUN_ID --workspace .
botpipe pending RUN_ID --workspace .
botpipe answer RUN_ID OPERATION_ID '"yes"' --workspace .
botpipe resume RUN_ID --workspace .
botpipe resolve RUN_ID OPERATION_ID --retry --workspace .
```

Commands write JSON to stdout and diagnostics to stderr. Catalog listing parses
Python and manifests without importing workflow modules. Execution accepts a
catalog name, `module:function`, or `file.py:function`, and rejects ambiguous
effective names.

See [Authoring](docs/authoring.md), [SDK](docs/sdk.md),
[Architecture](docs/architecture.md), [CLI](docs/cli.md), and the
[2.0 migration guide](docs/migration.md). The
[native capability evidence](docs/native-capability-evidence.md) records the
current adapter limits and proof status without treating fake-provider tests as
native conformance.
