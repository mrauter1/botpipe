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

Select the preset by the work actually required. An inspection-only verifier
uses `query`; a verifier expected to execute tests or builds uses `run`, even
when it declares no output artifacts. See [Authoring](authoring.md) for operation
boundaries and [Prompting](prompting.md) for provider prompt contracts.

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
A schema validates response shape, not the factual correctness of its fields.

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

One temporary app-server serves a complete provider operation, including its
validation and repair turns. Botpipe disposes it before releasing the session;
the next operation resumes the durable thread in a new app-server. Conversation
history persists, but background children and live tool handles do not carry a
survival guarantee across operations. Normal disposal confirms that the
app-server parent exited before the session is released.

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

The default artifact-map key is the path's exact stem. For
`Artifact.md("evidence-brief.md")`, access
`result.artifacts["evidence-brief"]`; use `name="evidence_brief"` when attribute
access as `result.artifacts.evidence_brief` is desired. `required=False` is the
default and permits a conditional artifact to be absent. Set `required=True`
when completion is invalid without that file. An optional file is still
validated and captured when present.

The shared labs helper intentionally specializes this behavior. Its
artifact-only producers run in distinct, run-owned writable directories and
receive the source workspace separately for read-only inspection. It remaps all
declared destinations into the attempt directory, allows missing artifacts for
`question` or `blocked`, and requires the full declared set for `accepted`. This
is not a general `Provider.run` workspace-isolation guarantee.

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

To test replay, resume the completed run and pass its workflow definition. Do
not call `run` again with the same ID.

```python
from botpipe import Botpipe, Provider, workflow
from botpipe.providers import FakeProvider


@workflow(name="replay_example")
def work():
    return Provider().generate("Return done.").value

backend = FakeProvider(["done"])
with Botpipe(tmp_path, provider=backend) as client:
    first = client.run(work, task_id="docs", run_id="first")
    call_count = len(backend.calls)
    replayed = client.resume(first.run_id, workflow=work)
    assert replayed.value == first.value
    assert len(backend.calls) == call_count
```

The call timeout covers setup as well as execution. Async cancellation performs
a bounded interrupt and contained-tree cleanup attempt before the task finishes
cancelling. This exceptional cleanup is distinct from normal idle app-server
disposal after a result. If normal disposal fails after completion, the result remains
completed and is never redispatched; shutdown is uncertain, and the session is
blocked until cleanup is retried or explicitly resolved.
