# Architecture

Botpipe has three responsibilities: authoring ordinary Python workflows,
recording durable operations, and talking to Codex. Python expresses the
process; there is no graph language or scheduler DSL.

## Run ledger

The state root contains one directory per task and run:

```text
tasks/<task-id>/runs/<run-id>/
├── ledger.jsonl
├── input.json
├── request.md                 # when the invocation has a textual request
└── operations/<safe-operation-component>/
    ├── attempts/<attempt>/prompt.md
    ├── attempts/<attempt>/request.json
    ├── attempts/<attempt>/response.md
    └── payloads/*.json
```

`ledger.jsonl` is the sole authoritative run chronology. Every record has a
monotonic `seq`, UTC timestamp, event name, run identity and data object.
Operation and attempt records also name their operation and attempt. The first
record references `input.json`, references `request.md` when the invocation has
a textual request, and carries the run's workflow, configuration, limits and
task identity.

Prompts and response text are plain UTF-8 files. Large or type-sensitive values
use referenced JSON payloads with a relative path, byte count and SHA-256 digest.
The codec preserves tuples, models, exceptions, non-string mapping keys and
other supported replay values; readable JSON does not replace that typed value.

Opening a run streams the ledger to fold its current run, operation, attempt and
budget state. Readers take a complete-record prefix and never contact Codex.
Malformed complete records, sequence gaps, missing payloads and digest failures
fail clearly. An executor holding the run lock may truncate an incomplete final
line before appending and records that repair.

Each append validates referenced payloads first, writes one complete JSON line,
flushes and syncs it, and only then advances memory. If acknowledgement is
ambiguous, the writer checks the retained offset and re-establishes durability.
An unconfirmable append poisons that run writer rather than allowing another
effect without a reliable record.

The [generated readable-history example](examples/readable-history/README.md)
can be inspected without a database or Botpipe process.

Operation identity remains run, scope and ordinal plus durable inputs. Source
manifests and hashes are execution evidence, not replay keys. Compatible source
edits may resume when they consume the same operations in the same scopes and
order. A changed prompt, input, read digest, output schema or effective
configuration fails before dispatch at an already-recorded position.

## Provider attempts

A provider operation records intent before dispatch. Each physical attempt has
its exact prompt and resolved non-secret request. The ledger records preparation,
dispatch reservation, native thread and turn checkpoints, terminal response,
validation failures, repair attempts and cleanup evidence. The terminal response
is durable before validation and artifact capture, so recovery can adopt it
without another model call.

Provider budgets are ledger state. One dispatch reservation updates all enclosing
budgets under the append lock. Every physical turn, including repair and an
operator-authorized retry, reserves once. Replay and recovery do not reserve.

Best-effort `on_event` callbacks are separate from durable checkpoints. Callback
failure does not alter the operation and callback delivery is not proof that a
turn or response was recorded.

## Sessions and processes

Conversation continuity lives outside any one run in an atomic binding at
`sessions/<identity-hash>.json`. The binding contains the canonical session key,
native thread ID and, while work or shutdown is pending, the owning run, logical
operation and latest attempt. A pending binding remains owned through
validation, repair, and adapter disposal; another run cannot silently continue
that conversation.

Each complete provider operation owns a temporary `codex app-server` adapter.
The adapter starts or resumes the session's durable native thread, remains alive
through validation and output-repair turns, and is disposed before the session
lock is released. A later operation, even for the same session and runtime,
uses a new app-server and resumes the recorded thread. Calls sharing a session
serialize under a lock keyed by the state root and canonical session identity,
including across runs and processes. Distinct sessions may run concurrently.
Conversation history survives this boundary; background children and live tool
handles created by one operation are not promised to survive into the next.

`Provider.with_config` shares its parent's session unless `session=` replaces it.
`Session.task(key)` is stable across runs for one task, `Session.work_item(item,
key)` is stable for a selected item, and `session=None` creates an independent
turn.

Probing checks the installed executable and generated protocol schema without
starting a model turn. Required capabilities are enforced immediately before
dispatch. A changed probe is audit evidence and does not by itself invalidate a
recorded operation.

## Recovery

| Outcome | Runtime action |
| --- | --- |
| `Completed` | Adopt the authoritative response without redispatch |
| `Stopped` | Retry only when recorded and current policy permit it |
| `Running` | Attempt bounded targeted interruption; remain unresolved while effects may continue |
| `Unknown` | Block automatic retry and require reconciliation or explicit resolution |

Missing terminal evidence after dispatch authorization is uncertain. Botpipe
does not infer that a turn was never sent from a missing acknowledgement. A
terminal response is validated and captured on resume. A completed operation
replays its recorded typed result and approved artifact handles.

`retry_safe=True` permits repetition; it does not prove idempotence.
`retry_safe=False` prevents new automatic retries and repair dispatches but does
not prevent adoption of a response already recorded. An operator may retry an
`Unknown` attempt deliberately, accept a supplied or current valid result, or
fail it. That choice is recorded and does not erase the uncertainty of earlier
effects. A confirmed `Running` attempt must first reconcile to a terminal state.

Ordinary operation completion performs normal idle app-server disposal and
confirms that the app-server parent exited before releasing the session. Child
process survival is not guaranteed. If disposal fails after the result is
durable, Botpipe retains the completed result and records shutdown uncertainty;
it never redispatches the completed work. The session remains unavailable for
unsafe reuse until shutdown is retried or an operator resolves it.

Cancellation and timeout use the stronger interruption path: request native
turn interruption, perform bounded background-terminal cleanup when available,
and contain still-attached descendants through the POSIX process group or
Windows Job. Async cancellation waits for this attempt before returning.
Unconfirmed turn cleanup remains `Unknown`; a detached daemon is outside
Botpipe's containment guarantee.

## Concurrency and workspace state

A run lock permits one executor or resolver for a run. A session lock serializes
one conversation. The short in-process append lock orders parallel ledger writes
and is never held across provider I/O, callbacks or artifact capture.

Distinct sessions may write the same canonical workspace concurrently. Botpipe
does not take a workspace lock, snapshot or rollback. It never prepares, moves,
backs up, restores or merges repository files around a call. Applications that
need source isolation should use separate worktrees.

Declared outputs are validated and copied into immutable content-addressed
artifact storage when an operation completes. Capture observes current bytes; it
does not prove which concurrent writer produced them or create an atomic
repository snapshot. The run's ledger, input, operation evidence and shared
session bindings are protected from artifact destinations.

## Read projections

`Botpipe.inspect`, `runs show`, and `runs logs` fold a bounded ledger snapshot.
Inspection adds derived usage, artifacts and provenance without changing the
ledger. Run listing discovers `tasks/*/runs/*/ledger.jsonl`; run IDs remain unique
across the state root and ambiguous or missing identities fail instead of
selecting an arbitrary directory.

There is one current file-native format. Botpipe has no SQLite backend, legacy
reader, migration path or parallel receipt authority.
