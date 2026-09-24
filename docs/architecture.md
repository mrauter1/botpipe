# Architecture

Botpipe has three responsibilities: authoring ordinary Python workflows,
coordinating durable operations, and talking to Codex. Python expresses the
process; there is no graph language or scheduler DSL.

## Runtime and journal

The SQLite journal retains runs, operations, sessions, provider budgets and
events. The 2.0 schema adds Codex thread and turn identifiers, the preset,
enforcement record and probe hash. Opening a 1.x journal fails without migrating
or modifying it.

An operation is identified by run, scope and position. Provider-operation inputs
include the prompt, input, read digests, output schema and resolved user
configuration. Probe hashes and other discovered installation/profile facts
remain audit evidence; a change in those observations alone is not a durable
identity veto. A committed operation replays its result. A different durable
fingerprint at a committed position fails before dispatch.

Workflow and operation callable identities deliberately omit source text.
Captured source hashes and manifests are provenance evidence, not replay keys.
Edited orchestration may resume when it consumes the same recorded operations in
the same scopes and order with matching durable inputs; an inserted, removed,
reordered or changed operation fails replay. Completed child workflows replay as
one child operation without re-entering the child body.

A provider intent precedes dispatch. A terminal response is recorded before
output validation and immutable artifact capture. This ordering lets recovery
adopt completed work without another model call, including after interruption
between response and capture. Repairs are additional recorded, budgeted attempts
on the same thread. Recovery itself does not consume a dispatch budget.

Activities, provider turns, human answers, nested workflows, parallel branches,
session bindings and worklist updates use the same operation journal and share
the run operation limit. Activities and provider turns default to
`retry_safe=True`. This flag permits repetition; it does not establish that the
operation is idempotent. Provider recovery also confirms that the prior turn
stopped before automatically dispatching a replacement. Nonrepeatable external
effects must use `retry_safe=False`.

## Codex adapter

One lazy `codex app-server` process belongs to a runtime and multiplexes its
threads. Its small adapter boundary is `probe`, `start_turn`, `interrupt` and
`close`. Runtime request/response records carry the durable attempt context.
There is one transport and one provider implementation.

Probing checks the installed executable's identity and generated protocol
schemas. Required methods are `thread/start`, `thread/resume`, `turn/start` and
`turn/interrupt`, with per-turn sandbox policy. Optional `outputSchema` falls
back to a prompt schema and local validation. Unused schema item versions do not
veto an otherwise usable installation. Missing capabilities actually required
by a call fail before dispatch; probe or profile changes alone do not invalidate
durable operation identity.

Every turn uses approval policy `never`. `query` and `generate` fix the read-only
sandbox and network off for commands within Codex's sandbox. Workspace-write
turns allow the workspace, declared artifact parents, and Codex's native
temporary roots. For an explicit tool allowlist, Botpipe disables discovered
tool-enabling features it knows how to control while preserving unrelated and
unknown feature flags. It audits the event stream, and a disallowed observed
tool call fails the operation with retained evidence. That audit detects the
violation; it cannot undo remote effects. Codex enforces its sandbox, while
Botpipe records configuration and observations.

Session bindings persist Codex thread identifiers. Threads are resumed after
restart. Sandbox policy is supplied per turn. Tool configuration is a thread
profile: when it changes, Botpipe unsubscribes the idle thread and resumes the
same history with the new configuration. If the installed Codex cannot perform
that transition, the call fails before dispatch.

A provider lazily creates a run-scoped session; providers derived with
`with_config` share it unless the session is replaced. `Session.task(key)` is
stable across runs of one task, `Session.work_item(item, key)` is stable for a
selected work item, and `session=None` creates independent turns. Durable session
locks serialize use of one session across threads and processes.

## Recovery

| Reconciliation result | Action |
| --- | --- |
| `Completed` | Adopt the authoritative response; do not redispatch |
| `Stopped` | Retry automatically only when recorded and current policy permit it; otherwise wait for operator resolution |
| `Running` | Make a targeted, bounded interrupt/reconciliation attempt; keep the operation unresolved while it may still act |
| `Unknown` | Keep the operation unresolved until an operator resolves it |

`Stopped` requires durable quiescence evidence. Before a turn acknowledgement,
a durable receipt recording failure and `cleanup.status=completed` is sufficient.
For native history marked failed, interrupted, or cancelled, Botpipe must run
background-terminal cleanup and then prove through the bounded, paginated list
that no background terminal remains. A historical terminal status or acceptance
of the cleanup RPC alone is not proof and remains `Unknown`.

A recorded terminal response is validated and captured without redispatch, so
completed output-repair work can still replay when later policy sets
`retry_safe=False`. That setting suppresses new automatic retries and new output
repair dispatches. Automatic and operator-authorized retries are recorded with
their origin. Cancellation ends the current invocation after bounded cleanup;
it does not redispatch. A later explicit resume may retry subject to the recorded
policy and limits. Retries operate on the repository's current state.

The run operation limit applies atomically across nested and parallel scopes and
can only be increased on resume. The run timeout supplies the default provider
dispatch and session-lock wait bound; it is not an overall deadline for workflow
Python. Durable provider-budget deadlines retain their original deadline across
suspension and resume, and nested provider budgets all apply.

An operator resolves uncertainty with explicit retry, acceptance of the current
workspace, or failure. A retry never pretends the earlier effects did not happen.
Accepting validates and captures the current declared artifact files. A valid
file may have existed before the attempt; capture does not establish exclusive
writer attribution.

## Concurrency

A run lock is keyed by journal path and run id and held for execution or
resolution. Another executor receives `RunBusy` immediately.
Windows and macOS canonical roots are compared without case sensitivity.

Conversation turns use the same file-lock primitive, keyed by journal and durable
session identity. Separate handles for one task or work item therefore serialize
across threads and processes, including the repair loop and session updates.
Independent calls (`session=None`) need no conversation lock.

Distinct sessions may dispatch writable turns against the same canonical
workspace at the same time, across threads and processes. An unresolved writable
operation remains governed by its own operation and run recovery state; it does
not create a global workspace reservation. Read-only calls and writers may
observe concurrent edits. Use separate worktrees when an application needs
source isolation.

The workspace is shared mutable state, not a Botpipe transaction boundary.
Botpipe does not prepare, move, back up, restore, or roll back workspace files,
and does not take an atomic repository snapshot. Declared output capture
validates and stores immutable versions of the current files only.

## Process lifecycle

The app-server runs in a POSIX process group or a Windows Job Object with
kill-on-close. Cancellation sends `turn/interrupt`, waits up to the configured
grace period, then attempts to terminate the process group or Job if needed.
Escalation interrupts all turns sharing that server; each retains its own
recovery status. Async cancellation waits for the bounded cleanup attempt before
returning control to the caller. Because the server is shared, cancellation may
interrupt sibling operations; Botpipe does not promise independent cancellation.
Cleanup evidence is reconciled for each affected operation as `Completed`,
`Stopped`, or `Unknown`. An unconfirmed stop remains `Unknown` for that operation
and run.

Codex owns the sandbox for its child commands. Botpipe adds no namespaces.
Still-attached descendant groups are included in shutdown, with process identities
checked before signalling. A daemon already detached from the tree is outside
Botpipe's control, so cleanup cannot guarantee that every escaped process ended.
Full access and explicitly enabled remote MCP tools have the effects authorized
by that configuration; filesystem read-only is not remote isolation.
