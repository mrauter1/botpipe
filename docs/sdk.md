# Provider SDK

`Provider()` uses the configured provider (Codex is the only provider in 2.0),
while `Codex()` selects it explicitly. Construction performs no I/O. The first
call loads configuration and starts the runtime. Both classes support `with`
blocks and `close()`.

## Operations

`run(prompt, *, input=None, reads=(), writes=(), returns=str, session=INHERIT,
sandbox=None, network=None, tools=None, timeout=None, output_retries=None,
retry_safe=None, on_event=None)` is the execution primitive. `None` inherits
configuration. The default sandbox is `workspace-write`, with network disabled,
and `retry_safe` defaults to `True`.

`query` is read-only with network disabled and accepts `tools=`. `generate` has
the same sandbox and network policy but uses `allowed_tools=()`; its empty
default disables tools. Neither preset accepts `writes`, `sandbox`, or `network`.
Use `run` when you need those controls.

All three methods accept `timeout`, `output_retries`, `retry_safe`, and
`on_event`. Their async forms are `arun`, `aquery`, and `agenerate`.

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

Botpipe validates typed results locally. A validation failure gets up to
`output_retries` additional turns (default two) in the same conversation.
Repairs count against provider budgets. Set `retry_safe=False` when repeating an
operation could duplicate an external effect; this also prevents Botpipe from
starting a new output-repair turn.

When Codex supports `outputSchema`, Botpipe sends it natively; otherwise it adds
the schema to the prompt. Local validation runs in both cases.

`retry_safe=True` permits repetition; it does not make an operation idempotent.
After interruption, Botpipe adopts a completed result when it can, retries only
after confirming the old attempt stopped, and otherwise leaves the operation
unresolved for operator action.

## Sessions and roles

1. Each provider owns one lazily created session.
2. Reusing a provider continues its Codex thread.
3. `with_config` shares the session unless `session=` is supplied.
4. `session=None` makes a call independent.
5. Within workflows, `Session.task(key)` creates a task-scoped identity and
   `Session.work_item(item)` creates one for a `WorkItem`; both survive resume.

```python
from botpipe import Provider, Session

base = Provider()
planner = base.with_config(instructions="Plan small, reviewable changes.")
reviewer = base.with_config(instructions="Find correctness defects.", session=Session())
```

`with_config` returns a variant without changing the original. It accepts
`instructions`, `model`, `effort`, `workspace`, `sandbox`, `network`, `tools`,
`timeout`, `output_retries`, `retry_safe`, `name`, `settings`, and `session`.
`settings` accepts validated, non-secret Codex configuration overrides.
Unless `session=` is supplied, the variant shares both the runtime and
conversation with its parent. Per-call settings override provider settings,
which override the `[codex]` table. An enclosing workflow policy remains a
ceiling: a provider call may tighten it but cannot widen it.

The provider `timeout` setting (and `[codex].timeout`) limits one provider call.
The top-level `timeout` in `botpipe.toml` separately supplies the default
provider-dispatch and session-wait bound.

Turns sharing a session are serialized. Give parallel branches separate
sessions; writable calls with distinct sessions may run concurrently in the same
repository. A conversation can mix presets; each turn gets the policy of the
method used for that turn. Changing its tool profile requires Codex to resume the
same history with the new profile; Botpipe fails before dispatch if the installed
Codex cannot enforce that transition.

## Results, artifacts and events

`Result[T]` exposes `value`, `artifacts`, `usage`, `operation_id`, `run_id`, and
`metadata`. Codex results include identifiers and enforcement evidence in
`metadata`. Replays return the recorded result without invoking Codex again.

Declare output files with `Artifact.json`, `Artifact.md`, `Artifact.text`, or
`Artifact.raw`, then pass them in `writes` to `run`. A required file or JSON
schema is validated before the operation completes. The returned artifact is a
content-checked immutable snapshot of that file. The current file may already
have existed and still be captured when valid; Botpipe does not claim exclusive
writer attribution or an atomic repository snapshot. It does not prepare,
backup, restore, or roll back workspace files. A retry runs against current
state.

`on_event` receives `StreamEvent(type, data)`. Notifications are best effort;
callback exceptions do not change the operation outcome. Replay emits one
`replayed` event. Durable evidence is recorded separately from callbacks.

## Enforcement boundaries

Approval policy is always `never`. Query and generation disable ambient MCP
servers unless their tools are explicitly allowed. For an explicit tool
allowlist, Botpipe uses Codex controls and audits observed calls. An unlisted
observed tool call fails and keeps its evidence. Detection cannot undo an effect
that already occurred.

Read-only and network-off settings govern commands in Codex's sandbox; they do
not prevent remote effects from a tool you explicitly allow. Workspace-write
permits the workspace, declared artifact parents, and Codex's temporary roots.
`run(sandbox="full-access")` supplies no filesystem isolation.

Direct calls are one-operation durable runs, visible through `botpipe runs` and
recoverable through `resume` and `resolve`, just like workflow operations.

The call timeout covers setup as well as execution. Async cancellation performs
a bounded interrupt and cleanup attempt before the task finishes cancelling.
Within a runtime, each logical session owns its app-server process, so escalation
is targeted to that conversation. Calls sharing the session serialize and are
reconciled from their durable attempt evidence; unrelated sessions keep their
own processes. Codex 0.156.1 keeps an exclusive writer lease while a thread is
loaded. Close the current provider or runtime before handing that durable session
to another process; the next runtime can then resume the bound native thread.
