# Provider-first implementation decisions

This document records implementation choices for PRD revision 1.2. The native
capability evidence document and acceptance report determine release readiness;
the examples here describe the authoring model.

## Ownership

A `Provider` family retains immutable operation defaults and one lazily selected
backend/profile. Derived configurations share that selection and their managed
`Session`. Each runtime resolves its own live adapter resources. This lets a
reused family keep its selected backend without retaining another runtime's
client, credentials, or transport. Explicitly attaching a provider to a runtime
requires using that same runtime inside a workflow.

The runtime owns adapters it constructs. Injected adapters remain caller-owned.
Closing an automatically configured provider closes its family's owned runtime;
closing a configuration with an explicitly supplied runtime leaves ownership
with that caller. Session identity and journal evidence outlive these resources.

## One operation, multiple attempts

Direct calls and workflow calls use the same provider coordinator. A direct
invocation is an ordinary recorded root with an importable internal entry point,
so `Botpipe.resume(run_id)` can recover it without application scaffolding.

Output repairs are generations within one operation. Each physical dispatch has
its own telemetry identity, request, native receipt, and artifact transaction.
A well-formed native terminal response advances the conversation before output
validation. Failed output validation rolls back the complete artifact set and
records feedback for a bounded repair. An uncertain native outcome requires
reconciliation before another dispatch.

Recorded request semantics govern replay. A current deployment ceiling gates
new physical dispatches, including repairs and authorized retries. It does not
rewrite the fingerprint of a committed operation or change the request used to
recover the original attempt. The policy intersection handles coupled network
settings and overlapping path scopes together.

## Native tool mediation

Exact command grants and autonomous read-only query require structured native
tool interception. The implementation uses Botpipe-owned bounded tools exposed
through supported native SDK/protocol interfaces while the native provider
retains its planning loop. A bridge must close the ambient tool inventory and
enforce the filesystem/process/network boundary before it may advertise support.

This is the architecture pivot described in PRD section 14: generic CLI shell
permission patterns cannot establish the required exact-argv contract. A finite
audited command recipe surface is the initial implementation target. The public
`generate`, `query`, and `run` contracts remain unchanged. Missing native or
platform proof remains a release gate, even when local mediator tests pass.

Query command execution uses a different recipe from exact generation grants.
Repository-wide git status cannot honor query's private-path exclusions and
narrower read roots. The query command instead counts lines in a bounded,
descriptor-confined snapshot with fixed trusted `wc -l`; only snapshot bytes
reach stdin. The existing exact git-status generation grant remains available
under its separately enforced workspace-wide envelope.

Pi's generate, query, and run operations use one pinned SDK and persistent
session manager. Delegating run to a different CLI release would introduce a
second native session-format and permission-transition contract. The SDK's
native built-in tool loop handles explicitly unrestricted run; generation and
query replace those built-ins with the mediated inventory. Output schemas guide
the prompt, while raw terminal text reaches the common validation/repair path.
This preserves completed-turn session advancement even for malformed output.

## Workspace coordination

Readers and writers use one local SQLite coordinator outside the workspace and
independent of run state directories. Claims compare canonical path ancestry:
reads may overlap, while writes exclude overlapping claims. Admission is atomic;
the coordinator transaction is not held during execution. Explicit parent leases
allow nested ownership without exempting conflicting parallel branches. Provider
claims carry their operation identity: restarting root orchestration cannot
release another operation's unresolved fence. Completion retires that operation's
claim independently of unrelated unfinished operations.

This replaces exact-directory marker probing. Ancestor markers cannot discover
all descendant readers, while creating markers throughout the tree requires
write access to read-only roots. A single execution lock would also serialize
unrelated sibling workspaces. Durable path claims solve those cases using the
same journal evidence that already governs unresolved effects. Native process
death alone does not retire a claim. The supported coordination boundary is one
host/account with a shared coordinator; mixed older marker runtimes and separate
host/container coordinators are outside that boundary. Native end-to-end A48
receipts remain a separate release requirement.

## Authoring comparison (A44)

| Job | Previous execution model | Provider-first form | Simplest credible alternative and remaining cost |
| --- | --- | --- | --- |
| Direct conversation | A Session carried execution methods and native continuation. | Reuse `p = Provider()` and call `p.generate(...)`; inspect returned `Result` identities when needed. | A native SDK call is shorter if durability is omitted. This API retains one handle plus an explicit `.value` for the answer. |
| Shared roles in a workflow | Session execution combined continuity, configuration, and prompts at each call. | Derive `planner = base.with_config(instructions=...)` and `builder = base.with_config(instructions=...)`; both share the initialized Session. | Passing role text on every call avoids named configurations but duplicates defaults. Derivation adds one line per reusable role. |
| Parallel work items | Explicit sessions and isolated editing workspaces were required for safe parallel work. | Use separate providers or `Session.work_item(...)` handles with isolated `workspace=` values and `parallel`/`aparallel`. | Bare concurrent calls are shorter but leave ownership and replay undefined. Workspace isolation and explicit sharing remain necessary author choices. |
| Typed decision | A generic model call and output schema could encode a verdict. | `Jev().decide(state=..., questions={"ready": Noul(...)})` returns the native typed answer and probability. | Calling TypeSafe directly is compact; the runtime adds recording, typed restoration, and conservative recovery. Question descriptors stay in one small module. |

Configuration selects a default explicitly; constructing a provider performs no
I/O and does not silently choose Codex. The selected `.botpipe-v2` schema adds
session ownership, affinity, and revision checks to the existing transactional
journal. The implementation rejects incompatible stores and provides no migration.
This is the current supported contract, not a prohibition on reusing older designs
or admitting compatible records in a future implementation. Explicit backend
selection and the schema boundary are documented setup choices.
