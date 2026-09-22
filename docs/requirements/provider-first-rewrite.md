# Botpipe: provider-first SDK and durable workflow runtime

**Product requirements and implementation specification — revision 1.3**

**Date:** 2026-09-22

**Target:** next incompatible major release (baseline package version: 1.0.0)

**Source baseline:** `mrauter1/botpipe`, merged main `ed4802dffc812105fca94d90a0d1edf16a731e2a` (PR #7). The inspected checkout at `9b58e77849bb968d2428201ea264f1ba7b0cf63d` has the same tracked file tree.
**Deliverable scope:** a specification for the rewrite, not an implementation or a release-readiness claim.

## 1. Product decision

Botpipe will provide a pleasant Python interface to provider capabilities and a durable runtime for composing those capabilities into repeatable processes. A developer can ask a question, execute a coding task, share a conversation between configured roles, obtain a typed probabilistic decision, or author a resumable workflow without changing the meaning of the underlying operation.

The central authoring rule is: **providers perform work; sessions carry conversation continuity; Python expresses the process; the runtime records operations and their outcomes.**

`Provider()` is the normal entry point: it selects the configured default backend. Vendor constructors such as `Codex()` are explicit opt-ins when an application intentionally depends on that backend. Managed conversation continuity is the default for conversation-capable providers. `Provider()` and `Provider(session=Session())` have equivalent continuity semantics; every conversation-capable construction gets its own session identity, initialized lazily when the backend is selected. `session=None` explicitly requests independent calls. Configuration derivation shares that lazy session binding, and the exact Session object once initialized, unless explicitly replaced.

The conversational operations form a clear progression: **`generate` answers from supplied context with commands denied by default; `query` can gather information through enforced read-only operations; `run` can make changes within policy.** `generate` can opt into exact, explicitly allowed read-only commands. Allowing a command does not grant write authority. Specialized `decide` and human-facing `ask_human` retain their distinct contracts.

**Revision 1.1 supersedes the earlier no-command meaning of `query`.** The no-command-by-default boundary now belongs to `generate`; query permits read-only commands as well as read tools. This change applies to examples, provider proof gates, streaming, and acceptance criteria throughout this document.

The rewrite preserves required product behavior, not the existing API or implementation structure. There will be one new SDK, one execution path, and one set of documentation. No compatibility wrappers, deprecated aliases, dual runtimes, legacy request shapes, or old workflow-language interpreters are required.

**Revision 1.3 corrects the execution-history constraint in revision 1.2:** backward compatibility with earlier journals and persisted execution state is not required, but neither reuse nor compatibility is prohibited. Choose journal implementations, schemas, and record formats on their merits for the new product. Retain or adapt an existing design when it is the simplest correct solution; do not replace it or break compatibility merely because it predates the rewrite. Supporting historical executions, including migration, is optional and must not weaken the selected durability, recovery, or evidence contracts. Required replay and compatible source-edit behavior remain unchanged.

### 1.1 Intended users and jobs

| User/job | Required outcome |
| --- | --- |
| Developer using an LLM or coding provider directly | A useful first call with a provider and prompt; no mandatory workflow, manager, or execution-record construction |
| Developer building a conversational helper | Consecutive calls continue a managed conversation; an independent call is explicit |
| Workflow author | Describe planning, implementation, review, human input, iteration, and parallel work in ordinary Python |
| Operator recovering interrupted work | Determine what completed, what can still act, and what requires reconciliation before any repeat execution |
| Developer sharing configurations | Derive planner, builder, and reviewer settings without duplicated configuration or accidental session cloning |
| Developer using specialized decision models | Preserve their native input and output contracts without pretending they are text-generating chat providers |
| Maintainer of packaged workflows and evaluation tools | Retain useful outcomes and evidence while reducing framework-specific machinery |

### 1.2 Outcomes that define success

1. A first direct call is as approachable as a small conventional SDK call.
2. Calls reveal their intent: `generate` uses supplied context and explicitly granted commands, `query` gathers information without mutations, `run` may act within policy, `decide` returns specialized decisions, and `ask_human` requests a person's answer.
3. Common operations behave the same directly and inside a workflow, including typing, validation, session selection, artifacts, errors, and provider restrictions.
4. Managed sessions, configuration derivation, and per-call overrides follow a small, documented set of rules.
5. Interrupted effects cannot become automatic duplicate dispatches merely because the API has changed.
6. Existing supported workflow outcomes remain available through the new API, with multiple required/optional provider-created artifacts intact.
7. Future adapters fit the capability boundary without changes throughout the runtime.
8. The final source tree, installation, examples, CLI, and test suite describe the new product consistently.

## 2. Scope, constraints, and freedom to simplify

### 2.1 Required scope

- Direct synchronous and asynchronous provider calls.
- Codex, Claude Code, and Pi adapters for generation, read-only query, and execution; a native JEV decision adapter; deterministic fake adapters for development and conformance tests. Section 7.5 defines mandatory versus optional capabilities and the release decision.
- Managed sessions by default on conversation-capable providers, explicit independent calls, shared-session configuration variants, and durable session scopes.
- Command-restricted `generate`, read-only `query`, effectful `run`, typed `decide`, typed results, streaming where supported, cancellation, and meaningful capability errors.
- Durable imperative workflows, activities, nested workflows, human input, parallel branches, worklists, limits, inspection, reconciliation, and compatible source edits on resume.
- Multiple provider-written artifacts, immutable captured versions, input snapshots, schema validation, and interrupted capture/rollback recovery.
- Packaged workflow, discovery, CLI, configuration, evidence/provenance, and evaluation functionality identified in the preservation inventory.
- Installation and documentation for the new major version, including a concise rewrite guide for existing authors.

### 2.2 Explicit exclusions

- Source compatibility with `Session.run`, `ask`, previous provider request/response protocols, graph/node APIs, historical autoloop projects, or old constructor shapes.
- An obligation to preserve earlier journals or persisted execution state solely for backward compatibility. Reading, inspection, import, migration, conversion, replay, resumption, reconciliation, and optimizer/history analysis of earlier records are optional, subject to section 2.3.
- An obligation to convert or restore native session bindings from earlier execution state; any supported restoration must satisfy the current identity, affinity, ownership, and revision contracts.
- A universal prompt-to-text interface for every backend.
- A mandatory Agent, Worker, Task, Factory, or Manager class just to hold a prompt and configuration.
- A second autonomous tool loop inside Botpipe when an execution provider already owns that loop.
- A distributed scheduler, hosted service, visual workflow editor, or generalized multi-tenant control plane.
- Exact-once external execution, arbitrary repository rollback, or automatic safety guarantees for user-written activity code.
- Unrequested feature expansion justified only by the availability of a pattern or dependency.

### 2.3 Compatibility boundary

Select one coherent journal contract for the new runtime. Reuse existing storage mechanisms and formats where they best satisfy the requirements; schema changes, version changes, and a fresh state directory must follow from concrete contract or implementation needs, not from a requirement to discard older designs. No parallel legacy runtime or compatibility layer is required. Compatibility that follows naturally from the chosen contract may be retained; readers or migrations may also be included when their product value justifies their total maintenance burden.

Run inspection, replay, resume, reconciliation, history-based labs, and optimizer evidence must validate records against the contracts required by the requested operation. A record's age alone neither qualifies nor disqualifies it. Read-only inspection or evidence use does not establish that a record can safely resume execution. Do not invent missing attempt identity, authority, session ownership, provenance, or measurements to make an earlier record appear compatible. No history backfill or old-to-new execution mapping is required. When no eligible evidence exists, retain the existing empty-evidence behavior, including zero optimizer provider calls.

An unsupported or unrecognized store must be rejected before mutation, with an actionable explanation and a fresh-state-directory option. Format/version validation remains necessary even when no historical compatibility is implemented. Do not silently reinterpret, overwrite, or delete unsupported state. The implemented format boundary and any supported conversion must be documented and tested. Recovery and compatible source-edit guarantees elsewhere in this PRD continue to apply in full to all executions admitted for replay or resume.

Existing names or algorithms may be retained where they are already good. A clean rewrite is a change in model and ownership, not a requirement to discard correct code. Remove redundant layers and compatibility branches; retain or adapt well-tested mechanisms when they satisfy the new contracts directly.

## 3. Fixed requirements and provisional design choices

The following requirements are fixed by this specification. A pivot must preserve them:

- Conversation continuity is the default for a conversation-capable provider; independent calls are explicit.
- `Provider()` selects the configured default backend; common examples and workflows do not hardcode a vendor.
- `generate` denies model-directed commands and autonomous tools by default. Its only tool exceptions are explicit command grants within a non-mutating ceiling.
- `query` permits authorized read-only operations, including enforceably read-only commands, but never provider workspace writes or external mutations. A command label or filesystem sandbox alone does not establish the full effect boundary.
- Workflow control flow is ordinary Python.
- Existing required capabilities and user-visible outputs survive the rewrite.
- Provider-created multiple artifacts remain first-class.
- Activity `retry_safe=True` remains the default; exception retries and uncertain-effect recovery remain distinct.
- Unsupported capabilities are explicit; adapters cannot silently drop controls or substitute another provider/model.
- There is no legacy API or historical-journal compatibility obligation. Existing journal designs and formats remain candidates on their merits; support for earlier records follows the validated contracts in section 2.3.

Internal module names, storage organization, adapter implementation techniques, helper names not fixed above, and the exact arrangement of configuration objects are provisional. They may change when a concrete alternative reduces total burden while passing the same behavioral scenarios.

The primary architecture candidate is configured provider values over one operation runtime. A stateful Agent abstraction and a universal executable/Task wrapper are comparison candidates, not planned extra layers. Introduce a new public abstraction only when it owns a coherent responsibility that ordinary functions, sessions, provider configuration, or run controls cannot express clearly.

## 4. Public concepts and ownership

| Concept | Owns | Does not own |
| --- | --- | --- |
| Configured provider | Stable configured-default or explicit backend selection, transport references, immutable default settings, optional default session reference, capability exposure | Workflow control flow, implicit authority to broaden policies, arbitrary global conversation state |
| Session | Logical conversation identity, native continuation binding, scope, affinity, and exclusive turn ownership | Execution of tasks, artifact transactions, retry authorization |
| Workflow | A repeatable process definition written as a Python function | A second graph representation or separately maintained route/state table |
| Run | One execution and its durable history, resource ownership, limits, pending input, and recovery state | The provider's native planning/tool loop |
| Operation | A recorded request, attempts, observations, and eventual outcome | A mandatory object users must construct for ordinary calls |
| Result | Validated value, immutable artifact handles, usage, and execution identifiers | A claim that all native side effects were rolled back |
| Artifact | Declared provider output or captured immutable evidence | A mutable live path masquerading as historical evidence |

The configured provider is intentionally stateful with respect to its referenced session. Its configuration remains immutable: deriving a variant does not mutate the original's settings. Native clients/connection pools may be shared internally without making their credentials or process handles serializable configuration.

### 4.1 Dependency shape

Public operation methods normalize intent and invoke the common runtime. The runtime coordinates policies, identity, journaling, session/workspace ownership, dispatch, validation, capture, and recovery. Provider adapters translate typed requests to native protocols and return native evidence. They do not independently implement workflow replay or a second artifact transaction system.

Workflow definitions, standalone calls, and CLI entry points converge on this boundary. Native response parsers, process runners, and evidence stores must not depend on public workflow implementations.

### 4.2 Implementation responsibilities and useful patterns

| Responsibility | Preferred shape | Reason |
| --- | --- | --- |
| Provider extensions | Small typed capability protocols and native adapters | Keep vendor variation at a replaceable boundary without forcing unrelated operations into one request type |
| Configuration | Immutable values with explicit derivation and referenced session resources | Make inheritance predictable without copying conversations or transport state |
| Execution | One operation coordinator with explicit attempt states | Keep standalone/workflow/async/streaming guarantees aligned |
| Durable records | Transactional journal plus durable file generations and commit pointers | Make interrupted publication and acknowledgement loss recoverable |
| Sessions/workspaces | Stable resource identity and exclusive ownership checks | Prevent history races and competing writers independently |
| Evidence/typing | Shared codecs, validation boundaries, immutable snapshots | Avoid duplicate normalization and historical evidence drift |
| Product workflows | Ordinary functions, focused schemas, small deterministic domain validators | Keep process intent readable without framework-wide managers |

These are responsibility boundaries, not a demand for one class per row or a rigid module count. Use composition and dependency injection at real I/O boundaries. Avoid service locators throughout business logic, generic repositories over every table, a command bus for ordinary function calls, or event-sourcing terminology without an actual replay requirement. The existing replay journal already supplies the relevant durable history.

## 5. Authoring contract

All code in this section describes the target SDK. It is not executable against the source baseline.

### 5.1 Direct use and continuity

```python
from botpipe import Provider, Session

provider = Provider()
provider.generate("Remember that the service uses PostgreSQL.")
answer = provider.generate("Which database does the service use?")
print(answer.value)

# An independent call does not replace the provider's default session.
independent = provider.generate("Explain database indexes.", session=None)

# Explicitly independent calls by default.
stateless = Provider(session=None)

# A new continuing conversation.
other = provider.with_config(session=Session())
```

Constructing `Provider`, `Session`, or a `with_config` variant performs no config-file reads, authentication, state-store writes, native adapter startup, commands, or model calls. Backend resolution and native sessions are lazy; there is no shared module-level default Session. The apparent default `Session()` semantics apply when the selected backend supports conversation; a session-free decision provider never materializes that implicit session.

### 5.2 Shared configurations and roles

```python
base = Provider()
planner = base.with_config(instructions="Create concrete implementation plans.")
builder = base.with_config(instructions="Implement the plan and verify changes.")

plan = planner.query(request, returns=Plan)
change = builder.run("Implement this plan.", input=plan.value)

# Independent continuing reviewer; settings inherited, history separated.
reviewer = base.with_config(
    instructions="Review the implementation critically.",
    session=Session(),
)
```

`with_config` returns a configured value retaining the same backend selection binding and capability surface; it does not re-select the current default. Omitted fields inherit; explicit nullable values clear; explicit collections replace. No implicit recursive merging of maps/lists and no deep copy or fork of conversation history. Unknown fields fail clearly. Derivation is a configuration operation and consumes no provider turn.

Provider-specific extensions must be namespaced and validated by their adapter. They cannot override a common contract or escape a policy ceiling. Reusable application behavior can be an ordinary function receiving a compatible provider; a role label is diagnostic metadata, not durable operation identity.

### 5.3 Operation signatures and results

The spelling `INHERIT` below describes an internal omitted-argument sentinel; callers do not import it.

| Operation | Required/common arguments | Result |
| --- | --- | --- |
| `generate(prompt, *, input=None, session=INHERIT, reads=(), allow_commands=INHERIT, returns=str, ...)` | Supplied context/history/read snapshots; no autonomous tools by default; explicit read-only command exceptions; no `writes` | `Result[T]` |
| `query(prompt, *, input=None, session=INHERIT, reads=(), returns=str, ...)` | Supplied context plus autonomous read-only discovery within authorized roots/services, including enforced read-only commands; no `writes` | `Result[T]` |
| `run(prompt, *, input=None, session=INHERIT, reads=(), writes=(), returns=str, ...)` | The same input conventions plus declared provider outputs and an optional workspace | `Result[T]` |
| `decide(*, state, questions, ...)` | Native structured decision inputs; no fabricated prompt, file workspace, or session | `Result[DecisionAnswers]` |
| `agenerate`, `aquery`, `arun`, `adecide` | Async equivalents with the same contracts | Awaitable corresponding result |
| `ask_human(question, *, returns=str)` | Typed human input in a workflow | Validated `T`, or durable suspension |

`reads` supplies recorded snapshots; it is not a grant to access arbitrary paths. `query` and `run` can also explore an effective workspace within policy. `generate` has no autonomous workspace exploration unless a specific allowed command provides it. Workspace resolution also determines relative snapshot/command paths. Neither `generate` nor `query` accepts `writes`, directly or through a vendor extension.

For `generate`, `allow_commands` is an immutable collection of exact argv tuples, for example `allow_commands=(("git", "status", "--short"),)`. Built-in generation defaults grant no commands. A selected profile, constructor, or `with_config` may explicitly configure generation grants; omission on a call inherits that generation-specific set, while `allow_commands=()` clears it for that call. Explicit collections replace rather than union. These grants do not inherit the commands available to `run` or `query`; a preceding turn cannot grant them. Inspection exposes the effective grants. Section 7.2 defines matching and enforcement. Complex command-pattern languages are not required for the first release.

Execution options include a label, finite positive timeout where enforceable, bounded output-repair attempts, and an optional policy that can only narrow enclosing policy ceilings. Explicit command grants select from permissions permitted by those ceilings; they never broaden a ceiling. A deny-by-default grant set is distinct from a deployment prohibition that cannot be overridden. The implemented names must clearly distinguish output repair from transport retry and uncertain-effect reconciliation. Do not carry forward a single ambiguous `retries` option for all three behaviors; use `output_retries` for validation repair in the new provider API.

`Result[T]` exposes at least `value`, `artifacts`, `usage`, `run_id`, `operation_id`, and provider metadata that is explicitly marked nonportable. A result is returned only after terminal response validation and required artifact capture commit. A direct call raises a structured error on failure; a workflow runner returns overall `RunResult` status. Do not switch between raw strings and result wrappers depending on the execution context.

`RunResult[T].value` is exactly the workflow function's returned value; there is no implicit Result flattening. A function returning `result.value` yields that application value. A function intentionally returning `Result[T]` yields `RunResult[Result[T]]` at the top-level runner. A nested workflow call returns its function value normally, while run status remains available through inspection. `RunResult.artifacts` is a run-wide collection keyed by producing scope/operation and artifact name, preserving all accepted versions without overwriting duplicate short names. `Result.artifacts` contains that operation's outputs only. Aggregating handles does not copy files or count usage twice.

No uniform text field is required for decision answers. Usage records preserve native units and identify what can be aggregated. Missing token/cost data remains unknown, not zero.

### 5.4 Configuration and runtime context

Keep `Botpipe` as the application/runtime entry point for workflow execution, inspection, and recovery. It supplies workspace/state-store location, default provider selection/configuration, and enclosing limits/policies. A simple direct provider call uses the same runtime services through a lazily resolved default runtime; it does not require an explicit `Botpipe` instance.

The public `Provider` is a configured-provider facade, not the adapter protocol and not a factory that unpredictably changes its Python type. `Provider()` stores a lazy default-backend selector and an implicit managed-session binding. `with_config` returns the same configured public type, sharing the selector and default-session binding while applying immutable setting overrides. Separate constructions do not share session state. Explicit constructors such as `Codex`, `ClaudeCode`, `Pi`, and `Jev` select their named backend; they may use the same internal coordinator without a parallel runtime.

Provider construction may receive an explicit `runtime=Botpipe(...)` resource reference. Selection resolves atomically at first effective use, before dispatch, in this order:

1. Inside a workflow, use the active run's recorded default-provider specification. An attached incompatible runtime/store fails rather than splitting the operation across journals.
2. Outside a workflow, use the explicitly attached runtime if present.
3. Otherwise, lazily resolve the standalone runtime and project configuration from the current workspace.

The selected backend/profile snapshot is then pinned for the provider and every `with_config` derivative, including derivatives with independent sessions. Derivation cannot change backend selection. A later directory/configuration change does not retarget an existing family; construct a new `Provider()` or an explicit backend value. A module-global provider therefore honors the active runtime on first use and remains pinned on subsequent uses. Concurrent first use resolves once atomically. Sharing the selection binding does not authorize sharing an incompatible state store or workspace-bound native conversation.

There is no implicit vendor fallback: if no default is configured, resolution raises an actionable `ConfigurationError` before dispatch. The project template documents how to select a default. A configured backend with a missing capability raises `CapabilityError`; methods never route to different backends to make a call succeed. In particular, if JEV is selected, `Provider().decide(...)` uses JEV without creating a Session; `generate/query/run` fail. Omitted session configuration adapts to the backend's declared capability, while an explicit `session` argument, including `None`, is rejected for a session-free decision backend.

A new root workflow records its default-provider specification (or its absence) and non-secret semantic settings. Children inherit that selection snapshot, with separate default session identities. Unresolved provider families use that snapshot; an already pinned family deliberately reused from another run retains its own selection. Record family selection and first-use alias relationships alongside session aliases, including when the family differs from the run default. Replay reconstructs that family's recorded binding; it must not re-resolve a previously pinned family against the run default. Fresh, not-yet-recorded families in a resumed run use the run snapshot. Changed project/CLI defaults apply to fresh families in new root executions. Explicit constructor/`with_config` code changes remain ordinary recorded-input compatibility checks, not a reason to overwrite historical requests. Missing/incompatible recorded adapters cause a restoration error, never automatic fallback.

Credentials are re-resolved when needed. Current deployment ceilings gate new dispatches, repair turns, retries, and future operations; they may narrow or block saved requests. They do not retroactively reauthorize or re-execute committed outcomes, or turn conservative receipt/status recovery of the same attempt into a new task dispatch. Inspection, saved-result replay, and cancellation remain available subject to access controls for the stored data and backend. No prior snapshot authorizes bypassing a tighter current ceiling.

Runtime references and native clients are resources, not serialized configuration fields. Explicit vendor constructors bypass default backend selection and do not absorb another backend's profile settings. They inherit common runtime defaults and may use only configuration explicitly associated with their selected backend.

The runtime control surface must cover `run/arun`, `resume/aresume`, `resolve`, `cancel`, `inspect`, and `runs`. `resume(run_id)` distinguishes a stored workflow run from a standalone one-operation run. Standalone recovery reconstructs the recorded request and adapter configuration, then performs recovery/validation/capture; it does not infer a new prompt or silently dispatch another task. `resolve(run_id, operation_id, retry=... | response=..., artifact_digests=...)` records the permitted reconciliation decision before resume. Explicitly supplied `None` is a real response, not an omitted argument.

Restoration requires the recorded typed contracts to be importable or supplied through an explicit contract registry on the runtime. Local classes and closures can execute but must produce an actionable restoration requirement if they cannot be resolved in another process. A missing contract must not cause a downgrade from typed validation to unchecked JSON or a new provider call. Registry entries are matched to the recorded structural contract before use.

`Provider()` is the normal spelling inside and outside workflows. `current_run().provider` is an optional memoized `Provider()` for authors who intentionally want one default conversation per workflow scope. Repeated access returns the same configured value; a separately constructed `Provider()` is a separate conversation. Its backend selection and session rules are otherwise identical. Explicit vendor constructors remain useful in backend-specific examples and integrations; a CLI default never rewrites them.

Effective model/instruction settings follow, from lower to higher priority: built-in adapter defaults, the selected project/provider profile with application/CLI overrides, configured provider/`with_config` settings, and permitted per-call overrides. Policy grants do not follow unrestricted last-writer-wins merging: deployment/run/workflow/provider/operation ceilings intersect, and a more local call cannot broaden them. Derivation may replace ordinary configuration and select generation grants, but cannot clear or broaden an inherited policy ceiling. Every dispatch records its effective non-secret settings and the adapter version.

Live provider/client/process objects must not be serialized as workflow input. Persist typed configuration and stable session references. Native authentication is resolved from the environment or referenced credential source when execution occurs, without putting credential values into journals or fingerprints.

### 5.5 Workflow and artifact example

```python
from pydantic import BaseModel
from botpipe import Artifact, Botpipe, Provider, workflow

class Plan(BaseModel):
    steps: list[str]

@workflow
def implement(request: str):
    base = Provider()
    planner = base.with_config(instructions="Create a concrete implementation plan.")
    builder = base.with_config(instructions="Implement and verify the requested change.")

    plan = planner.query(request, returns=Plan)
    implementation = builder.run(
        "Implement this plan and write the implementation and check reports.",
        input=plan.value,
        writes=(
            Artifact.md("implementation.md", required=True),
            Artifact.json("checks.json", required=True),
        ),
    )
    return implementation.value

result = Botpipe(workspace=".").run(
    implement, "Add CSV export.", task_id="csv-export"
)
```

The configured default must pass read-only-query conformance. A planner can inspect the repository through authorized read tools/commands. Use `generate` instead when planning only from supplied context. A reviewer that writes a report or executes ordinary project tests uses `run`: tests can execute project code, write caches, or contact services. A query may use only checks that are independently constrained to its read-only boundary. These examples specify target behavior, not a claim that native adapters already meet it.

## 6. Sessions: identity, continuity, and scope

### 6.1 Binding and override rules

| Expression | Contract |
| --- | --- |
| `Provider()` | Lazily select configured default; fresh managed-session binding for a conversation-capable backend |
| `Provider(session=Session())` | Equivalent continuity semantics |
| `Provider(session=None)` | Configured default with no continuity between calls |
| `Codex()` / `ClaudeCode()` / `Pi()` | Explicit backend choice; same default continuity rules |
| `p.with_config(instructions=...)` | Preserve lazy selection/session bindings and the exact Session reference once initialized, including explicit `None` |
| `p.with_config(session=Session())` | New conversation; no inherited transcript |
| `p.with_config(session=None)` | Derived independent-call configuration |
| `p.run(..., session=other)` | Override this invocation only |
| `p.query(..., session=None)` | Independent invocation; does not append to or replace the default conversation |

Session identity must not depend on Python object addresses, transport connection identity, thread scheduling, or a freshly generated random ID during every replay. Configuration cloning and logical operation identity are separate. Two calls with identical prompts remain different operations when executed at different durable positions.

### 6.2 Scope contract

Use lazy, atomic first-use binding. `Session()` creates a fresh handle without performing I/O. The first selected invocation binds that handle to a canonical durable identity before native dispatch. A workflow journal records the handle's first-use alias at a stable scope/operation position; later uses of that same handle refer to the same identity. On replay from workflow entry, reconstructed handles resolve through those recorded aliases. The runtime must verify the alias pattern as well as operation inputs: replacing one previously shared handle with two independent ones must not silently pass replay.

| Context | Required behavior |
| --- | --- |
| `Provider()` constructed inside workflow code | New construction obtains a new conversation; backend uses the run snapshot; replay reconstructs the saved identity through the recorded first-use alias |
| Provider constructed outside a workflow | Construction is allowed. First use binds it without depending on import timing; the journal records its selected identity and alias relationships |
| Same live provider deliberately reused across sequential runs | It continues the same canonical session. The record makes cross-run reuse visible; this is a consequence of reusing a stateful object, not a global singleton |
| Memoized workflow default provider | `current_run().provider` is one `Provider()` per workflow scope using the run selection snapshot; a new root execution gets a fresh default session binding |
| Nested workflow default | A child scope gets its own default provider/session; an explicitly supplied parent Session reference preserves intentional shared continuity |
| Independent call | `session=None` creates no reusable conversation binding; any native per-call thread ID is retained only as attempt/recovery evidence |
| Explicit task/work-item continuity | `Session.task(key)` and `Session.work_item(item, key=...)` resolve stable project/store/task/item identities and are recoverable across process starts |
| Explicit restoration of a standalone session | `Session.load(session_id, state_dir=...)` resolves a persisted handle with affinity and revision checks; it never searches for a similarly configured conversation |

Ordinary unnamed objects created anew after a process restart do not automatically continue unrelated earlier executions. Resume of a specific workflow uses its journal; cross-start continuity outside that replay uses an explicit stored/task/item reference. A module-global provider may be a useful configuration base; `base.with_config(session=Session())` inside a workflow deliberately gives that execution separate continuity.

The canonical session record carries an expected conversation revision. Reusable turns acquire exclusive ownership and check that revision before dispatch. A suspended workflow cannot silently continue after another run advanced its shared session: it fails with a session-history conflict and requires an explicit new-session/handoff decision. Committed earlier operations can still replay without touching the current native conversation. Unresolved attempts fence the session as well as any writable workspace.

Resume reconstructs from workflow entry, including session aliases; arbitrary mid-function restart is not promised. Persisted session references, not live provider/transport objects, can cross a durable child boundary. A handle already bound to an incompatible state-store namespace or native affinity cannot be silently rebound. Intentional cross-run sharing uses a common store and the same recorded identity.

The first-use binding/alias/revision model must pass A04–A06 before being frozen. If it proves more complicated than an equally expressive ownership model, use the pivot rule to simplify it while preserving default continuity and explicit sharing. Do not solve a replay issue by silently resetting a conversation.

### 6.3 Native affinity and concurrency

A session binds to an enforceable backend identity and compatible native continuation configuration. Backend changes, account changes, unsupported model changes, or incompatible workspace bindings must produce a specific affinity error; they must not silently reset history or claim a migrated native conversation. Explicit evidence/transcript handoff starts a new session and records the transition.

Only one invocation may extend a mutable session at a time. Overlapping attempts fail with a session-busy error before dispatch. The runtime must not silently choose a scheduling-dependent conversation order. Concurrent branches use separate sessions and independently appropriate workspaces.

Changing role instructions affects the current invocation; it does not erase prior messages or create independent judgment. A derived reviewer inherits history unless its session is explicitly changed. Generation grants and query restrictions are recomputed per invocation regardless of earlier effectful turns. Moving between `generate`, `query`, and `run` preserves conversation continuity while replacing tool permissions for that invocation; inability to enforce the new boundary is a capability error, not permission to reset history or retain broader native tools.

Continuing sessions should preserve the existing native message prefix and append new turns or supported instruction deltas, so providers can reuse their context cache. Repeating an unchanged role must not needlessly rebuild the history or append duplicate role messages. Role changes and explicit clearing must take effect through a supported incremental update where available; clearing must explicitly supersede earlier role guidance without deleting the conversation. Cache reuse never overrides current permissions or correctness, and retaining history alone is not proof of a cache hit. Native compaction and cache eviction remain provider-controlled.

Continuity is not available merely because a backend is called a provider. Session-free decision capabilities reject session arguments. Session inspection must expose logical ID, scope, affinity, and native binding status without leaking credentials.

## 7. Provider capabilities and enforcement

### 7.1 Shared interface by capability

Define small typed protocols for generation, read-only query, task execution, and specialized decisions. Reserve the public name `Provider` for the configured-default entry point; adapter protocols use distinct internal or capability-specific names. Concrete providers may implement more than one capability. Shared envelopes provide identity, usage, errors, evidence, and tracing; operation payloads retain their natural types.

Capabilities must express supported operations and constraints, including conversation continuation, tool-free generation, exact command grants, read tools, read-only command execution, structured output, artifacts, streaming, cancellation/confirmed termination, recovery, and enforceable permission modes. Validate the concrete request against the selected adapter/version/platform/configuration before dispatch. A boolean `supports_query` without its enforceable restrictions is insufficient.

Common semantic settings must have common meanings. Vendor-specific settings stay explicit. Substitution is promised only for new calls within a compatible capability contract; pending native sessions and uncertain attempts stay bound to their recorded backend. Completed operations replay their saved outcome without calling a newly selected provider.

### 7.2 Generation, read-only query, and command enforcement

| Operation | Context and discovery | Model-directed commands | Workspace/external mutations |
| --- | --- | --- | --- |
| `generate` | Supplied prompt/input, selected conversation history, recorded `reads`; no ambient tool discovery | Denied by default; only exact explicit command grants, still subject to read-only effects | Denied |
| `query` | The same context plus autonomous authorized read tools, repository inspection, and separately approved read services | Permitted only through the profile's enforced read-only command surface | Denied |
| `run` | Context and tools within enclosing policy | Permitted within policy | Permitted within policy; `writes` declares captured outputs, not all possible edits |

`generate` names production of a response; its result may be text, code-as-text, or a typed value. It does not write the generated content into the workspace. No filesystem, shell, browser, network, MCP, plugin, delegated worker, or code-execution tool is implicitly enabled. Explicit `reads` are runtime-snapshotted input, not autonomous tool permission. If the author opts into `allow_commands`, only those commands become available and the operation no longer promises zero command executions. An empty effective grant set guarantees no model-directed command execution. For arbitrary custom tools or mutating commands, use `run` with an explicit policy rather than extending `generate` with another general tool loop.

`query` is a non-mutating information-gathering operation. It can list/search/read authorized source material and execute an audited, constrained read-only command surface without listing each command in the user call. It cannot write, delete, rename, publish, update remote state, execute an unconstrained project task, or widen authority. A query profile must identify its read roots, tool/command surface, network services if any, and actual enforcement. The default local read scope is the effective workspace root intersected with deployment, run, workflow, provider, and per-call policy ceilings. Runtime-private state locations, paths/resources classified as credential-bearing by the effective profile, and explicit exclusions are denied. Profiles must enumerate their default exclusions; this does not promise automatic detection of secrets embedded in otherwise authorized content. Parent directories, sockets, and network services are not implicit. Additional roots/services require explicit configuration within policy. An explicitly empty local read scope disables local discovery rather than restoring the workspace default. Query can still answer from supplied context or other permitted read sources; blocked tool requests are denied, and an explicit request requiring unavailable local discovery fails with a targeted capability error. The portable baseline requires useful local listing, search, file reading, and read-only command execution on a profile that permits them; web/MCP/database reads are additional advertised capabilities. `reads=()` does not disable query discovery; use `generate` for that intent or narrow the query policy.

Command enforcement must satisfy these requirements:

An exact grant is exposed only through an interceptable structured native command invocation validated before process creation, or a Botpipe-owned command mediator while native generic shell/process tools remain disabled. A startup tool-name allowlist, post-launch approval hook, or unrestricted shell tool cannot implement `allow_commands`. The native provider retains its planning loop; mediation only checks and executes the selected permitted invocation. If the adapter cannot establish pre-execution enforcement, reject the requested grant before model dispatch. Persist and fingerprint the full resolved command envelope, not just the public argv tuple.

1. A generation command grant matches an exact argument vector, resolved executable identity, allowed working directory, and controlled environment. The enforcing profile supplies the fixed effective working directory, minimal environment, read roots, empty stdin, network denial, descendant constraints, and bounded execution/output limits; the argv tuple does not bypass these constraints. Resolve/pin the executable before dispatch; do not trust a model-controlled PATH or a same-named workspace binary. No string-prefix matching, implicit glob expansion, shell interpolation, or approval-prompt bypass qualifies as an allowlist.
2. Query commands must execute under a boundary that prevents workspace and external mutations. A label such as “read-only,” an HTTP GET method, or a tool's self-declared annotation is not proof. Review flags, aliases, startup/configuration files, external helpers, plugin loading, executable replacement, and symlink/path escapes. Deny mutable services, sockets, credentials, and network destinations outside the allowed read surface.
3. Both command paths deny uncontrolled descendants and indirect execution. Shells, interpreters, command substitution, pipes, redirection, hooks, and delegated processes must not bypass the permitted operation or command set. Trusted mediation/bootstrap code is separate from commands chosen by the model; enabling a trusted helper does not grant the model arbitrary helper arguments. The first release may reject commands requiring an unsupported descendant or expansion instead of adding a general command-language policy.
4. A generation grant authorizes command selection, not mutations. For example, an exact `git status --short` grant is usable only when its native configuration/helpers and filesystem/network effects are constrained. `git commit`, deployments, and arbitrary tests belong in `run`, even if a caller includes them in a generation grant. Invalid known requests fail before model dispatch; disallowed commands proposed during a turn are blocked before execution and recorded, never auto-upgraded to run.
5. Permission ceilings are fixed for each invocation and re-established on fresh and resumed native sessions, output repair, and operation transitions. Inherited run permissions, startup hooks, MCP servers, extensions, role instructions, and provider-specific settings cannot widen them. Prompt injection in read content is treated as data, not a new permission grant.
6. All material observations used by the model are recorded: supplied snapshots plus autonomous tool/command inputs, outputs or immutable references, exit status, relevant identity, and truncation. Keep bounded evidence; explicitly identify incomplete capture rather than claim reproducible inspection. A committed operation replays its result, not the live reads or commands.

The runtime may launch a fixed trusted adapter process, persist journal/session metadata, and capture returned values in Botpipe-owned state. These are not model-directed workspace actions. Inference transport is separately authorized from model-directed network access. This is an operational non-mutation contract over protected workspace/external state, not a claim that inference consumes no resources or read services create no audit logs. Adapter startup and maintenance must remain within their documented trusted boundary; arbitrary user/project hooks do not qualify.

Unsupported requested enforcement raises `CapabilityError` before dispatch. Prompts, refusals, permissive approval settings, or a filesystem read-only mode alone are insufficient proof. Local filesystem restrictions do not by themselves contain network effects, subprocess escapes, or plugin tools. A tool-free native profile proves generation only; it does not prove useful query discovery or selective command grants. Conversely, read-only shell access does not prove command-free generation.

Neither operation has a `writes` argument. To publish a returned value, use an explicit recorded persistence activity; provider-created reports use `run`. An explicit read-only command exception is intentionally available on `generate`, but the common case remains `provider.generate(prompt)` with zero tool grants.

### 7.3 Execution contract

`run` delegates the native execution loop to the provider within effective policy. It supports explicit workspaces, material reads, typed values, multiple output declarations, and managed continuation. It does not imply unrestricted permissions. No provider-specific option may exceed enclosing policy.

Botpipe must distinguish the trusted bootstrap process from commands invoked by the model; must establish owned process/session lifecycle where supported; and must retain enough receipts to recover the exact attempt. A detached child process or lost native response is not proof of stopped effects.

### 7.4 JEV and typed decision capabilities

`Jev().decide(state=..., questions=...)` preserves native Choice, Score, and Noul inputs and outputs. Retain option/rubric definitions, selected values, distributions, and native confidence fields where supplied. Noul's truth probability must not acquire a fabricated separate confidence field. Do not collapse a native distribution to a string verdict as the only retained result.

Batch independent questions against one state; dependent questions require subsequent operations. Record the model/version, state, question definitions, response, usage, and validation. No chat session, fake assistant message, filesystem workspace, or artificial file artifact is required. In a workflow, this remote probabilistic call is recorded and replayed like other effects.

An LLM adapter may implement the same decision shape if explicitly selected, but it must identify the actual backend and must not imply equivalent calibration or silently substitute for JEV. Shape validity does not establish decision correctness.

Expose typed decision descriptors through a small decision-capability module. For example, the proposed authoring form is:

```python
from botpipe import Jev
from botpipe.decisions import Noul

decision = Jev().decide(
    state={"criteria": criteria, "evidence": evidence},
    questions={
        "satisfied": Noul(
            instructions="Does the supplied evidence satisfy the supplied criteria?"
        )
    },
)
probability = decision.value["satisfied"].noul
```

These descriptors preserve the native question contract. They do not introduce an Agent class, implicit history, or a generic string-output conversion.

### 7.5 Provider proof gates

The release must include a versioned capability matrix for Codex, Claude Code, Pi, JEV, and fake adapters, with tested platforms/native versions and actual limitations. Current capability claims require native integration evidence in addition to fake tests.

**Required completed-release baseline:** Codex, Claude Code, and Pi must each provide `generate` with no commands/tools by default, generation with exact explicit read-only command grants, useful autonomous read-only `query` (local listing/search/reading and a constrained command surface), and `run`. All three must support managed continuation and shared-role configuration across those operations, adapter-validated typed outputs, run-created multiple artifacts, sync/async calls, and honest cancellation/recovery on declared supported profiles. JEV must provide native typed `decide` with durable recording/replay and configured-default selection. These requirements cannot disappear by relabeling an incomplete adapter as capable.

Optional capabilities include additional read services/connectors, advanced parameterized command grants beyond exact argv recipes, native schema enforcement beyond client validation, native session forks, and live streaming on profiles without a native event interface. Every advertised capability still requires evidence. A finite documented read-only command surface is sufficient; universal classification of arbitrary shell commands is not required or promised.

A development build may expose only proven operations and reject others. That does **not** satisfy the completed-release baseline. If Phase 0 cannot establish a required generation/query boundary, that blocks the complete rewrite release until a supported native control or enforceable mediation boundary passes conformance, or the user explicitly changes the requirement. Do not substitute another model/provider behind the selected provider or silently downgrade query to a context-only response. Moving the old no-command guarantee from query to generate is the explicit revision 1.1 product decision; further weakening is not an implementation pivot.

Phase 0 must prove command-free generation, exact command grant enforcement, useful read-only discovery, operation transitions on the same managed conversation, output contracts, cancellation, and recovery for each required adapter. Where the native interface lacks a guarantee, use a supported native SDK/protocol or enforceable mediation boundary. Botpipe must not quietly take over the provider's planning loop merely to mimic support; a necessary boundary change is an explicit architectural decision under section 14.

Continuation conformance includes changing role instructions and permitted settings on the same native session. An adapter must not silently ignore those changes, preserve an incompatible earlier system configuration, or reset history to make an override appear successful. Unsupported combinations fail clearly and identify the compatible alternative.

The research starting point, checked 2026-09-21, is deliberately more conservative than a product support claim:

| Adapter | Evidence available | Required proof or limitation |
| --- | --- | --- |
| Codex | App-server documentation describes threads/turns, output schemas, interruption, read-access controls, and per-turn sandbox policy [P1] | Tool-free generation and exact command-grant enforcement remain unproven by this research. Read-only sandbox settings are relevant to query but do not alone establish external non-mutation. Prove all three profiles and transitions; reject unsupported combinations. |
| Claude Code | The CLI documents built-in tool restriction/disable controls, separate MCP controls, and a restricted mode [P2] | Verify startup/settings, hooks/plugins, resumed sessions, and exact command mediation. Tool-disable controls inform generation; enabling a shell or read tools does not itself prove query containment. Native allowed-tool approval rules are not automatically exact command grants. |
| Pi | The SDK documents an all-tools disable option and separately configurable tools and resource loading [P3] | Prove generation with all native/extension tools closed, exact granted-command mediation, and a constrained read-only query surface. Disabling built-ins alone leaves extension/custom tool paths to check. |
| JEV | Official TypeSafe documentation describes state/questions and typed Choice/Score/Noul answers [P4] | Pin the actual native schema and version behavior. Do not invent a chat session, universal confidence value, or unsupported endpoint contract. |
| Fake adapters | Deterministic scripted outcomes and fault injection are under Botpipe's control | Exercise contracts without credentials, but never use fake success as proof of native enforcement. |

Supplied immutable read snapshots are available to all conversational operations. Botpipe reads authorized bytes as recorded input without granting native filesystem tools. This is sufficient for context-only generation; it is not a substitute for the required autonomous discovery capability of query. Native documentation is an investigation input, not integration proof.

## 8. One operation runtime

### 8.1 Direct and workflow calls

Every operation receives an execution ID and operation ID before dispatch. Direct calls automatically create a one-operation run with inspectable recovery evidence. Calls inside a workflow join its current run/scope. Cheap remote decision calls need a small record; they do not need workspace transaction machinery when no files are involved.

The runtime persists the effective request before dispatch: the resolved provider-selection snapshot, effective command grants/read scope, operation kind, logical position, provider identity, relevant non-secret configuration, instruction/prompt sources and rendered content, typed input, session binding, policy, read evidence, output contract, workspace, limits, and attempt identity. Store credential references or redacted configuration, never reusable credential values.

Record native session/turn locators as soon as they are observed so recovery can find the attempt. Publish a reusable conversation revision only from authoritative turn/termination evidence, with the associated response checkpoint. Session advancement and the response checkpoint must not disagree after a crash. A rejected typed answer may still represent a completed native turn; output repair continues from its recorded conversation state, not an invented pre-turn history.

A crash before the result returns must not make the run undiscoverable. Direct exceptions include run/operation identifiers; the state store and run listing locate attempts even when no result object was delivered. The state-store location is explicit in inspection and configurable without requiring every direct call to pass it.

Standalone session state and one-operation runs are persistent evidence, not an immortal process-global cache. Closing a provider releases owned transport resources without deleting the journal or historical artifacts. Retention/deletion is explicit operator policy; it may not remove state still referenced by an unresolved attempt. Application and standalone operations sharing a bound session must resolve to the same store/namespace or fail before dispatch.

### 8.2 Replay contract

Workflow resume re-executes ordinary Python control flow and substitutes committed operation outcomes. It does not serialize a Python stack. Material external reads, random values, clocks, subprocesses, and network calls that affect control flow belong behind provider operations or `@activity`.

Match stable scope/operation identity, recorded inputs, and compatible durable value contracts. Do not identify work by provider object identity or role label. Compatible implementation edits are allowed: committed operations retain saved outcomes and future operations use current code. An altered historical sequence/input/contract fails with a targeted replay mismatch. A completed run returns its saved result without re-running the workflow or applying revised budgets.

Restore committed typed values without re-running custom validators. Initial external inputs, human answers, and provider outputs are validated at their ingestion boundary. Internal function calls preserve normal Python argument semantics. Validation before commitment must be side-effect-free because interruption can require repeating it.

### 8.3 Attempt lifecycle and recovery

Separate the operation lifecycle from native recovery evidence. Operation states must distinguish pending, dispatched, observed terminal response, validating/capturing, committed, failed, and uncertain/interrupted work. Native recovery outcomes remain explicit: completed with authoritative response and stopped effects; confirmed stopped without a response; running; or unknown.

- Persist dispatch intent/attempt identity before launching effects.
- A completed operation reuses its saved value and artifacts.
- Recover the same attempt before authorizing any new attempt.
- A running or unknown attempt remains fenced; missing receipts and generic recovery exceptions do not prove termination.
- A recovered authoritative completion takes precedence over an operator-supplied substitute response.
- Manual retry or response reconciliation requires confirmed stopped effects where external writes are possible. Generation and query also consume inference and may advance a managed session: an uncertain read-only turn still fences that session and must recover the same attempt before any new turn. Non-mutation does not imply that blind redispatch is safe.
- A crash during output validation, capture, or rollback resumes that stage; it does not restart the provider merely because the final result was not committed.
- No exactly-once promise is made for external systems. The contract is durable evidence, conservative recovery, and explicit reconciliation when outcome is uncertain.

### 8.4 Activities and human input

`@activity(retry_safe=True, retries=0)` preserves the agreed default. `retry_safe` permits re-execution of an unfinished activity; `retries` controls additional attempts after known exceptions. Completed outcomes always replay. Automatic retry requires both the recorded attempt and current declaration to allow it. Editing a previously unsafe declaration to `True` does not retroactively authorize an uncertain earlier effect.

`ask_human` records a typed request and suspends with `awaiting_input`. Answers are durably validated and associated with the exact pending operation. Invalid or non-durable answers keep the request pending with a serializable diagnostic. An explicit `None` answer/result is distinct from an absent value. Parallel human-input requests must remain individually identifiable and answerable without being misreported as ordinary branch failures.

### 8.5 Nested and parallel work

Calling a decorated workflow from another creates a stable child scope and uses shared enclosing limits. `parallel` preserves branch identity and result order across resume. Preserve all-or-raise and collect-results behavior, with suspension/interruption handled as runtime control states rather than collected application exceptions.

Separate sessions do not provide workspace isolation. Independent writable branches require isolated workspaces or a declared nonconflicting ownership strategy that the runtime enforces. Shared source workspaces can be used only under an appropriate enforced read policy. Generate/query do not claim writer ownership merely because they read, but must not read a workspace fenced by an unresolved writer; fail with a workspace-busy diagnostic or use an explicit immutable snapshot. Concurrent reads of live files are observations, not a whole-repository snapshot; use a recorded immutable tree when consistency across reads matters. Retain workspace fences until native effects and interrupted capture/rollback are settled.

### 8.5.1 Synchronous and asynchronous composition

`@workflow` and `@activity` accept both `def` and `async def`. An async workflow awaits `agenerate`, `aquery`, `arun`, or `adecide` and awaits async child workflows/activities; their committed outcomes and failures replay with the same contracts as synchronous calls. `Botpipe.run` can drive an async root when it owns the event loop; `Botpipe.arun` is the entry point from an existing loop. Do not nest event loops implicitly or return a coroutine as a durable value. Unsupported sync-in-loop invocation fails with guidance to the async equivalent.

Provide `aparallel` as the asynchronous counterpart to `parallel`, preserving stable branch scopes, ordered results, settle behavior, and enclosing budgets. It may schedule supported sync callables through managed workers and async callables through tasks, while preserving runtime context. Raw scheduling of concurrent effects into the same unpartitioned workflow scope is unsupported and must be diagnosed; pure local async computation remains ordinary Python.

`ask_human` records and suspends immediately; it does not block a thread while waiting for a person and works from both sync and async workflows. No separate human-input API is needed solely for async code. Cancellation must propagate through awaited children and managed workers, settle their owned effects, and preserve pending human-input/control states during replay.

### 8.6 Limits and budgets

Preserve run operation limits, run timeouts, and nested provider budgets. Counts are reserved durably before dispatch. Initial calls, output repairs, and explicitly authorized retries consume provider turns; receipt recovery and committed replay do not. Parallel branches and nested workflows share enclosing counters atomically.

Scoped absolute deadlines include suspended time and survive resume. They cannot silently reset or extend. Explicit operator changes to permitted run limits are recorded as run-specific revisions and must not mutate application defaults for other runs. A completed run's limits remain unchanged.

Reject booleans, nonfinite values, nonpositive limits where positivity is required, and silently truncated integers. Timeout enforcement requires a backend that can establish stopped effects; otherwise reject the timed operation before dispatch. Expiration must not release a workspace fence while an effect can continue.

## 9. Artifacts, typed values, and evidence

### 9.1 Artifact contract

Preserve `Artifact.json`, `.md`, `.text`, and `.raw` or equally clear constructors with path, logical name, kind, schema, and required/optional status. A single operation can produce multiple independently validated files as well as a typed return value. The provider creates declared output files; the runtime captures immutable versions.

An artifact handle distinguishes the original provider destination from the captured immutable path, identifies its digest and producing operation/attempt, and supports reading the captured content. Downstream `reads` must resolve to the recorded version, not whatever currently exists at the destination. Missing optional artifacts are explicit absence; missing required artifacts fail validation.

Fresh path reads are snapshotted before dispatch as recorded observations. Prompt files and relevant source dependencies receive analogous evidence. Requested paths must respect policy and workspace boundaries, including symlinks and aliases; canonical ownership checks must not rely only on unnormalized strings.

### 9.2 Transaction and repair behavior

Preserve declared destinations before dispatch. Validate return values and declared files before committing an accepted result. Invalid attempts are quarantined; restore prior declared files or prior absence before an authorized output-repair attempt. Do not overwrite changes made by an unrelated writer. Arbitrary repository edits are not rolled back by this artifact transaction.

The atomic guarantee concerns the accepted result and complete captured artifact generation. It is not a claim that a provider's live edits to several workspace files are one filesystem transaction. Make artifact bytes durable before publishing their journal references; use an immutable generation/commit pointer or an equivalent recoverable protocol across filesystem and database boundaries. Every generation validates its complete expected inventory before acceptance.

Output repair is bounded and recorded as additional provider attempts under the same logical operation. It never implies permission to rerun an uncertain native effect. Every repair must retain the original operation kind, generation grants, and query read scope, and re-check session ownership, current policy ceilings, deadlines, provider turn counts, and workspace fencing. Validation failure never converts generate/query into run or expands command permissions.

When native completion exists but durable artifact inventory does not, reconciliation requires a complete expected digest/absence map for all declarations. Verify current content at reconciliation and again at capture. Conflicting digests, undeclared entries, missing required entries, or still-running effects prevent acceptance.

### 9.3 Structured outputs

Support the baseline's useful typed values: Pydantic models, dataclasses, enums, typed collections, primitives, paths, and Botpipe references as documented by the durable codec. Do not serialize arbitrary executable objects or treat object `repr` as a durable encoding.

Respect the user's schema configuration. Do not impose `extra="forbid"` globally. A workflow may choose a strict schema for its own contract. Provider-side schema constraints and client-side validation must be distinguished; if the backend needs a stricter wire schema, adapt it without silently changing the public acceptance contract or document/reject the unsupported request.

### 9.4 Worklists

Preserve stable item identifiers, source artifact association, explicit selectors, safe item directory keys, status updates, and immutable artifact versions. Iteration uses the recorded selection even when completion updates the underlying list or the live source changes. A selected item must not disappear or be visited twice because a process resumed. Work-item sessions attach to stable worklist/item identity.

### 9.5 Source and execution evidence

Retain execution-revision start/end observations, logical callable identity, source/prompt/package fingerprints when verifiable, and explicitly unverified provenance when source cannot be established. Dynamic/nested callables may still execute; do not fabricate verified evidence for them.

Mixed-revision or unverified executions cannot become verified evidence for one source revision merely because later execution returns to that revision. Source snapshots are observations and attribution aids, not blanket code-hash locks on resume. Evidence references must remain useful when artifacts are exported or inspected from another path.

## 10. Streaming, cancellation, and failures

### 10.1 Streaming surface

Provide `stream(prompt, *, operation="generate" | "query" | "run", ...)` and `astream(...)`; the `operation` selector is required. The selected operation determines allowed arguments and permissions: run streaming may declare `writes`; generate/query streaming may not. Generation command grants and query read-only restrictions apply unchanged. Streaming observes one invocation, not a second dispatch or a second implementation of execution semantics.

Return a stream object with ordered normalized events, `run_id`, `operation_id`, a terminal `Result`, and cancellation. Preserve native event metadata without claiming every backend emits identical tool/thought/token events. Never synthesize hidden reasoning or normalize vendor-specific details into false guarantees.

The canonical lifecycle is a context-managed stream. Exiting the context before terminal completion requests cancellation and settles or records uncertainty before releasing owned resources. Obtaining the final result does not dispatch again. Merely pausing event consumption does not authorize another session turn. If live streaming is unavailable, report that capability; do not label a buffered final response as live streaming.

Live partial events are observation, not committed workflow values. Durable decisions use the terminal result. On replay, return the saved terminal outcome and an explicit replay indication; do not fabricate a live token history. Durable workflow effects based on intermediate chunks are outside this release's streaming contract and must not be presented in examples as recoverable behavior.

### 10.2 Cancellation

Sync timeout, async task cancellation, explicit stream cancellation, and run cancellation converge on one stop/recovery path. Distinguish a cancellation request from confirmed stopped effects. Propagate cancellation to the owned provider attempt, wait for authoritative termination within a bounded control timeout, and retain an uncertain/interrupted state when confirmation is unavailable.

No cancellation path may mark success, silently resubmit the work, release writer ownership prematurely, or let a worker thread continue mutating a supposedly stopped session. A cancellation of observation must not be mistaken for evidence that a remote/native task ended.

### 10.3 Errors and diagnostics

Use a small typed error taxonomy covering invalid configuration, unsupported capability/policy, session affinity/busy/scope errors, output validation, replay mismatch, run busy, budget exhaustion, pending human input, provider failure, and uncertain effects. Include actionable context and run/operation/attempt identifiers when available. Preserve native diagnostic detail without exposing credentials.

Validate adapter responses independently of model output: native identifiers and text fields have declared types; usage/metadata are finite, bounded, serializable data. A malformed adapter response after dispatch cannot be treated as evidence of stopped effects. Consult authoritative lifecycle evidence; retain uncertainty when termination or outcome cannot be established. This differs from a well-formed terminal response whose user-requested output schema fails and can enter bounded output repair.

Errors must explain the violated contract and the concrete next action, such as selecting an enforceable provider profile, using a new session, supplying an isolated workspace, answering pending input, or reconciling a stopped attempt. Ordinary provider errors must not be translated into misleading model refusals.

## 11. Preservation inventory and application migration

The inventory is grounded in source, current exports, manifests, documentation, and behavioral tests at the baseline. All repository tests under `tests/` are collected by the current configuration; the inventory collected 794 tests. This is a collection count, not a claim that this planning task established 794 passing tests. Existing tests are requirements evidence, not an API compatibility suite to preserve unchanged.

### 11.1 Core capability preservation

| ID | Existing capability to preserve | Target requirement | Primary baseline evidence |
| --- | --- | --- | --- |
| C01 | Sync/async imperative workflows, nested scopes, typed ingress | Sections 5 and 8; one execution path and normal Python control flow | `runtime.py`, `tests/test_runtime_acceptance.py`, `tests/test_ingress_and_limits.py` |
| C02 | Continuing run/task/work-item conversations | Section 6, with managed provider defaults replacing Session execution | `sessions.py`, `tests/test_sessions.py`, `tests/test_worklists.py` |
| C03 | Compatible source edits and committed result replay | Stable operation prefix and durable contracts; no blanket source-hash replay gate | `tests/test_mutable_replay.py`, `tests/test_runtime_corrections.py` |
| C04 | Activity retry default and explicit unsafe reconciliation | Recorded/current retry permission intersection; known exceptions separate | `tests/test_activity_defaults.py`, `tests/test_flag_state.py` |
| C05 | Provider dispatch checkpoints and four-state recovery | Exact attempt/generation recovery and native session restoration | `provider_checkpoints.py`, `tests/test_recovery_outcomes.py`, `tests/test_provider_checkpoints.py` |
| C06 | Complete native process containment | Verified owned process groups on POSIX and suspended-start Job Object containment on Windows, or an equally proven replacement | `processes.py`, `tests/test_processes.py`, `tests/test_providers.py` |
| C07 | Writer ownership across clients/state directories | Cross-process workspace fencing; corrupt or missing foreign evidence cannot free an uncertain writer | `tests/test_runtime_acceptance.py`, `tests/test_recovery_integration.py` |
| C08 | Multiple outputs and artifact attempt generations | Full-set validation/capture, required/optional semantics, immutable handles, quarantine and rollback | `tests/test_artifact_attempts.py`, `tests/test_artifact_rollback.py`, `tests/test_artifact_reconciliation.py` |
| C09 | Durable codec and one-time validation | Restore committed model/exception/enum/reference state without custom validator side effects | `codec.py`, `tests/test_codec_state.py`, `tests/test_codec_corrections.py` |
| C10 | Human questions, answers, diagnostics, replay | `ask_human`; invalid answers remain pending and correctly targeted | `tests/test_input_acceptance.py` |
| C11 | Parallel scopes and mutable worklists | Ordered branch results, stable selection and item identities, isolated sessions/workspaces | `worklists.py`, `tests/test_worklists.py`, `tests/test_workflows.py` |
| C12 | Run limits and provider dispatch budgets | Journal-backed shared counts, non-resetting deadlines, explicit run-local revisions | `tests/test_budgets.py`, `tests/test_ingress_and_limits.py` |
| C13 | Prompt files, strict templates, source observations | Recorded rendered inputs and source evidence; unavailable provenance explicit | `prompts.py`, `tests/test_prompt_contracts.py`, `tests/test_prompt_source_context.py` |
| C14 | Callable/package/source evidence and portable references | Honest mixed/unverified attribution; bounded capture and inspection | `provenance.py`, `tests/test_source_records.py`, `tests/test_portable_source_records.py` |
| C15 | Discovery, project configuration, CLI operations | Section 12; no import side effects during listing; typed invocation and useful exit states | `discovery.py`, `config.py`, `cli.py`, `tests/test_discovery.py`, `tests/test_cli.py` |
| C16 | Commit acknowledgement recovery | Confirm the exact committed projection after acknowledgement loss; otherwise retain uncertainty | `storage.py`, `tests/test_checkpoint_recovery.py`, `tests/test_journal_reads.py` |
| C17 | Physical dispatch evidence and usage | One record per actual attempt, provider/model/effort identity, timing, partial/final usage, and revision attribution | `dispatches.py`, `tests/test_dispatches.py`, `tests/test_evidence_profiles.py` |

Do not discard a behavioral test because it imports `Session.run` or another removed symbol. Translate the scenario into the new public API. Exact aliases, legacy recovery return shapes, and old manifest readers can disappear after their useful behavior has a new contract.

### 11.2 Packaged workflows

| ID / workflow | Required behavior and outputs | Rewrite acceptance |
| --- | --- | --- |
| W01 — Ralph Loop | Plan `work.json`; independent plan review; persistent ordered work items; implement/review feedback loop; durable completion; plan and item review reports | A rejected plan is revised; a rejected item is reworked with the same item session; accepted items are not repeated on resume; return the completed immutable worklist. Artifact-producing reviewers remain `run`. |
| W02 — Devloop and docloop | Phase-plan contract, plan/implementation/test/repair/audit reviews, preserved completed phases, stable active phase during repair, implementation retry after failed tests, final `passed`/`blocked`/`needs_followup`, bounded child follow-up | Preserve evidence and result paths. Docloop or skipped-test mode emits explicit reduced-assurance evidence and no test turns. Child artifacts cannot overwrite parent artifacts; follow-up depth remains bounded. A skipped test is not a passing test. |
| W03 — Goal | Persistent objective/subgoal state; `set`, `status`, `pause`, `resume`, `clear`, `edit`, and `replan`; replacement questions; dependency validation; priorities and active subgoal; plan/work/final verification; repeated-blocker termination; resource accounting | Exercise every action, missing/replacement-objective question, replan, blocker, budget limit, and completion path. State I/O is recorded/deterministic, committed subgoals are not repeated, and repair turns count toward usage. |
| W04 — Image to game | Resolve explicit/inferred/prompt-derived image references; ask on missing/invalid/ambiguous inputs; build and audit a playable-game goal; invoke Goal as a durable child; publish reference contracts, child receipt, and final report | Preserve fidelity, playability, affordance, persistence, browser audit, screenshot/comparison gates, and complete/blocked/budget-limited mapping. Reference scanning is a recorded observation. |
| W05 — Code to workflow | Bounded source manifest and trace corpus; independent behavior/design/build verification; local rework and backward replan; discoverable materialized workflow package and publication receipt | Capture source deterministically; validate behavioral coverage and package discovery/equivalence; publish only validated material. All generated prompts/examples/imports use the new SDK. |

Workflow identifiers can remain because they describe useful products, not old API shapes. CLI catalog/option spellings are part of the API clean break: old short aliases are not a compatibility requirement. This is an intentional naming migration, not permission to remove their underlying actions. Each currently exposed workflow outcome must remain discoverable under one documented canonical reference; the author migration guide maps removed names to that reference. Retain an alias only if it serves the new product independently of compatibility.

### 11.3 Labs workflows

All fifteen labs workflows remain in scope. Shared helper code may be simplified, but it must preserve typed inputs, explicit phase order, independent verification, required immutable outputs, phase evidence, and final results. Local rework repeats its phase; a replan returns to its declared earlier checkpoint; a question/blocked state suspends through `ask_human`; terminal failure remains distinct.

| ID | Workflow | Required outcome |
| --- | --- | --- |
| L01 | `task_to_candidate_workflow_set` | Ranked candidates, comparison/fit-gap evidence, structured summary, next action |
| L02 | `candidate_workflow_to_adapted_execution_plan` | Fit analysis and adapted plan with deterministic callable-parameter validation |
| L03 | `task_to_workflow_strategy` | Explicit run-existing/compose/adapt/create-new strategy and next-action package |
| L04 | `workflow_idea_to_workflow_package` | Frame/design/build/evaluate; discoverable candidate package; validation without substituting authoritative files |
| L05 | `workflow_package_to_composable_building_blocks` | Candidate decomposition, contracts, isolated validation, verification summary; no authoritative-source mutation |
| L06 | `workflow_run_history_to_failure_modes` | Bounded journal-history evidence admitted under section 2.3, failure manifest, recurring weaknesses, ranked opportunities; support for earlier records is optional |
| L07 | `workflow_to_eval_suite` | Benchmark/edge/adversarial cases, rubric, manifest validation, optional accepted evaluation-case handoff, content-derived source/suite identities; no unperformed evaluation claim |
| L08 | `workflow_and_eval_to_refined_workflow_package` | Selected candidate, frozen authority, candidate overlay, isolated checks, verification/refinement package, optional paired comparison; no automatic promotion |
| L09 | `workflow_portfolio_to_operating_system` | Catalog/health evidence, lifecycle decisions, change candidates, governance package; deterministic cross-artifact publication checks |
| L10 | `company_operation_to_recursive_improvement_cycle` | Company pressure/priority/candidate evidence, consistent categories/priorities, next-cycle package; no hidden execution |
| L11 | `investigation_request_to_evidence_pack` | Scope, source register, gaps, findings/counts, and evidence readiness |
| L12 | `security_finding_to_verified_remediation` | Durable investigation child, assessment, verified remediation/residual risk, closure package; deterministic child-readiness and publication checks |
| L13 | `incident_to_hardening_program` | Timeline, affected surface, blast radius, gaps, ranked causes, mitigations/validation, hardening backlog and communications |
| L14 | `release_candidate_to_go_no_go` | Release/test/operations/rollback evidence, risks/blockers, go/conditional-go/no-go decision, communications package |
| L15 | `workflow_run_traces_to_optimization_candidates` | The optimizer evidence, candidate/review, and publication contract below |

Use `generate` for an artifact-free typed judgment over supplied immutable evidence with no tool access; use `query` when the reviewer must gather more evidence through enforced read-only operations. Keep `run` for reviewers that execute project checks with possible effects, use mutating tools, or write reports. Choose from required effects, not a blanket reviewer-to-query substitution.

### 11.3.1 Normative artifact preservation baseline

The following source-declared outputs are the minimum inventory for the fourteen ordinary labs. The optimizer lab has its separately specified generation in section 11.4. Required/optional flags, JSON field contracts, output-key derivation, and deterministic cross-document checks are defined by each workflow's `workflow.py`, `contracts.py`, `params.py`, applicable specs, and `labs/workflows/publication_validation.py` at the pinned baseline. These are normative preservation references, not merely illustrative documentation.

Phase 3 must translate these declarations and validators into an explicit new contract inventory and migrate all consumers together. Names or schemas can change under the clean API break only with a recorded old-to-new semantic mapping; dropping a document or field that carries a distinct required outcome is not a naming change. Conditional, dynamically materialized package files and evaluation/publication records are additional to this literal-output table.

| Workflow | Source-declared output inventory |
| --- | --- |
| `candidate_workflow_to_adapted_execution_plan` | `adaptation_request_brief.md`, `adaptation_success_criteria.md`, `workflow_fit_assessment.md`, `step_adaptation_matrix.md`, `adapted_execution_plan.md`, `proposed_workflow_parameters.json`, `adapted_execution_summary.json`, `adapted_execution_next_action.md` |
| `company_operation_to_recursive_improvement_cycle` | `company_operation_brief.md`, `recursive_improvement_criteria.md`, `company_pressure_map.md`, `recursive_improvement_priority_matrix.md`, `recursive_improvement_candidates.json`, `recursive_improvement_cycle.md`, `recursive_improvement_summary.json`, `recursive_improvement_next_actions.md` |
| `incident_to_hardening_program` | `incident_scope_brief.md`, `response_objectives.md`, `evidence_intake_register.md`, `incident_timeline.md`, `affected_surface.md`, `blast_radius.md`, `observability_gaps.md`, `evidence_gap_register.md`, `cause_hypothesis_ranking.md`, `immediate_mitigation_plan.md`, `validation_plan.md`, `incident_summary.json`, `hardening_program.md`, `hardening_backlog.json`, `follow_up_owners.md`, `stakeholder_communications_draft.md`, `incident_resolution_package.md` |
| `investigation_request_to_evidence_pack` | `investigation_scope_brief.md`, `evidence_intake_plan.md`, `evidence_pack.md`, `source_register.json`, `evidence_gaps.md`, `investigation_summary.json` |
| `release_candidate_to_go_no_go` | `release_scope_brief.md`, `decision_criteria.md`, `evidence_intake_register.md`, `release_inventory.md`, `test_evidence_pack.md`, `operational_readiness.md`, `rollback_readiness.md`, `blocking_issues.md`, `go_no_go_assessment.md`, `risk_register.json`, `decision_summary.json`, `release_decision_package.md`, `release_communications_draft.md` |
| `security_finding_to_verified_remediation` | `security_assessment.md`, `threat_scenario.md`, `remediation_acceptance_criteria.md`, `remediation_plan.md`, `verification_evidence.md`, `residual_risk.json`, `security_remediation_package.md`, `security_remediation_summary.json`, `security_next_action.md` |
| `task_to_candidate_workflow_set` | `candidate_request_brief.md`, `workflow_fit_criteria.md`, `workflow_comparison_matrix.md`, `fit_gap_analysis.md`, `candidate_workflow_set.md`, `candidate_workflow_set_summary.json`, `candidate_workflow_next_action.md` |
| `task_to_workflow_strategy` | `task_strategy_brief.md`, `workflow_selection_criteria.md`, `strategy_decision.md`, `workflow_strategy_package.md`, `strategy_summary.json`, `strategy_next_action.md` |
| `workflow_and_eval_to_refined_workflow_package` | `refinement_request_brief.md`, `refinement_success_criteria.md`, `workflow_refinement_plan.md`, `candidate_change_manifest.json`, `candidate_workflow_manifest.json`, `candidate_implementation_notes.md`, `candidate_verification_report.md`, `refinement_summary.json`, `refinement_next_action.md` |
| `workflow_idea_to_workflow_package` | `workflow_idea_brief.md`, `candidate_selection_criteria.md`, `workflow_design.md`, `workflow_contract.json`, `workflow_evaluation.md`, `workflow_package_summary.json`, `workflow_next_action.md`, `workflow_package_manifest.json`, `implementation_notes.md` |
| `workflow_package_to_composable_building_blocks` | `decomposition_request_brief.md`, `decomposition_success_criteria.md`, `decomposition_plan.md`, `building_block_contracts.json`, `candidate_decomposition_manifest.json`, `candidate_decomposition_notes.md`, `decomposition_verification_report.md`, `decomposition_summary.json`, `decomposition_next_action.md` |
| `workflow_portfolio_to_operating_system` | `portfolio_governance_brief.md`, `lifecycle_criteria.md`, `portfolio_health_analysis.md`, `lifecycle_recommendations.json`, `portfolio_change_candidates.json`, `workflow_portfolio_operating_system.md`, `portfolio_operating_summary.json`, `portfolio_next_actions.md` |
| `workflow_run_history_to_failure_modes` | `diagnostic_scope_brief.md`, `run_history_scope.md`, `failure_mode_map.md`, `failure_mode_manifest.json`, `recurring_weak_points.md`, `improvement_opportunities.json`, `improvement_opportunities_summary.json`, `diagnostic_next_actions.md` |
| `workflow_to_eval_suite` | `evaluation_request_brief.md`, `evaluation_dimensions.md`, `benchmark_case_matrix.md`, `edge_case_matrix.md`, `adversarial_case_matrix.md`, `eval_case_manifest.json`, `eval_rubric.md`, `workflow_eval_suite.md`, `workflow_eval_suite_summary.json`, `workflow_eval_next_action.md` |

In particular, the security-remediation workflow consumes the investigation child's `investigation_scope_brief`, `evidence_pack`, `source_register`, `evidence_gaps`, and `investigation_summary` artifact keys. Preserve that complete evidence dependency and the deterministic child-readiness checks, or migrate both contracts atomically to an equivalent explicit mapping. Generated workflow packages must also include their discoverable module/manifest and all referenced prompts/assets.

### 11.4 Optimizer, refinement, and evaluation

The authoritative baseline includes `botpipe_optimizer`, the optimization-candidate lab, and its evaluation/refinement consumers. The exported and tested observation-ranking/report behavior in `optimization.py` is in scope even where its API looks older. Requirement documents establish intended contracts; they are not evidence that every desired behavior already passed a test.

| ID | Required contract |
| --- | --- |
| O01 — Evidence | Capture bounded inspected journal/physical-dispatch evidence admitted under section 2.3; group exact source surfaces and revisions; preserve unknown/mixed identities and provider/model/effort strata. Support for earlier records is optional and must satisfy the same evidence requirements. Reliability, token, and dispatch-time metrics are deterministic measured values, not provider prose. |
| O02 — Candidates | Preserve producer-prompt, verifier-rubric, token, workflow, and evaluation-case candidate kinds; strict content-derived candidate/review/handoff identities; normal proposal plus independent review; bounded history/bytes/turns/deadlines. Empty evidence makes zero provider calls. |
| O03 — Publication | Publish immutable content-addressed generations with an atomic root receipt. Validate the full hash/size/identity chain when loading. An unevaluated recommendation remains explicitly `not_evaluated`. Never mix files from different generations. |
| O04 — Refinement | Freeze the editable surface and execution tree before provider edits. Permit bounded changes/additions/removals only inside the candidate boundary. Validate in isolated arms with argv execution, no shell interpolation, bounded diagnostics, and unchanged authoritative source. |
| O05 — Paired evaluation | Freeze evaluator/spec/cases/order/repetitions/settings/thresholds/limits. Run baseline and candidate arms against the same plan and validate complete atomic results. Once a paired attempt has launched, resume must never relaunch either arm, including after generic explicit retry authorization. A valid saved comparison can recover it; absent or invalid evidence leaves it interrupted or fails validation. A genuinely new evaluation requires a new explicit evaluation invocation/attempt identity. Preserve improved/regressed/no-material-change/inconclusive outcomes; never auto-promote. |
| O06 — Consumers | Accept only verified candidate/publication records; preserve source-candidate and suite identity; reject tampering, drift, oversized inputs, or mismatched evidence. Evaluation-suite generation alone is not evaluation. |

Migrate these capabilities to the new operation/evidence boundary instead of preserving old trace readers, route labels, or compatibility arguments. Deprecated parameter aliases and redundant convenience entry points may be removed after their useful outcomes have native replacements. Do not manufacture missing measurements from Git history or upgrade historical receipts into current verified proof.

The baseline's complete accepted optimizer generation includes `workflow_optimization_evidence.json`, `baseline_surface_manifest.json`, `workflow_optimization_candidates.json`, `workflow_optimization_report.md`, `workflow_refinement_evidence.json`, and a same-directory `optimization_publication_receipt.json`. Include `workflow_optimization_candidate_review.json` when model review occurred and `workflow_optimization_supporting.md` when supporting material was supplied. The root receipt selects a fully installed and reverified generation; it cannot refer to partially written files. The rewrite must retain each document's semantics and downstream handoff, even if a coordinated schema/name revision is chosen. Candidate proposal uses `run` when it may write supporting material; an artifact-free independent review uses `generate` over frozen evidence or `query` when additional read-only discovery is intended. Both require a separate Session for independent history.

### 11.5 Removal and simplification checklist

- Remove `Session.run/arun`, `ask`, old provider-protocol compatibility branches, and old request/response adaptation. Assess existing journal mechanisms, readers, converters, and tests on their usefulness to the chosen contracts, rather than their age. Remove compatibility-only machinery when it has no justified role; do not discard a superior journal design or useful recovery test merely to force a format break. Cover unsupported-store rejection and the supported format boundary, and exercise required recovery scenarios through the new API.
- Rewrite current workflows, optimizer consumers, tests, examples, manifests, authoring guidance, and generated-workflow templates together.
- Remove stale CLI examples such as unsupported `--task`/`-wf` spellings; document actual new commands.
- Consolidate duplicate request normalization, policy resolution, dispatch accounting, response validation, and artifact publication into the common path.
- Retain domain-specific workflow schemas and deterministic validators where they protect actual behavior; do not replace them with a generic manager merely to reduce file count.
- Remove obsolete files only after their unique behavioral requirements are mapped or explicitly identified as compatibility-only. The final repository must not contain two independently functioning SDKs.

## 12. CLI, configuration, packaging, and documentation

The CLI must continue to support workflow discovery/inspection, catalog/module/file references, typed JSON/file/plain-request inputs, task/run IDs, run listing/filtering/details/logs, resume, typed human answers, and explicit reconciliation. Supply machine-readable output, meaningful exit status, and diagnostics consistent with SDK results. A command alias without independent value may be removed; its underlying user action must remain available.

Configuration keeps workspace/state location, the default provider/profile, model/effort settings, generation command grants, query read scope, policy, operation limits, and timeouts discoverable. SDK constructors and CLI commands feed one selection/resolution path; `Provider()` consumes that configuration without naming a vendor in workflow code. Document exact search and precedence for project files and CLI overrides; diagnose conflicting configuration instead of silently choosing an undocumented source. Old shapes may be rejected; the new schema must have one documented canonical form.

Preserve the ability to choose an explicit config path/environment override, load a single workspace configuration or a `pyproject.toml` section, and resolve relative paths against the workspace. An explicit SDK/CLI config path outranks the environment-selected config path; otherwise discover the canonical workspace config, then the `pyproject.toml` section. Use one source rather than recursively merging competing files. Explicit application/CLI provider/profile overrides outrank the selected file default. The canonical filename, environment-variable name, and config schema must be fixed and documented together before Phase 1 completes. A missing default provider is an actionable configuration error when default selection is used; it does not prevent explicit-provider or provider-free workflows. Configuration-source precedence is distinct from `with_config` value derivation: do not accidentally carry a recursive file-merge rule into session/configuration cloning. Workflow listing must avoid importing arbitrary workflow modules; execution must detect ambiguous names and module-cache collisions. JSON stdout and stderr diagnostics must remain separable for automation.

Ship typed Python APIs, package data for supported workflows/prompts/assets, and a fake-provider path that does not require external credentials. Preserve the baseline Python minimum unless a deliberate compatibility decision is documented; do not raise it incidentally. Keep provider-specific optional dependencies isolated from the base install where feasible.

Documentation must include first call, managed sessions and independent calls, shared roles, configured-default selection, generate/query/run distinctions and exact command grants, typed values, multiple artifacts, human input, parallel isolation, recovery, limits, custom capability adapters, and one complete workflow. Include a concise old-concept-to-new-concept guide without shipping compatibility code. All executable examples and packaged workflow metadata must use the new SDK.

## 13. Implementation plan and architecture checkpoints

### Phase 0 — Establish evidence and resolve feasibility

1. Record the baseline tree, currently passing/collected checks, functioning product surfaces, broken historical imports, and supported platform/provider versions.
2. Prove managed sessions, command-free generation, exact command exceptions, and useful read-only query on each required coding provider through the native interface; prove JEV's typed boundary independently.
3. Build three small design probes: direct continuing generation with an independent-call override, plus a read-only query and a narrowly allowed generation command; resumable edit/review with multiple artifacts and a human pause; parallel work items with isolated sessions/workspaces and a typed decision gate.
4. Compare provider defaults plus ordinary functions against the simplest credible alternative on these same probes. Assess setup, repeated arguments, state visibility, debugging, recovery, and extension effort.
5. Settle any blocker by changing the adapter/runtime boundary or another provisional design choice. Preserve fixed requirements and record the decision.

**Exit:** concrete evidence for capability enforcement and one coherent ownership/identity model. No architecture is frozen merely because a short example is attractive.

### Phase 1 — Implement the common runtime and provider surface

Implement `Provider()` selection/binding and typed configuration/derivation, Session identity/ownership, capability interfaces, direct run records, effective request preparation, result/error types, fake adapters, and the new provider methods. Establish the operation state machine and policy intersections before duplicating convenience surfaces. Make direct calls work before requiring workflow setup.

**Exit:** direct API and session contract tests pass with deterministic fakes and native smoke probes; no Session-as-executor dependency exists in the new path.

### Phase 2 — Complete durable execution and artifacts

Implement workflow replay, activities, human suspension, source observations, nested/parallel scopes, budgets, writer/session fences, native recovery, reconciliation, typed codec restoration, and artifact transactions on the shared operation path. Include streaming/cancellation once it uses that same path.

**Exit:** interrupted operations at dispatch/response/capture/rollback boundaries recover according to contract without duplicate uncertain effects; direct and workflow execution produce equivalent values and evidence.

### Phase 3 — Migrate product workflows and operator surfaces

Rewrite packaged workflows and approved labs/evaluation tools using the new public API. Preserve their intended outcomes and artifact schemas unless an explicitly documented improvement includes corresponding consumers. Complete provider adapters, CLI/configuration, inspection, packaging, and documentation. Remove replaced code and old import paths instead of maintaining adapters between runtimes.

**Exit:** every required preservation row has a concrete passing acceptance scenario; no advertised workflow imports a removed API.

### Phase 4 — Review, simplify, and release

Run the full new suite and native conformance matrix. Compare representative workflow source before/after; explain any remaining repetition or abstraction. Remove duplicated normalization, unused compatibility branches, dead exports, obsolete tests/examples, and stale documentation. Build/install distribution artifacts in a clean environment and exercise the CLI and packaged workflows.

**Exit:** section 15's release gates pass. Capability gaps, blocked native proof, missing workflow migrations, or unexplained regressions prevent a complete-release claim.

## 14. Pivot rule

The implementation team is authorized to pivot when a clearly better representation emerges. A pivot is a normal design action, not a failure or a reason to stop useful work.

For each material pivot:

1. State the concrete friction or failed scenario in the current candidate.
2. Develop the proposed alternative enough to run or inspect the same representative cases.
3. Compare total burden: user concepts, code/configuration, hidden interactions, correctness obligations, operational diagnosis, and likely changes. Do not optimize only line count.
4. Verify the fixed requirements and preservation matrix still hold. A provider limitation cannot justify weakening generation command restrictions or query non-mutation, disguising state loss, or dropping a current workflow outcome.
5. Record a short decision with evidence, rejected alternatives, affected contracts/examples/tests, and the migration step. Update the PRD and implementation together.
6. Adopt the better design and remove the superseded path; avoid accumulating both alternatives permanently.

Routine architectural pivots that preserve the agreed outcomes do not need a new approval round. A proposal that changes a fixed user requirement must be called out as a scope change; it must not be smuggled in as implementation detail.

## 15. Acceptance matrix and release gates

These are behavioral acceptance scenarios, not instructions to mirror individual implementation functions. Use deterministic fake providers for repeatable control-flow and failure tests, real temporary files/processes for resource behavior, and native adapters for capability proof. Do not claim native support from mock results.

### 15.1 Core and provider acceptance

| ID | Scenario and required result | Covers |
| --- | --- | --- |
| A01 | Two calls through one `Provider()` with a configured conversational backend continue its conversation; a second construction is separate; explicit `Session()` is equivalent and `session=None` is independent | Managed defaults |
| A02 | Config variants share one lazy backend selection and the identical initialized Session object; new Session/None overrides are correct; one-call overrides and empty command-grant tuples do not mutate defaults | Derivation and omission semantics |
| A03 | Direct and workflow calls with equivalent effective inputs have the same typed values, output validation, artifact semantics, and error classification. Assert that returning an operation value yields that value in RunResult, intentionally returning a Result preserves nesting, and aggregate artifacts/usage do not overwrite versions or double count | One runtime; C01 |
| A04 | Reconstruct workflow/session handles after process restart and recover the same native conversation; multiple new runs receive independent application-default sessions | C02; scope contract |
| A05 | Task and work-item continuity survives intended executions; child scopes are stable; unrelated ownership/affinity misuse fails before dispatch | C02, C11 |
| A05b | Reconstructed module-global handles preserve first-use aliases on resume; shared-to-independent alias drift fails; later cross-run session advancement blocks an old suspended run before its next native turn | Session alias/revision contract |
| A06 | Overlapping calls sharing a session cannot both dispatch concurrently; independent sessions work in isolated parallel branches | C02, C07, C11 |
| A07 | Generate with empty grants blocks every autonomous tool and model-directed command on fresh/resumed sessions; prior run/query authority, hooks/plugins/MCP, and role instructions cannot leak permissions | Command-free generation |
| A07b | Explicit exact read-only argv grants execute through pre-execution mediation; a generic-shell-only adapter rejects them before dispatch. Modified arguments, shell strings, PATH/executable replacement, uncontrolled descendants, environment/config injection, and mutating grants are rejected. Inherited configured grants and per-call clearing work; changed historical grants fail replay | Generation command exceptions |
| A08 | Query autonomously lists/searches/reads permitted local sources and executes a constrained read-only command. Verify default workspace, narrower, and empty local scopes, including enumerated private-state/credential-path exclusions and no ambient parent/network access. Attempted edits, remote mutation, shell escape, traversal/symlink escape, and hidden helper effects are denied. Network reads require a separately enabled read service; supplied reads remain immutable snapshots | Read-only query; C08 |
| A08b | Generate → query → run → generate on one native session retains history and role overrides but resets permissions every turn; streaming, repair, and resume obey the same boundary. Tool-free response alone cannot certify query | Operation transitions |
| A09 | Unsupported schema, timeout, policy, continuation, and backend options fail before provider dispatch; no silent field dropping, provider substitution, or budget charge for nonexistent dispatch | Capability contract |
| A10 | Compatible providers execute the same declared operation contract; native session/provider affinity prevents false continuation after a backend change | Substitutability |
| A11 | Typed return validation respects the supplied schema's extra-field policy; malformed and unsupported values fail distinctly; output repairs are bounded and charged | C09 |
| A12 | Mixed JEV question types preserve native fields/distributions; dependent decisions use explicit subsequent state; explicit Jev and a JEV-configured Provider create no session and replay committed answers. Explicit session arguments and unsupported conversational methods fail without fallback | Specialized decisions |
| A13 | Every physical call/repair/retry has distinct attempt telemetry with accurate identity and available usage; recovery/replay creates no new provider turn | C17 |
| A45 | Provider/Session construction and derivation perform no I/O; first use observes the effective default then pins the family atomically; later config changes affect only new families. Explicit vendor construction wins; missing default produces ConfigurationError before dispatch | Default-provider resolution |
| A46 | Change project/CLI backend/profile after suspension: recorded families retain their saved binding, including a cross-run reused family differing from the run default; new families on resume use the saved run snapshot. Fresh families in new roots use new config; unresolved attempts stay on their native backend. Tighter current ceilings gate new effects without blocking committed replay or conservative recovery | Configuration drift and recovery |
| A47 | Repeated current_run().provider access shares one scoped conversation; separate Provider constructions, roots, and child defaults are independent. Explicit stored Session sharing remains intentional and affinity checked | Default convenience versus fresh construction |
| A48 | Read tool/command observations retain bounded immutable evidence, identities, exit/truncation data; replay performs no live re-read. An uncertain generation/query turn fences its session, and a fenced mutable workspace cannot be inspected as settled evidence | Read evidence and recovery |

### 15.2 Durability and resource acceptance

| ID | Scenario and required result | Covers |
| --- | --- | --- |
| A14 | Resume reuses committed values and recorded failures without re-execution; a completed root returns immediately without changing limits or provenance history | C01, C03 |
| A15 | Edit implementation/version between executions: completed effects replay, future work uses current code, and incompatible recorded input/position/type changes fail before new effects | C03, C09, C14 |
| A16 | Interrupt a retry-safe activity and resume; it may rerun. Interrupt an unsafe one; it remains unresolved. Changing its flag cannot retroactively authorize repetition | C04 |
| A17 | Crash before spawn, after dispatch, after native session ID, after terminal response, after normalized value checkpoint, during artifact capture, and during rollback; recover the exact stage without a duplicate uncertain dispatch | C05, C08 |
| A18 | Completed native response plus pending artifact capture updates native session continuation correctly; the next turn uses the recovered session | C02, C05 |
| A19 | Missing/malformed receipts, dead leader with live descendants, unreadable foreign ownership, and ambiguous process identity remain unknown/fenced | C05–C07 |
| A20 | Timeout/cancel on POSIX and Windows stops and joins the complete owned process tree or leaves explicit uncertainty; no writer/session ownership is released early | C06, C07 |
| A21 | A different client/state directory cannot write an unresolved workspace; confirmed completion/reconciliation releases ownership safely | C07 |
| A22 | Lose a storage commit acknowledgement: exact committed state is confirmed or uncertainty is reported; no duplicate dispatch/publication follows an unchecked assumption | C16 |
| A23 | A direct call crashes before returning: inspect finds its pre-dispatch identity and recovery state; continuation/reconciliation works without reconstructing a fake workflow | Direct durability |
| A24 | Required and optional multi-file outputs, preexisting destinations, missing files, bad JSON/schema, duplicate paths/names, symlinks, and conflicting external edits preserve full-set acceptance/rollback rules | C08 |
| A25 | Interrupt capture after validated-value persistence: resume neither re-runs validators nor launches output repair. Immutable prior artifact versions stay readable | C08, C09 |
| A26 | Manual reconciliation checks stopped effects, authoritative responses, and the complete digest/absence map; changing a file after approval is detected at capture | C05, C08 |
| A27 | Answer a typed human request incorrectly, then correctly; bad answers remain pending, valid answers replay once, explicit None is preserved, and parallel pending questions remain targetable | C10 |
| A28 | Resume a partially completed worklist after source/status changes; original item selection/order/payload remains stable and completed items are not repeated | C11 |
| A29 | Nested/parallel budgets reserve atomically; repairs count, recovery does not; suspension does not extend deadlines; changing one run's allowed limits leaves other runs unchanged | C12, C17 |
| A30 | Stream generate, query, and run with explicit operation selection; final values match nonstreaming calls; early context exit cancels safely; replay identifies a saved result without invented live deltas | Streaming/cancellation |
| A31 | Sync and async cancellation during native execution and artifact finalization cannot leave an apparently successful run with a live writer | Async parity; C06–C08 |
| A31b | Equivalent sync and async workflows, activities, nested calls, aparallel branches, and human pauses return/replay the same values, artifacts, order, budget counts, and suspension states; no coroutine or nested event loop escapes as application data | Async composition |
| A32 | Source unavailable, dynamically defined, mutated, or mixed across revisions is labeled honestly; compatible edits still resume; optimizer cannot attribute mixed evidence to one verified revision | C13, C14, O01 |

### 15.3 Product acceptance

| ID | Scenario and required result | Covers |
| --- | --- | --- |
| A33 | Exercise Ralph's plan rejection, item rework, interruption, and completion with preserved reports and session boundaries | W01 |
| A34 | Exercise Devloop repair/test failure/final audit/follow-up, docloop skip behavior, and depth limits without losing completed phases or overwriting parent evidence | W02 |
| A35 | Exercise every Goal action, blocker/replan/budget path and Image-to-game input/child/result path | W03, W04 |
| A36 | Generate and discover a workflow package from source evidence, force verification/replan, and publish only the validated package | W05 |
| A37 | Discover every labs manifest and exercise each lab's success and applicable rework/replan/question/failure/publication paths against its artifact contract | L01–L15 |
| A38 | Empty optimizer evidence yields zero calls; meaningful evidence yields bounded, independently reviewed, content-identified recommendations; unknown/mixed evidence is not upgraded | O01, O02 |
| A39 | Interrupt/tamper with publication generations and handoffs; loaders reject incomplete/drifted records and never mix generations or claim unevaluated improvement | O03, O06 |
| A40 | Candidate refinement leaves authority byte-identical; validation is isolated and bounded; paired evaluation covers all four outcomes. After an attempted pair is interrupted, repeated resume and generic retry authorization launch neither arm; valid saved evidence recovers it, missing evidence stays interrupted, and tampered evidence fails | O04, O05 |
| A41 | CLI and SDK invoke equivalent workflows/inputs; config precedence, typed answers, reconciliation, JSON output, exit states, and non-importing discovery are consistent | C15 |
| A42 | Install a built wheel in a clean environment; discover packaged workflows and assets, run fake-provider examples, validate type information, and import optional adapters only with their documented extras | Packaging |
| A43 | Old execution API/compatibility shims are absent. Journal design and format decisions are justified by the new requirements; historical compatibility is neither mandatory nor categorically forbidden. The supported format boundary is documented and tested. Unsupported or unrecognized stores are rejected before mutation with an actionable fresh-state-directory option. Any admitted historical records satisfy the contracts of the requested inspection, evidence, or recovery operation without fabricated facts. Empty eligible history makes zero optimizer provider calls. Required replay/recovery scenarios pass; all shipping examples and generated templates use the new model | API clean break; journal reuse on merit; section 2.3 |
| A44 | Compare direct conversation, shared-role workflow, parallel work items, and typed decision examples against the baseline and simplest credible alternative; document any remaining ergonomic cost | Product simplicity |

### 15.4 Release gates

1. Every fixed requirement, C01–C17, W01–W05, L01–L15, and O01–O06 is mapped to passing acceptance evidence. No preserved outcome disappears solely because its old API is removed.
2. All new unit/integration tests pass; translated baseline behavioral coverage passes; no unexplained regression is dismissed as a rewrite artifact. Record baseline failures separately and resolve their applicable behavior before claiming preservation.
3. Linux/POSIX and Windows containment, filesystem transaction, codec, publication, and recovery checks pass on native runners. Preserve the current minimum-Pydantic compatibility check where that version remains supported.
4. Every mandatory provider/capability combination in section 7.5 passes, and each additionally advertised capability has an integration receipt with pinned versions/platform/configuration, including fresh and resumed session cases. A run-only coding adapter does not satisfy this gate. No required capability remains an unacknowledged placeholder.
5. The full package builds and installs cleanly; bundled workflows/prompts/assets and the CLI work from the installed distribution, not only a repository checkout.
6. Documentation, examples, generated templates, migration guidance, configuration schema, and provider capability tables agree with the implemented API.
7. Independent review covers default-provider resolution, session ownership, generation command grants, query enforcement, direct-call recovery, artifact publication, and removed compatibility. Findings are resolved or explicitly block the release.
8. No live worker, unknown native effect, unresolved publication transaction, or test-owned process remains when validation concludes.

Do not set an arbitrary line-count or coverage percentage as a substitute for these gates. Simplification is successful when an author has fewer rules to remember and the code retains the behaviors needed to diagnose and recover real work.

## 16. Source and decision references

Primary baseline references are immutable GitHub links to the revision identified above. Provider documentation references record an observation date and establish investigation inputs; they do not replace integration proof for an enforcement claim.

### Baseline repository

All paths below refer to main commit `ed4802dffc812105fca94d90a0d1edf16a731e2a`:

- [README](https://github.com/mrauter1/botpipe/blob/ed4802dffc812105fca94d90a0d1edf16a731e2a/README.md), [SDK](https://github.com/mrauter1/botpipe/blob/ed4802dffc812105fca94d90a0d1edf16a731e2a/docs/sdk.md), [architecture](https://github.com/mrauter1/botpipe/blob/ed4802dffc812105fca94d90a0d1edf16a731e2a/docs/architecture.md), and [authoring](https://github.com/mrauter1/botpipe/blob/ed4802dffc812105fca94d90a0d1edf16a731e2a/docs/authoring.md).
- [Runtime](https://github.com/mrauter1/botpipe/blob/ed4802dffc812105fca94d90a0d1edf16a731e2a/botpipe/runtime.py), [sessions](https://github.com/mrauter1/botpipe/blob/ed4802dffc812105fca94d90a0d1edf16a731e2a/botpipe/sessions.py), [providers](https://github.com/mrauter1/botpipe/blob/ed4802dffc812105fca94d90a0d1edf16a731e2a/botpipe/providers.py), and [artifacts](https://github.com/mrauter1/botpipe/blob/ed4802dffc812105fca94d90a0d1edf16a731e2a/botpipe/artifacts.py).
- [Packaged workflows](https://github.com/mrauter1/botpipe/tree/ed4802dffc812105fca94d90a0d1edf16a731e2a/botpipe/workflows), [labs workflows](https://github.com/mrauter1/botpipe/tree/ed4802dffc812105fca94d90a0d1edf16a731e2a/labs/workflows), and [optimizer](https://github.com/mrauter1/botpipe/tree/ed4802dffc812105fca94d90a0d1edf16a731e2a/botpipe_optimizer).
- [Optimizer requirements](https://github.com/mrauter1/botpipe/blob/ed4802dffc812105fca94d90a0d1edf16a731e2a/docs/requirements/optimizer-v2.md), [optimizer acceptance](https://github.com/mrauter1/botpipe/blob/ed4802dffc812105fca94d90a0d1edf16a731e2a/docs/optimizer-acceptance.md), [test suite](https://github.com/mrauter1/botpipe/tree/ed4802dffc812105fca94d90a0d1edf16a731e2a/tests), [packaging](https://github.com/mrauter1/botpipe/blob/ed4802dffc812105fca94d90a0d1edf16a731e2a/pyproject.toml), and [CI](https://github.com/mrauter1/botpipe/blob/ed4802dffc812105fca94d90a0d1edf16a731e2a/.github/workflows/ci.yml).

### Provider and authoring references

- **P1:** [OpenAI Codex app-server](https://developers.openai.com/codex/app-server/) and [CLI reference](https://developers.openai.com/codex/cli/reference/).
- **P2:** [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference) and [Agent SDK](https://code.claude.com/docs/en/agent-sdk/python).
- **P3:** [Pi SDK documentation](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/sdk.md) and [RPC documentation](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md).
- **P4:** [TypeSafe primitives](https://docs.typesafe.ai/primitives) and [quickstart](https://docs.typesafe.ai/introduction/quickstart).
- **Authoring comparison:** [Strands state management](https://strandsagents.com/docs/user-guide/concepts/agents/state/) and [workflow example source](https://github.com/strands-agents/harness-sdk/blob/main/site/src/content/docs/user-guide/sdk/multi-agent/workflow.mdx). Strands provides a concise stateful callable and ordinary-Python composition; Botpipe's proposed distinction is explicit operation effects plus durable execution/evidence, not sole ownership of those authoring patterns.

### Evidence limits

This PRD was grounded in the baseline source, collected test inventory, and current primary documentation. It does not claim that the rewrite exists, that all baseline tests were run during planning, or that generation/command-grant/query enforcement has been proved. Native adapter/version choices and enforcement mechanisms must pass Phase 0; their uncertainty is exposed as an implementation gate rather than hidden in a universal provider promise.
