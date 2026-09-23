# Provider SDK

`Provider()` selects Codex through `default_provider`; `Codex()` selects it
explicitly. Construction performs no I/O. The first call loads configuration,
opens the durable runtime and probes Codex. Model names pass through unchanged.

## Operations

`run(prompt, *, input=None, reads=(), writes=(), returns=str, session=INHERIT,
sandbox=None, network=None, tools=None, timeout=None, output_retries=None,
on_event=None)` is the execution primitive. `None` inherits configuration.
The default sandbox is `workspace-write`, with network disabled.

`query` fixes `sandbox="read-only"`, `network=False` and `writes=()`.
`generate` fixes those same values and takes `allowed_tools=()` instead of
`tools`. Supplying a fixed argument raises `TypeError`, even when its value
matches the preset. Use `run` for different settings.

`arun`, `aquery` and `agenerate` have the same semantics. Cancelling an async
call waits for interrupt and process cleanup before raising `CancelledError`.
The default interrupt grace period is ten seconds.

```python
from pydantic import BaseModel
from botpipe import Codex

class Review(BaseModel):
    accepted: bool
    notes: str = ""

reviewer = Codex(instructions="Review correctness and simplicity.")
result = reviewer.query("Review the current diff.", returns=Review)
print(result.value.accepted, result.value.notes)
```

Typed results use Codex's `outputSchema` when available and a prompt schema
otherwise. Botpipe always validates the result locally. A validation failure
gets up to `output_retries` additional turns (default two), on the same thread.
Repairs count against budgets. A completed turn advances conversation history
even when its output fails validation.

## Sessions and roles

1. Each provider owns one lazily created session.
2. Reusing a provider continues its Codex thread.
3. `with_config` shares the session unless `session=` is supplied.
4. `session=None` makes a call independent.
5. Within workflows, `Session.task(key)` and `Session.work_item(item)` create
   durable scoped identities that survive resume.

```python
from botpipe import Provider, Session

base = Provider()
planner = base.with_config(instructions="Plan small, reviewable changes.")
reviewer = base.with_config(instructions="Find correctness defects.", session=Session())
```

`with_config` returns an immutable variant. Supported fields are `instructions`,
`model`, `effort`, `workspace`, `sandbox`, `network`, `tools`, `timeout`,
`output_retries`, `name`, `settings` and `session`. A role can tighten an
enclosing run's permissions; it cannot widen them. Settings are validated
non-secret Codex configuration overrides. Never put credentials in a prompt or
durable configuration.

Turns sharing a session are serialized. Parallel branches use separate
sessions. A session can mix presets because its sandbox is set for each turn.
Thread-level tool configuration must remain enforceable; unsupported transitions
fail before dispatch with a capability error.

## Results, artifacts and events

`Result[T]` exposes `value`, `artifacts`, `usage`, `operation_id`, `run_id` and
`metadata`. Metadata includes Codex version, thread and turn ids, probe hash,
tool evidence and the enforcement record. Replays return the recorded result
without locating or invoking Codex.

Declare output files with `Artifact.json`, `Artifact.md`, or another artifact
constructor, then pass them in `writes` to `run`. Captured versions are immutable
and content checked. Required files and schema constraints are validated before
commit. Botpipe does not roll back repository edits after a validation failure.

`on_event` receives `StreamEvent(type, data)`. Notifications are best effort and
are not journaled as callbacks. Callback exceptions do not change the operation
outcome. Replaying a call emits one `replayed` event. Durable tool evidence is
recorded separately from the callback.

## Enforcement boundaries

Approval policy is always `never`. Query and generation disable ambient MCP
servers unless explicitly named in their tool allowlist. Generation configures
available Codex tool features and audits notifications; an unlisted observed
tool call fails with `CapabilityError`, preserving its evidence.

The read-only sandbox is Codex's filesystem protection, not a guarantee about
remote MCP servers. Opting into an MCP server authorizes its tools and their
possible remote effects. `run(sandbox="full-access")` supplies no filesystem
isolation. Botpipe records these mechanisms honestly.

Direct calls are one-operation durable runs, visible through `botpipe runs` and
recoverable through `resume` and `resolve`, just like workflow operations.
