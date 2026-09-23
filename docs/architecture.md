# Architecture

Botpipe has three responsibilities: authoring ordinary Python workflows,
coordinating durable operations, and talking to Codex. Python expresses the
process; there is no graph language or scheduler DSL.

## Runtime and journal

The SQLite journal retains runs, operations, sessions, provider budgets and
events. The 2.0 schema adds Codex thread and turn identifiers, the preset,
enforcement record and probe hash. Opening a 1.x journal fails without migrating
or modifying it.

An operation is identified by run, scope and position. Its fingerprint includes
the prompt, input, read digests, output schema and resolved configuration. A
committed operation replays its result. A different fingerprint at a committed
position fails before dispatch. Existing compatible source-edit checks remain
part of workflow resume.

A provider intent precedes dispatch. A terminal response is recorded before
output validation and immutable artifact capture. This ordering lets recovery
adopt completed work without another model call, including after interruption
between response and capture. Repairs are additional recorded, budgeted attempts
on the same thread. Recovery itself does not consume a dispatch budget.

Activities, human answers, nested workflows, parallel branches and worklist
updates use the same operation journal. Activities default to retry-safe; an
activity with uncertain external effects must declare `retry_safe=False`.

## Codex adapter

One lazy `codex app-server` process belongs to a runtime and multiplexes its
threads. Its small adapter boundary is `probe`, `start_turn`, `interrupt` and
`close`. Runtime request/response records carry the durable attempt context.
There is one transport and one provider implementation.

Probing checks the installed executable's identity and generated protocol
schemas. Required methods are `thread/start`, `thread/resume`, `turn/start` and
`turn/interrupt`, with per-turn sandbox policy. Optional `outputSchema` falls
back to a prompt schema and local validation. Missing tool/MCP configuration
capabilities disable the affected presets, not unrestricted provider calls.

Every turn uses approval policy `never`. `query` and `generate` fix the read-only
sandbox and network off. Generation disables tool features outside its named
allowlist and audits the event stream. An unexpected tool call fails the
operation with retained evidence. Codex enforces its sandbox; Botpipe records
configuration and observations rather than claiming a separate proof tier.

Session bindings persist Codex thread identifiers. Threads are resumed after
restart. Turn-level settings can change per call; a change to a setting that
Codex only accepts at thread creation must be rejected if it cannot be applied
without losing the promised history.

## Recovery

| Recorded state | Read-only preset | `run` |
| --- | --- | --- |
| No dispatch intent | Dispatch | Dispatch |
| Dispatched, terminal response missing | Reconcile, then retry if needed | Recover completed result or remain unresolved |
| Terminal response recorded | Validate and capture | Validate and capture |
| Committed | Replay | Replay |

An operator resolves uncertainty with explicit retry, acceptance of the current
workspace, or failure. A retry never pretends the earlier effects did not happen.
Accepting captures declared artifacts and still validates their contract.

## Concurrency

A run lock is keyed by journal path and run id and held for execution or
resolution. Another executor receives `RunBusy` immediately. A workspace writer
lock is keyed by canonical root and held for a writable provider turn, including
output capture. It waits only within the operation's timeout, then raises
`WorkspaceBusy`. Coordination files live in per-user state, outside workspaces.
Windows and macOS canonical roots are compared without case sensitivity.

An unresolved writable operation leaves a small fence next to its workspace
lock. Other runs trying to write the root receive `WorkspaceUnresolved`, naming
the run to resolve. Resolving the owning operation clears its fence.

Read-only presets do not acquire the writer lock or consult its fence. They may
observe a concurrent edit in progress. Overlapping roots such as `repo` and
`repo/sub` are not coordinated. Parallel writers should use separate worktrees.
Different hosts and containers are not coordinated.

## Process lifecycle

The app-server runs in a POSIX process group or a Windows Job Object with
kill-on-close. Cancellation sends `turn/interrupt`, waits up to the configured
grace period, then terminates the process group or Job if needed. Escalation
interrupts all turns sharing that server; each retains its own recovery status.
Async cancellation waits for cleanup before returning control to the caller.

Codex owns the sandbox for its child commands. Botpipe adds no namespaces.
Still-attached descendant groups are included in shutdown, with process identities
checked before signalling. A daemon already detached from the tree is outside
Botpipe's control. Full access and explicitly enabled remote MCP tools have the effects
authorized by that configuration; filesystem read-only is not remote isolation.
