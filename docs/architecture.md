# Architecture

Botpipe is a durable-functions runtime for trusted Python workflows.

## The invariant

Python owns control flow. Every material observation or external effect goes
through a recorded Botpipe operation.

The workflow body can use normal functions, conditions, loops, exceptions,
nested workflows, and `parallel()`. Botpipe does not compile that code into a
second state machine. Instead it assigns deterministic operation identities and
replays committed results from a SQLite ledger.

## Ledger and replay

Each run records metadata, source fingerprints, operation intent and outcomes,
provider sessions, human-input events, usage, and immutable artifact references.
Files become durable before the ledger refers to them. Shared workspace claims
protect overlapping live reads and writes across processes and state directories.

The 2.0 ledger defaults to `workspace/.botpipe-v2`. Before opening an existing
database in write mode, Botpipe checks its application and format versions
through a read-only connection. This implementation supports the version-2
schema; incompatible stores are rejected without schema changes and the operator
is directed to a fresh state directory. The existing SQLite/checkpoint design is
retained on its merits. Backward compatibility is optional under the PRD, and a
different format boundary requires its own validated implementation.

Run records own root execution facts; operation records own their checkpoints.
The journal commits an operation checkpoint, its native session update, and the
associated event together. Physical-dispatch events retain separate evidence
about each actual provider attempt and its usage. An operation response cannot
retroactively establish the usage of an earlier unknown dispatch.

Atomic publication flushes file contents before replacement. On POSIX it also
flushes directory entries and propagates flush failures. Windows retains the
file flush and atomic replacement, but Python cannot fsync directory handles
there; the same directory-entry persistence after sudden power loss is not
guaranteed.

On replay, a completed operation returns its recorded outcome. Matching uses its
scope, ordinal, kind, logical callable identity, and actual inputs, including
provider prompts and schemas. A mismatch blocks that operation before effects.
Implementation hashes and workflow version labels are observational metadata.
Activities, workflow bodies, and helpers may be edited: recorded work is reused
and future work executes current code. A completed root run returns its saved
result without rerunning the workflow or rewriting its history.

Orchestration must still consume the recorded operation prefix. Botpipe does not
remap inserted or reordered operations; indistinguishable requests at the same
position retain the same identity. Material observations belong inside recorded
operations, rather than unrecorded mutable closure or receiver state.

## Durable value codec

The ledger stores a narrow JSON value language. It supports JSON scalars and
containers plus explicit records for bytes, paths, dates, enums, sets, tuples,
artifact handles, Pydantic models, and dataclass instances. Model and dataclass
records use a versioned state format. Their fields are encoded recursively by
canonical Python field name, so aliases do not change the durable identity and a
nested model retains its concrete type. Pydantic records also retain which
fields were explicitly set and any allowed extra fields.

Replay restores model and dataclass state without calling constructors,
validators, default factories, `model_post_init`, or `__post_init__`. External
run arguments, provider responses, and human answers are validated once before
their normalized state is recorded. Internal workflow and activity calls retain
ordinary Python argument semantics. Validation may repeat after a crash before
its state was recorded, so validation hooks must remain free of external effects.
Codec traversal has depth and value-count limits and rejects cycles.

Typed records carry a codec-owned structural storage contract: concrete type
identity, declared field types and layout, enum membership and backing type,
flag storage, and supported exception storage. The contract excludes
implementation code, validators, default values, aliases, and source locations.
Source-only edits remain compatible; incompatible type or field changes fail
clearly without coercion or automatic migration. Before a resume accepts an
answer, changes limits, or starts work, it checks contracts throughout the
recorded run state.

Activity and child-workflow requests store keyword arguments as ordered
name/value pairs. Replay therefore preserves observable Python keyword order;
execution still receives ordinary keyword arguments.

`Flag` and `IntFlag` pseudo-members store their native integer value and name.
Enum records and contracts use native storage fields; public `name` and `value`
properties remain views of that state. An int-backed pseudo-member's integer
payload must match its stored value, or encoding rejects it.
Application attributes and populated custom slots are rejected; disposable
stdlib caches are not durable state. Restoration does not invoke application
construction hooks. A historical value that current construction would no longer
produce is restored without inserting it into the enum's shared cache, so reading
old state does not change the validation of new values. Equivalent standard
composites retain normal enum identity. Custom metaclass dispatch, attribute
lookup, or class construction prevents new entries in the constructor cache;
compatible existing entries can still be reused.

Datetime records retain wall time, `fold`, and fixed-offset timezone names.
Supported timezones are naive values and exact `datetime.timezone` instances;
`ZoneInfo` and custom `tzinfo` implementations are rejected because their
behavior depends on state outside this record format.

Define durable contracts at module scope so a new process can import their
concrete types. Types reachable through workflow annotations are registered
automatically, including generic arguments and nested fields. A local
polymorphic subtype that appears only at runtime cannot be reconstructed in a
fresh process; move that contract to module scope.

The automatic state codec deliberately refuses values whose complete state is
not represented by ordinary fields. This includes private fields, excluded
fields, secrets, custom serializers (including compiled core-schema serializers),
cached or unknown instance attributes, custom state hooks, and unrecognized
storage slots. Put such data in an artifact or
return a separate plain model designed as durable state. Records must use the
current explicit storage format; there is no legacy reader.

Recorded operation failures retain concrete exception types, native state, and
stored slot owners. Replay checks their storage contracts before restoring state
without application constructors. Contract incompatibility is a replay failure;
`ActivityFailed` is reserved for exception state that cannot be restored safely.

## Source observations

Source fingerprints describe revisions for inspection and optimization; they do
not gate ordinary replay. They capture bounded Python helper and contract
sources, including class behavior. Provider installations, external modules,
environment values, arbitrary closures and receiver state are not frozen.

Executable provenance is a rooted callable graph. Ordered, labeled edges describe
wrappers, partial bindings, referenced helpers, and class construction. Each
callable is expanded once per calculation; local references represent recursion
and shared dependencies. Fingerprinting and source capture share this dependency
description. Dependencies discovered through owned modules and classes join the
same bounded traversal.

Each workflow has an application source origin. It follows partials, bound
methods, and decorators to the application implementation; imported decorators
and helper bindings do not replace it. That origin selects relative prompt files.
SDK classification and source discovery use canonical resolved paths, including
symlinked installations. Source ownership is only a capture boundary, not stored
value compatibility or a requirement to preserve a directory layout.

Every execution appends start and end revision observations to the journal.
Inspection derives provenance from the complete history, so A → B → A remains
mixed. Missing observations remain explicit. Capture failure does not prevent
ordinary execution; frozen optimizer experiments still require verified source.
Mixed or unknown histories remain useful diagnostics but cannot establish a
verified single-revision baseline.

Graph expansion scales with distinct callables and dependency edges, rather than
the number of paths through shared helpers. Caches belong to one calculation so
later changes to code and bindings remain visible. The repeatable benchmark in
`benchmarks/callable_identity.py` measures fingerprinting, the workflow catalog,
and fake-provider execution and replay separately. Timing measurements complement
deterministic graph-size regression tests; they are not wall-clock CI thresholds.

An operation that may have started an external effect but has no committed
outcome is `interrupted`. Botpipe will not infer that the effect failed or rerun
it. The operator must record the observed response or explicitly authorize a
retry with `Botpipe.resolve()`.

Provider recovery and manual reconciliation use the same explicit outcomes:
`Completed(response)`, `Stopped`, `Running`, and `Unknown`. A completed matching
receipt is authoritative over operator input. Only a confirmed stopped attempt
without a completed response accepts a manual response or retry authorization.
Running and unknown attempts remain blocked; a recovery hook returning
`None` establishes no knowledge of termination. A native launch interrupted
before its process identity was recorded therefore remains uncertain.

One provider checkpoint model interprets saved state for normal execution,
recovery, manual reconciliation, and workspace ownership checks. The provider
lifecycle owns the corresponding decisions; the operation coordinator retains
artifact capture and validation work. These are provider-specific rules, not a
second control-flow language for workflows or a universal state machine for
inputs and activities.

| Durable fact | Permitted continuation |
| --- | --- |
| Preparation began; no dispatch intent exists | Finish preparation before dispatch. |
| Dispatch intent exists; no response is recorded | Recover the same attempt; uncertainty never authorizes redispatch. |
| Dispatch was rejected before effects | Finish restoring destinations, then replay the recorded rejection. |
| A completed response is recorded | Validate and capture that response without another provider call. |
| A validated value is recorded | Finish capture and the result checkpoint without revalidating. |
| Output validation failed | Finish rollback before replaying the failure or starting a separate repair operation. |
| An explicit retry is authorized | Reconcile the previous generation before preparing the next one; repeated authorization does not skip generations. |

Valid historical provider checkpoints are decoded into this model. Unknown or
contradictory checkpoint state blocks continuation and does not establish that
effects stopped. Retry generations remain within the existing operation record;
validation repair calls and physical dispatches retain their existing identities.

Adapters return `ProviderResponse` with string text, an optional string session
ID, and plain JSON objects for usage and metadata. Botpipe validates this
protocol before recording the response. Malformed responses and unexpected
exceptions after dispatch remain uncertain; they cannot silently coerce durable
values or establish that external effects stopped.

While a workspace has an unresolved uncertain effect, its durable workspace
claim blocks conflicting work in that directory, its ancestors, and its
descendants, even when clients choose different state directories. Read claims
can coexist; a write conflicts with overlapping reads or writes. Resolve the
recorded effect before continuing conflicting work.

The local coordinator stores claims in the account's Botpipe state directory,
outside the workspaces themselves. A short SQLite transaction checks and admits
claims atomically; OS locks identify live claim holders. Process death releases
the OS lock but does not establish that an orphaned native attempt stopped.
Unresolved reader and writer claims therefore survive until journal evidence
permits their release. Writer claims cover output validation and finalization,
not merely native response arrival. Nested operations delegate an explicit
parent lease; sharing a run ID does not exempt parallel branches from conflicts.
Provider claims also identify their owning operation. Root recovery preserves
those claims, and replay may recover only the matching operation's ownership.
A completed operation releases its own claim independently of unfinished work
elsewhere in the run. Broader ancestor claims remain in place when a child-root
workflow re-enters for recovery.

All cooperating processes must use the same coordinator and filesystem namespace
on one host/account. Shared workspaces across accounts, isolated containers, or
hosts need a separately supported coordination mechanism. Before switching from
the earlier per-directory-marker runtime, stop its native processes and reconcile
its unresolved runs using that runtime; mixed ownership protocols cannot
coordinate safely. The new protocol does not create lock files in read roots.

## Declared output transactions

Each provider attempt records exact output destinations and moves their previous
contents into backups before dispatch. Providers write directly to those paths.
Botpipe validates the typed response and the complete declared artifact set,
preflights durable value encoding, and publishes immutable snapshots before
committing the operation. A saved validated value and capture manifest allow
recovery to finish that commit without revalidating or redispatching.
The capture intent records every output's content digest before any snapshot is
published. Recovery verifies existing snapshots and requires unsnapshotted files
to still match that intent; edited files cannot silently become provider output.
If the process stopped before recording an inventory, resume remains interrupted.
An operator can approve the current files with `resolve(..., artifact_digests=...)`:
the mapping must name every declared artifact with its SHA-256 digest, or `None`
for an absent optional artifact. Reconciliation requires completed or confirmed
stopped effects and records operator provenance. Capture rechecks those digests;
later edits remain blocked. A provider text receipt alone cannot authenticate
the files that happened to remain in its workspace.

When a completed attempt fails output validation, rollback quarantines its
declared outputs and restores every previous declared file. The rollback journal
supports interrupted renames and detects conflicting changes. It requires a
stopped provider; it cannot undo arbitrary repository edits outside the declared
outputs. Replaying a successful capture reads immutable snapshots and leaves the
current mutable workspace untouched. Backup and quarantine renames require the
declared destinations and transaction directory to share a filesystem.

## Run limits

The client owns defaults for new runs. Each run persists its own immutable
`RunLimits`, inherited by its child contexts. Resume can increase that run's
operation limit or change its per-call timeout without changing client defaults.
All entry points reject boolean or fractional operation counts, nonfinite
timeouts, and nonpositive limits. These limits are separate from durable provider
budgets: resuming does not restart an existing provider-budget deadline.

## Operation boundary

Provider calls, activities, prompt-file reads, human input, worklist snapshots,
and artifact publication are operations. Runtime integrations can use
`current_run().operation(...)` for the same durable boundary.

```python
@activity(retry_safe=False)
def create_ticket(title: str) -> dict[str, str]:
    return remote_api.create_ticket(title)
```

Activities default to `retry_safe=True`, allowing unfinished calls to execute
again on resume. Use `retry_safe=False` for operations such as ticket creation
that require reconciliation before repeating. Exception retries remain opt-in
through `retries` (default `0`). Automatic retry requires both the saved attempt
and the current activity to permit it. Changing the flag cannot authorize
repeating an earlier unsafe attempt. Explicit `resolve(..., retry=True)` remains
the operator's authorization. This is not an exactly-once guarantee.

## Scopes and concurrency

The root workflow has a scope. Nested workflows and parallel branches derive
child scopes from deterministic call sites and ordinals. Worklist iteration
stays in the current scope; `Session.work_item()` derives stable provider
identity from the worklist and item ID. Each parallel callable receives an
independent scope, so scheduling order does not change operation identity.
Concurrent mutation through one shared session is rejected. Parallel provider
edits require an explicit isolated workspace per branch; read-only sessions may
share the application workspace.

`parallel()` records the ordered logical identities and explicit bound arguments
of its prepared branches, along with the settlement mode. Partial bindings retain
keyword order and serializable callable data; explicit names do not erase those
bindings. Nonserializable callable objects remain opaque references. Code edits
do not change that request, while a changed target or durable binding does.
Branch identity is checked before branch execution. Dynamically created
callables can only be checked when orchestration reaches that call site;
run-status bookkeeping may already have been committed by then.

Prompt paths use the branch's application source directory when it has one.
Branches composed only from SDK callables inherit their parent's source directory;
the workspace is the fallback for a root without application source. Additional
executable dependencies do not change this resource origin.

## Inspection

Before a run, inspection reports the callable signature, typed schemas, policy,
source, and source digest. Python topology is dynamic, so it does not claim to
enumerate future branches. After a run, inspection adds the operations and edges
actually observed. A completed run proves only the path taken for those inputs.

Inspection uses one journal snapshot of run, operation, and event records. A
shared read projection derives artifacts and usage from that snapshot without
hydrating application result models. Foreign-workspace ownership checks use the
journal's read-only unresolved-effects query; missing or malformed evidence keeps
the workspace fenced.
