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
Files become durable before the ledger refers to them. A workspace lock protects
one active run from another process.

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

On replay, a completed operation returns its recorded result. A changed kind,
scope, input, prompt, schema, or source raises a mismatch instead of silently
doing different work. Workflow versions label intentional releases; they do not
bypass source validation.

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

Within a run, checkpoints containing concrete model, dataclass, enum, or type
objects carry a versioned, deduplicated source capsule. The capsule and value
commit in the same SQLite transaction. Operation inputs also record the active
ownership boundaries, so manual resolution can capture a concrete result even
when its activity has no return annotation. These boundary locators are excluded
from operation fingerprints. Nested workflows inherit their caller's ownership
and add their own boundary. Before a
resume writes an answer, changes limits, or decodes state, Botpipe verifies the
capsules already recorded by the run. Owned type evidence covers source bytes,
loaded method code, properties, referenced helpers, and owned base classes.
Types outside the workflow ownership boundary are recorded as external by
qualified name; their installations and mutable configuration remain part of
the environment authors must preserve.

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
return a separate plain model designed as durable state. Legacy unversioned
model and dataclass records are rejected with a migration error; Botpipe never
passes them through current validation and silently changes their meaning.
Historical typed checkpoints without a source capsule are likewise refused on
resume because current source cannot be used to bless unverifiable old state.

Recorded operation failures carry source evidence for the concrete exception
class and classes that own its stored slots. Replay verifies that evidence
before restoring exception state without application constructors. Missing or
changed source evidence is a replay failure, not an `ActivityFailed` fallback;
that fallback is only for a verified exception whose state cannot be restored.

The automatic fingerprint pins the whole orchestration module and bounded,
owned Python helper and contract modules, including class behavior. Mutable
application files are outside this fingerprint. It is not an immutable process
or environment snapshot: provider installations, external modules, environment
values, and configuration semantics
can change outside that source bundle. Authors should bump
`@workflow(version=...)` when those dependencies change meaningfully and start a
new run when the original environment cannot be reproduced.

Callable identity describes executable behavior and supported explicit bindings,
including recursive partials, bound methods, and callable instances. It does not
serialize arbitrary receiver state, closures, or the process environment. Live
`Session` objects remain usable in ordinary Python composition. Code identity,
recorded prompt/data observations, and the full package provenance surface serve
different purposes: a package resource edit is not by itself a new replay gate.

Executable identity is a rooted callable graph. Ordered, labeled edges describe
wrappers, partial bindings, referenced helpers, and class construction, including
custom metaclass execution. Each callable is recorded once per calculation;
local node references represent recursion and shared dependencies. Object
addresses never enter the fingerprint. Sharing is observable Python behavior:
binding one callback twice differs from binding two independently created callbacks.
Fingerprinting and source capture use the same executable dependency description.

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
Running and unknown attempts remain blocked; a legacy recovery hook returning
`None` establishes no knowledge of termination. A native launch interrupted
before its process identity was recorded therefore remains uncertain.

One provider checkpoint model interprets saved state for normal execution,
recovery, manual reconciliation, and workspace ownership checks. The provider
lifecycle owns the corresponding decisions; sessions retain the artifact and
validation work. These are provider-specific rules, not a second control-flow
language for workflows or a universal state machine for inputs and activities.

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
fence blocks a different run from starting there, even when clients choose
different state directories. Resolve the recorded effect before continuing work
in that workspace.

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

`retry_safe=True` means retry is safe according to the activity contract. It is
not an exactly-once guarantee.

## Scopes and concurrency

The root workflow has a scope. Nested workflows and parallel branches derive
child scopes from deterministic call sites and ordinals. Worklist iteration
stays in the current scope; `Session.work_item()` derives stable provider
identity from the worklist and item ID. Each parallel callable receives an
independent scope, so scheduling order does not change operation identity.
Concurrent mutation through one shared session is rejected. Parallel provider
edits require an explicit isolated workspace per branch; read-only sessions may
share the application workspace.

`parallel()` records each prepared branch's complete workflow fingerprint and
uses the same definition to execute it. Its result carries the union of the
caller's and branches' source ownership, including types returned across package
boundaries. Branch identity is checked before branch execution. Dynamically
created callables can only be checked when orchestration reaches that call site;
run-status bookkeeping may already have been committed by then.
Historical parallel records without complete branch identity cannot be upgraded
from current code and are rejected on replay.

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
