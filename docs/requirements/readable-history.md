# Botpipe — readable history and simpler execution

Product requirements and implementation contract · 24 September 2026

Delivery: one implementation PR, greenfield. This document specifies the work; it does not claim that implementation or release verification has occurred. No compatibility with current or older Botpipe versions is required.

## 1. Product decision

Botpipe lets developers run coding agents from ordinary Python, recover interrupted work, and understand what happened well enough to improve the process.

Make the recorded history useful directly to a person or Codex reading files. Replace the SQLite journal and overlapping provider receipts with a file-native ledger; give each conversation its own Codex process; reduce duplicated provenance, lab ceremony, and obsolete tests. Preserve the runtime behaviors that justify its existence.

The design has four ownership rules:

1. A run's append-only ledger owns its execution history and replay state.
2. A small session binding owns conversation continuity across calls and runs.
3. A session's adapter owns its Codex process and cleanup.
4. Python workflow code owns decisions, loops, concurrency, and workspace isolation choices.

No database export, general transaction framework, new workflow DSL, or workspace rollback is introduced.

### Baseline and precedence

The source reviewed while preparing this design is `12188c298e44e7f7b5230d2626b9dbd20c710548` on `simplify/shared-workspace-execution`. This is a reference for reusable code and behavior, not a compatibility baseline. Record the actual implementation base SHA in the single PR for review and source-delta accounting. This PRD's target requirements, not historical branch structure, govern the implementation.

This PRD supersedes earlier requirements for SQLite as the journal, a runtime-wide multiplexed app-server, forced writer isolation, workspace fences, artifact preparation/rollback, and blanket producer/verifier pairs. Retain the chosen Codex-first product scope without a compatibility commitment to any prior SDK.

## 2. Outcomes, scope, and exclusions

### Required outcomes

- An agent can inspect a run chronologically using ordinary file tools, open the exact inputs and outputs of an attempt, and understand retries, reviews, human decisions, failures, and resolutions.
- Completed work replays without another provider call or revalidation of an already accepted human answer.
- Uncertain external effects remain visible and are never mistaken for a safe fresh attempt.
- Cancelling one conversation does not terminate an unrelated conversation's Codex process.
- Ordinary historical runs remain attributable for optimizer comparisons, without repeating full source manifests throughout their history.
- Labs use typed values, ordinary Python, activities, and declared artifacts with less redundant orchestration.
- Tests protect useful outcomes and real failure boundaries, with less dependence on superseded internals.

### Included work

File-native history and its readers; provider attempt evidence; session bindings and process ownership; compact provenance; lab result/control simplification; removal of prose-pattern gates; affected optimizer, CLI, documentation, skill, and tests.

### Explicit exclusions

- Backward compatibility with any Botpipe release: no legacy journal readers, migrations, adapters, aliases, fallback schemas, dual backends, or export pipeline.
- Rebuilding SQLite: no generic transactions, two-phase-commit coordinator, event bus, event-handler registry, compaction engine, or distributed storage.
- Unrelated rewrites of type serialization, callable identity, artifact capture, or optimizer scoring merely to reduce line counts. Reusing useful code does not require preserving its old wire format or compatibility branches.
- New providers, tool mediation, reviewed-version allowlists, or unrelated SDK changes.
- Workspace locks, fences, isolation mandates, merge handling, backup/restoration, or rollback. Distinct sessions may write the same repository concurrently.
- Automatic pruning of history, session eviction, background retention jobs, or cross-host coordination.
- A UI, generated narrative summaries, or provider calls required to read a ledger.

### Greenfield boundary

Implement one supported file-native store format, starting with fresh state. There is no requirement to read, resume, resolve, import, or preserve wire/schema compatibility with runs, sessions, artifacts, receipts, or configuration from current or older Botpipe versions. Do not build SQLite-specific detection or old-version recovery instructions. Normal validation of the supported format is sufficient; unsupported data is not interpreted, overwritten, or deleted.

Remove compatibility-only code, fixtures, documentation, and tests when replacing an affected component. Public/internal signatures, record layouts, IDs, and result models may change where they simplify this design; update all packaged consumers, type checks, docs, and the skill in the same PR. The specified Provider/session authoring model and required outcomes remain product requirements, not promises to existing applications. Supported Python/platform combinations remain requirements. Greenfield does not justify unrelated redesign or discarding useful, already-correct implementations.

## 3. Non-regression contract

These are behavior requirements for the new implementation and its own newly created history. Throughout this PRD, "preserve" means preserve these outcomes, not historical APIs, schemas, or bytes. Compatible workflow source edits and replay within the new format remain required; cross-version replay does not.

- Preserve `Provider`, `Codex`, sessions, immutable `with_config`, sync/async calls, presets, typed results, policy narrowing, and configuration precedence.
- Preserve lazy construction/probing and replay without an installed Codex binary.
- Preserve operation identity by run, scope, and ordinal, including durable-input fingerprints and compatible source edits. Source provenance is evidence, not a new replay veto.
- Preserve activities, nested workflows, `parallel`/`aparallel`, worklists, human input, run limits, and nested provider budgets.
- Preserve the current `retry_safe=True` default for activities and provider operations. It is permission to repeat, not proof of idempotence. `retry_safe=False` prevents new automatic retries and repair dispatches; it does not prevent adopting a recorded response.
- Preserve recovery's `Completed`, `Stopped`, `Running`, and `Unknown` distinctions. A running or unconfirmed prior turn is not safe to repeat merely because the preset is read-only.
- Preserve immutable captured artifacts, required/optional declarations, validation, bounded output repair, and operation-local capture recovery. Capture observes current files; it does not prove which writer created them.
- Preserve run and conversation locks, including cross-process use and Windows/macOS path semantics. Remove no lock that protects a run or conversation merely because workspace locks were removed.
- Preserve targeted interruption, bounded process cleanup, honest cleanup evidence, and async cancellation waiting for cleanup before returning control.
- Preserve actual-execution verification: checks that must run tests use `run` or an appropriate activity; inspection-only reviews use `query`.
- Preserve Codex feature probing, optimistic handling of unused/unknown schema additions, sandbox/tool auditing, native temporary-directory access, and durable enforcement evidence.

## 4. File-native ledger

### 4.1 Layout and authority

Use a task/run organization and immutable artifact store, reusing the implementation where practical without requiring its prior path/record formats. Within each run, the new readable surface is:

| Location | Meaning |
| --- | --- |
| `ledger.jsonl` | Sole authoritative chronology and recovery history for the run |
| `input.json` | Original typed workflow arguments, referenced by the run's first record |
| `request.md` | Original textual request when the invocation has one; not a separately interpreted input |
| `operations/<operation-id>/attempts/<attempt>/prompt.md` | Exact rendered prompt dispatched for this attempt, including repair instructions |
| `operations/<operation-id>/attempts/<attempt>/request.json` | Resolved non-secret request, policy, schema, input/read references, and identity |
| `operations/<operation-id>/attempts/<attempt>/response.md` | Exact final textual response, including invalid responses retained for diagnosis |
| Attempt/operation JSON payload files | Structured responses, typed replay values, errors, and tool/cleanup evidence when too large for a concise record |
| Immutable artifact paths | Captured output versions and capture manifests for the new store |

Use stable IDs in filenames; use meaningful names and scope in ledger records. Do not make filesystem paths from unchecked workflow names, prompts, or other arbitrary user text. Run-owned references are relative to the run directory, validated on read, and include digest/size when they identify immutable payloads. External workspace/read references remain explicitly external; portability of workspace side effects is not promised.

There is one persisted chronology, not both `trace.jsonl` and `events.jsonl`. The first record carries the format version, run identity, workflow name/version, task identity, creation time, initial configuration, and input reference. A cached run listing, if eventually justified, is derived data and cannot override this ledger. This PR requires no persistent index or checkpoint cache.

Preserve state-root-wide run-ID uniqueness: `inspect`, `resume`, and `resolve` still accept a run ID without a task ID. Under the lock keyed by state root and run ID, creation checks existing task/run paths and rejects duplicates across tasks. Lookup reports missing or ambiguous IDs rather than choosing a match. Directory/metadata lookup is sufficient initially; it must not open unrelated payloads. A recorded session-owner reference identifies its exact run directory as well as the run ID.

### 4.2 Records

Each record has a monotonically increasing per-run `seq`, UTC timestamp, event type, and a JSON object containing the event facts. Operation records also identify the operation, scope, ordinal, kind, and readable name; attempt records identify the attempt and dispatch as applicable. Keep the familiar inspection names where they remain useful.

The finite vocabulary must cover:

- Run creation, each execution/resume segment, status changes, and completion.
- Operation intent, validated completion, failure, and unresolved state.
- Attempt preparation, dispatch reservation, native thread/turn acknowledgement, terminal response, validation/repair feedback, and cleanup/reconciliation evidence.
- Budget creation and original deadline; reservations shared by all enclosing budgets.
- Human-input request and accepted typed answer.
- Explicit resolution selection and completion.
- Existing nested workflow, worklist, and session operations.

Reuse existing domain operations rather than inventing a parallel state machine for every feature. A small explicit record reader/folder in the journal module is sufficient; no generic event-sourcing framework.

Keep concise decisions, error reasons, retry origins, usage, and references in the timeline. Large prompts, responses, schemas, and codec payloads belong in referenced files. Retain every physical attempt, including failed validation and repairs. Do not repeatedly embed full workflow state or full source manifests.

Reuse the codec's type-fidelity implementation where useful, removing compatibility-only decoding branches. A readable JSON value must not replace a lossless typed replay payload if doing so changes tuples, non-string mapping keys, models, exceptions, or other supported values. Small codec payloads may be inline; human-facing text remains plain UTF-8. Historical codec encodings need not be readable. A wholesale new serialization system is unnecessary.

Parallel entries are ordered by observation, not a claim about a universal causal order. Scope, parent operation, and attempt IDs explain their relationships. Replay still uses operation identity, never ledger sequence as workflow position.

### 4.3 Minimal write discipline

The existing cross-process run lock permits one executor/resolver for a run. A short in-process append lock orders writes from its parallel branches and provider callbacks. Never hold that append lock across provider I/O, user callbacks, filesystem capture, or another external effect.

1. Validate/encode the record and persist any immutable files it references.
2. Under the append lock, check the relevant current state/limit, assign sequence, and append the complete JSON record plus newline. Retain its `(run_id, seq)`, encoded bytes, and pre-append byte offset until the outcome is confirmed.
3. Flush and sync durable boundaries before permitting the next effect or acknowledging a durable result. Handle short writes and propagate failures.
4. Advance the in-memory folded state only after the append is confirmed. After an ambiguous append acknowledgement, confirm the exact record at the retained offset while still holding the append lock. No other append proceeds until that outcome is resolved; if it cannot be resolved, fail the writer and stop further effects. Visible bytes alone do not prove a failed sync succeeded: re-establish the required sync before acknowledging durability, or stop with the failure.

File creation and replacement use the necessary platform-specific durability primitives already present where possible. Do not claim guarantees stronger than the filesystem supports. A newline is a record delimiter, not proof of power-loss atomicity.

On opening a run, stream its ledger once to rebuild run-local state. Subsequent appends use in-memory state; they must not reread the complete file. Readers take a bounded prefix ending at a complete record, expose the last sequence read, and do not mutate storage or contact Codex. Large sidecars are opened only when requested or needed for replay.

An interrupted non-newline final tail is not a completed record. Under the run lock, an executor may discard that incomplete tail before appending and report the repair. Read-only inspection leaves it untouched. Malformed complete records, missing required payloads, digest mismatches, invalid state transitions, and sequence gaps fail clearly with the run/path/sequence; do not skip interior corruption and continue executing.

Payloads written before their referencing record may be orphaned by a crash. Ignore unreferenced files; do not add garbage collection in this PR. A failed durable write must stop further effects rather than fall back to an unjournaled result.

### 4.4 Provider evidence and recovery

The run ledger becomes the only authority for provider-attempt progress. Remove the separately mutable receipt lifecycle and receipt-scanning recovery fallback after all equivalent evidence is represented. Retain immutable payload files where useful; they are referenced evidence, not another competing status store.

Adapter checkpoints that matter to recovery must synchronously reach this durable path. Best-effort `on_event` callbacks remain distinct and cannot be used as durability acknowledgements. Persist thread/turn identity and response evidence as soon as available, before validation or artifact capture. A completed native turn advances conversation continuity even if its output later fails validation.

| Crash/interruption boundary | Required behavior |
| --- | --- |
| Intent recorded, dispatch not authorized | No provider turn dispatched; proceed when safely resumed |
| Dispatch authorized, no durable terminal outcome | Reconcile with Codex using recorded identities; do not infer non-dispatch from missing acknowledgement |
| Terminal response durable, validation/capture unfinished | Adopt and continue validation/capture without redispatch |
| Operation completion durable | Replay the recorded typed result and artifact handles |
| `Stopped` confirmed | Retry only under recorded/current retry policy and limits |
| `Running` or `Unknown` | Bounded targeted reconciliation/cleanup; remain unresolved until stopped, completed, or explicitly resolved |

Do not promise exactly-once external execution. A crash between an external effect and recording its result remains possible. The ledger makes this uncertainty explicit.

### 4.5 Budgets and accepted decisions

Replace SQL-specific budget access with small journal operations. While holding the append lock, check all enclosing provider budgets and append one dispatch-reservation record containing their identities and updated counts. There must be no interval in which one parallel branch consumes only some of its nested budgets or another branch exceeds the common limit.

Every physical dispatch, including repair and operator-authorized retry, reserves once. Recovery and replay do not reserve. Preserve original deadlines across suspension, the current timeout-ceiling rules, and conservative treatment of a reservation whose dispatch outcome is unknown. No automatic refund for a crash merely because a response is absent.

Validate a human answer once and record its accepted typed value before continuation. Resume uses that value even if validators or surrounding source later change compatibly.

Record an operator's retry/accept/fail choice before executing it. Completion after a crash must continue that same choice. Preserve existing acceptance/capture behavior and approved digests; never replace a previously approved artifact capture with newly changed workspace bytes. A deliberate retry gets a new attempt identity, leaving earlier evidence intact. No resolution restores workspace files.

Use this explicit-resolution policy: a turn confirmed `Running` blocks retry, accept, and fail until reconciled; `Unknown` blocks automatic retry, but an operator may deliberately retry, accept a valid supplied/current result, or fail it. Record that authorization and the remaining uncertainty. The operator's choice is not evidence that cleanup succeeded. This is the intended operator control, not a legacy-compatibility obligation; no mandatory session-fork/poison mechanism is needed.

## 5. Sessions and process ownership

### 5.1 Durable session bindings

Run-local ledgers cannot by themselves own conversations shared across runs. Use one small atomic JSON binding per canonical session identity under the state directory, alongside the existing session-lock mechanism. Scope is encoded in the identity; retain existing task/work-item/direct identity semantics. Validate the binding's format version and canonical identity. It contains the native thread ID and, while a logical provider operation is pending, its owning run/operation and latest attempt reference. Ownership covers the full validation/repair loop, not only one physical turn.

Key session locks by the canonical state root and session identity, not by a particular run's new ledger path. Otherwise two runs sharing `Session.task(...)` would silently stop serializing. Lock order is run lock, then session lock; do not acquire another run lock while holding a session lock.

Under the session lock:

1. Persist the run's attempt intent.
2. Persist its pending-operation/attempt reference in the session binding **before dispatch**.
3. Perform normal preflight and thread setup, recording any new native identity. Reserve/record immediately before a physical turn dispatch, then send it. Preflight/setup alone does not consume a provider turn.
4. Persist acknowledgements and terminal response in the owning run ledger.
5. Advance the binding's thread identity from recorded authoritative evidence, keeping its pending operation through validation and any repair attempts. Only after durable operation completion, final failure with a known finished/stopped attempt, or a completed operator resolution does one atomic replacement preserve the final thread identity and clear the pending owner. Retain the physical session lock through the repair loop as today.

An ambiguous binding write also requires confirmation under the session lock: re-read the exact intended binding and establish the required sync before dispatch or acknowledgement. If confirmation fails, stop; neither an exception nor visible bytes alone establishes whether the update became durable.

On acquisition after a crash, inspect the referenced operation before using the binding. A durable response can repair a stale thread identity, but does not release ownership if validation/repair remains unfinished. If another run acquires the physical session lock but finds that pending owner, report a `SessionError` naming the run to resume/resolve; do not wait while holding the lock it needs. If no turn of the logical operation was authorized, non-dispatch is established and its pending reference can be cleared without provider recovery. A different run may repair the shared binding from already durable facts, but must not mutate the originating run's history or acquire its run lock while holding the session lock.

An operator-authorized retry retains ownership for the next attempt. A completed accept/fail resolution releases it even when the prior native outcome remained unknown, under the policy in section 4.5; retain the uncertainty in the ledger rather than fabricating stop evidence. Without such authorization, unknown attempts never release a pending owner automatically. Missing owner history or a corrupt binding produces a named `SessionError`, not silent conversation loss.

This is a specific conversation-binding protocol, not a general multi-file transaction API. No global scan of all historical runs is required on every session acquisition.

### 5.2 One app-server per active session

The runtime lazily owns a simple map from canonical session identity to adapter. Distinct sessions get distinct app-server processes. All handles for one session within that runtime share its adapter; `with_config` does not accidentally create another process or lose history. Key routing by the Botpipe session identity, available before the first turn, not the initially absent native thread ID. Creation and close are synchronized; `run` and recovery select the same owner. Capability probing reuses its existing cache and must not create an extra idle app-server.

Keep a session's server alive until runtime/provider close, cancellation requiring escalation, or transport failure. Do not close it after each successful turn: that would change the behavior of background work started in the session. There is no idle eviction or generic process pool in this PR. Document that many long-lived sessions consume more processes; applications can bound lifetime using the existing close/context-manager API.

`session=None` gets an operation-local adapter, reused for that operation's repairs/recovery and closed after its cleanup. It does not create a permanent anonymous entry in the session map. Durable thread continuity across runtime restarts still comes from the session binding and Codex resume, not from a process surviving forever.

Per-session process ownership is per runtime, not a cross-process server broker. Two processes sharing a durable session still serialize through its lock and resume the latest native thread. Reacquisition after another process used the session must refresh its binding/profile; stale in-memory subscriptions must not lose intervening history. Verify this behavior against native Codex before claiming support.

Sandbox remains per turn. Tool-profile changes still require whatever unsubscribe/resume sequence the installed Codex actually needs. One server per session does not justify deleting that behavior without a contract test.

### 5.3 Lifecycle simplification

Remove runtime-wide active-turn routing, sibling-interruption fan-out, and multi-session shutdown coordination that become unreachable. Retain protocol request correlation, process-generation checks, mandatory checkpoint failures, and cleanup evidence needed by one session; small scope does not make stale reader threads harmless.

Cancellation interrupts the target turn, waits within its configured grace, and escalates only its owned process group/Job Object when required. Async cancellation waits for this bounded cleanup attempt. Incomplete cleanup stays `Unknown`; it must not be presented as a clean stop. Runtime close attempts cleanup for every owned adapter even when one fails, and reports relevant failures.

After confirmed shutdown, the next authorized recovery/turn can lazily restart that session's transport. Prefer the adapter's existing restart path; if its map entry is replaced, use identity/generation checks so old cleanup cannot remove or affect the replacement. Retain/report incomplete cleanup rather than silently discarding its ownership.

## 6. Provenance with demonstrated utility

Preserve source attribution because the optimizer compares historical runs with proposed workflow changes. Removing all observation from ordinary runs would make later attribution impossible.

Separate identity from full manifests:

- Ordinary execution segments record compact start/end provenance: workflow identity, surface ID, orchestration ID, verified/unavailable state, and a concise reason when unavailable.
- Keep the identity calculation consistent with explicit optimizer baseline capture. Record prompt/resource changes, not only Git HEAD or the workflow's declared version.
- Persist a full source manifest only when an optimizer/inspection operation explicitly needs that deliverable. Do not repeat it in run metadata and multiple events.
- A completed replay does not re-observe current files and overwrite historical identity. A resume with compatible edits records a new execution segment; it does not relabel earlier work as produced by the new source.
- Missing source, loaded-source drift, or source mutation during observation remains explicitly unverified. Observation failure must not prevent otherwise valid execution or fabricate attribution.

Retain currently justified callable/type identity behavior. Share capture work where existing inputs are already available, but do not replace trustworthy attribution with heuristics or introduce a new provenance framework. The intended reduction is redundant work and persisted bulk, not false certainty.

Update optimizer readers to consume compact records and the new journal snapshots. `improve_workflow` must explicitly capture and validate its canonical baseline surface manifest; remove its fallback from a missing surface manifest to `asdict(SourceManifest)`, which is a different contract. If baseline attribution is unavailable, report that limitation instead of publishing a falsely matched baseline. Preserve baseline/candidate separation, publication receipts that are actual optimizer deliverables, paired evaluation recovery, and exclusion of `created`/`running` runs from automatic history selection. Removing provider transport receipts does not mean deleting all files named receipt.

## 7. Labs: structured production, meaningful review

Review every call through `labs/workflows/_shared.py:run_phase` and the custom `improve_workflow` flow. Apply the simplest shape that preserves the phase's job:

| Phase job | Preferred shape |
| --- | --- |
| Produce a decision or structured handoff | Provider returns a domain model; Python uses its fields |
| Produce declared files | `run` with artifacts and, when useful, a typed result |
| Check types, references, counts, coverage, or file validity | Existing schema/deterministic validation; no extra provider needed |
| Independent judgment materially improves the result | Retain a typed reviewer with explicit acceptance/rework reasons |
| Verify code by executing tests/builds | `run` or an activity that executes the check; record actual results |
| Publish a typed value as JSON/Markdown | Small journaled activity; do not ask a model to copy it into another file |

Do not make a generic reviewer reconstruct domain facts that the producer can return correctly under an explicit schema. Do not remove security, release, evidence-quality, or other substantive reviews just because they cost a turn.

Simplify duplicated context snapshots, artifact-name inventories, and phase bookkeeping. Prefer local Python variables, clear loops/functions, and existing Botpipe operations. Do not replace verbose workflows with a configurable phase engine, universal outcome interpreter, or hidden routing table.

Preserve meaningful local rework, backward replanning, human prerequisite collection, bounded execution, and historical evidence. Typed schemas must represent unavailable information without forcing invented facts. Let normal Pydantic extra-field behavior stand unless a particular boundary genuinely requires stricter validation.

### Remove prose-pattern enforcement

Delete keyword/regex gates such as `_HIDDEN_EXECUTION_PATTERNS`, negation exceptions, and `_no_hidden_execution` from publication policy. Natural-language phrasing is not reliable evidence that an action happened or was authorized.

Use structured facts for choices: a recommendation, a proposed follow-up, and an actually executed child operation are different things. Actual execution is established by recorded runtime operations/check results, not a producer's assertion. Where interpreting supplied prose is genuinely part of the job, use a journaled provider call with typed output and explicit uncertainty. Do not add a classifier to every publication as a replacement tax.

Retain deterministic checks of IDs, declared outcomes, cross-artifact references, candidate coverage, provenance, and requested execution boundaries. Recommendations must not trigger downstream execution unless ordinary workflow code and user parameters explicitly select it.

### Coverage of useful lab outcomes

- Release: distinguish go, conditional go, and no-go with blockers and executed-versus-unexecuted checks.
- Investigation, incident, and security: retain evidence sources, missing prerequisites, remediation/hardening actions, and verified closure where requested.
- Workflow strategy/candidate/adaptation/evaluation: retain valid selected-workflow references, parameters, candidate identities, and executable evaluation contracts.
- Workflow packaging: materialize a runnable package and retain real validation/build results.
- Portfolio/company improvement: produce useful recommendations without silently launching recommended work.
- `improve_workflow`: preserve explicit proposal/implementation/evaluation choices, measured-versus-unmeasured claims, bounded revision, history filtering, and optimizer publication integrity.

## 8. Test cleanup and efficient verification

Before deleting a test, identify the product behavior it protects. Classify it as retain, rewrite against a public behavior, merge with equivalent coverage, or remove because its requirement was explicitly superseded. Keep a concise change map in the PR; test count alone is not a success metric.

Remove tests requiring SQLite internals, old-version compatibility, duplicate provider receipts, shared-server sibling cancellation, forced workspace isolation/rollback, particular prose phrases, exact prompt wording, mandatory verifier counts, or obsolete lab result wrappers. Replace any still-valid behavior they covered in the same change. Build replay and crash fixtures in the new format; do not retain historical journals merely to keep an old test passing.

Do not delete corruption, crash-boundary, process cleanup, cross-process lock, type fidelity, budget, or optimizer attribution tests because their setup is inconvenient. Fault injection at a durable-write boundary and transport contract tests legitimately inspect internal boundaries; avoid testing incidental helper call counts or dictionary layout outside a documented format.

Use the fake adapter for ordinary workflow tests, the fake app-server for protocol/lifecycle scenarios, and a small native suite for Codex/platform contracts. Prefer readiness handshakes over tiny sleeps and 50 ms setup deadlines. Windows tests must not confuse slower startup/fsync with the behavior under test.

Retain supported Linux/macOS/Windows and Python 3.12/3.13 coverage. Keep latest-stable Codex contracts and nightly execution. Reuse current bounded test concurrency; do not increase worker count to hide a bottleneck. Attach before/after timings from comparable runners, with slow cases explained. Measure ledger growth/append work structurally, not through fragile wall-clock thresholds.

## 9. Acceptance criteria

All criteria are merge gates unless an explicitly named native environment is unavailable; that is a recorded blocker, not a pass.

| ID | Required evidence |
| --- | --- |
| A1 — Direct readability | A representative multi-step run with a repair, human answer, and failure/resolution can be understood by reading its ledger and referenced UTF-8/JSON files. Exact prompts and every available attempt response are present. No SQL query/export is needed. |
| A2 — Replay fidelity | Kill a three-operation workflow after two completions; resume makes zero provider calls for those two, preserves typed values/artifacts, and rejects changed durable inputs before effects. Completed replay works without Codex. |
| A3 — Attempt recovery | Inject crashes before dispatch, after authorization, after native acknowledgement, after response, and during capture. Assert adoption versus unresolved status and retry rules, including `retry_safe=False`, without rollback. |
| A4 — Ledger correctness | Parallel appends retain distinct ordered records. Lost acknowledgements do not duplicate an accepted result/reservation. A torn final tail is handled only as specified; interior corruption/missing required payloads fail visibly. Read-only inspection does not alter bytes. |
| A5 — Shared limits | Three parallel child workflows under a two-turn budget dispatch exactly twice and report budget exhaustion. Nested reservations are all-or-none; repairs/retries count once; replay/recovery count zero. Original deadlines and run-operation ceilings survive resume. |
| A6 — Human/operator decisions | Crash after answer acceptance or resolution selection, then resume. No second human validation or changed resolution choice occurs. Retry, accept, and fail each complete correctly; accepted artifact digests cannot silently change. |
| A7 — Shared sessions | Separate processes/runs sharing task/work-item identity serialize and continue the latest thread; direct provider reuse preserves its existing cross-run continuity. Crash after a response but before binding update/validation does not lose history or let another run interleave before required repairs. Crash before any dispatch reservation is recognized as non-dispatch without a provider call or charge. Ambiguous binding writes prevent unconfirmed dispatch. Verify binding state after each explicit resolution of `Unknown`, and that all choices reject `Running`. |
| A8 — Process ownership | Reused/derived providers continue one session; replaced/independent sessions are separate. Escalating cancellation of session A leaves B operational; A's authorized restart/recovery subsequently works. Independent operation-local adapters are cleaned up; runtime close attempts every adapter, and stale cleanup cannot affect a replacement. |
| A9 — Native continuity | On each supported platform, verify same-session preset/tool-profile transitions, background-work behavior between successful turns, process cleanup, and cross-process reacquisition. Missing native evidence is not replaced by a fake assertion. |
| A10 — Existing workspace behavior | Concurrent distinct-session writers can enter the same workspace. Failure/cancellation/resolution does not restore files. Current-state artifact capture and immutable prior versions retain their existing contracts. |
| A11 — Provenance/optimizer | An ordinary run can later be attributed by optimizer history. Source/prompt drift, mixed execution segments, unavailable source, and completed replay are classified honestly. Full manifests are not repeated; explicit baseline/evaluation/publication scenarios pass. |
| A12 — Labs | All useful deterministic scenarios in section 7 pass, including rework, backward replan, human prerequisites, negative decisions, executable checks, and no unrequested downstream execution. A producer's prose cannot masquerade as execution evidence. |
| A13 — SDK/CLI | Public type checks for the target API, imports, wheel installation, configuration, presets, events, `doctor`, workflow discovery, run list/show/logs, resume, and resolve pass against the file store. Concurrent attempts to create the same run ID under different tasks cannot create ambiguous runs; run-ID-only lookup remains unambiguous. |
| A14 — Greenfield format | Fresh state supports the full run/inspect/resume/resolve lifecycle using only the new format. Unsupported-format input fails clearly without overwriting data. No compatibility-only reader, alias, migration, dual-write/export path, or historical-format fixture remains in affected components. |
| A15 — Bounded storage work | Appending N bounded records writes O(N) ledger bytes and does not rescan prior records per append. Reading a selected run does not open unrelated runs' payloads. Inspection of a live run returns a coherent complete-record prefix. |
| A16 — Simplification and coverage | PR includes removed responsibilities, production-source delta versus its actual base, rewritten/removed-test mapping, and comparable CI timings. Net production-source reduction is the target; any increase requires a concrete justified tradeoff, not code relocation. |

These tests reduce regression risk; no PRD can guarantee the absence of every bug. The acceptance evidence, review, and explicit greenfield boundary are the release decision inputs.

## 10. Single-PR implementation sequence

Use reviewable commits inside one PR. Do not ship partially migrated storage or defer affected consumers to another PR.

1. **Characterize and specify.** Record the base, map current journal consumers and preserved behaviors, define the small ledger envelope and session binding, and add representative behavior fixtures. Prototype the cross-run session crash boundary before broad storage replacement.
2. **Replace journal authority.** Implement append/read/fold and payload references; move run operations, budgets, human input, resolutions, and inspection to it. Remove SQL access, duplicate receipt authority, and affected compatibility-only branches as their replacements land. Reuse the codec/artifact implementations for their useful behavior, not old-format compatibility.
3. **Isolate session processes.** Add lazy per-session ownership and operation-local independent adapters; retain proven profile transitions/cleanup. Delete now-unused multiplexing and sibling-shutdown branches.
4. **Trim provenance and migrate consumers.** Record compact segment identities; retain explicit optimizer manifest capture; retarget CLI, optimizer, and history discovery to the same journal readers.
5. **Simplify labs and tests.** Apply structured producer results and meaningful reviews phase by phase, remove prose gates, update all affected prompts/contracts/consumers, and remove superseded tests only with their behavior map.
6. **Review and verify.** Run focused crash/concurrency/native tests, then the full deterministic/platform suite, public typing, wheel smoke, and source-growth checks. Independently review storage/session ownership and confirm no prohibited responsibility has reappeared.

The storage and process changes are the high-risk portions. A failed characterization or native continuity test must be resolved before merging; do not compensate by weakening the test or promising a follow-up fix.

## 11. Expected code changes and deletions

| Area | Intended change |
| --- | --- |
| `journal.py`, `budgets.py`, affected `runtime.py` paths | Replace SQL coupling with a small file ledger and domain operations implementing the specified target behavior |
| `providers.py`, `operations.py`, provider checkpoints | One durable attempt-evidence path; remove mutable transport receipt authority |
| `sessions.py`, `locks.py` | File bindings and state-root session-lock identity; preserve scope and cross-process semantics |
| `codex_appserver.py`, provider ownership | Per-session process lifecycle; remove unnecessary multi-session routing/fan-out |
| `provenance.py`, surface helpers, optimizer readers | Compact ordinary observations; explicit full manifests; no unrelated identity rewrite |
| Lab shared helpers, contracts, prompts, publication validation | Typed producers, proportionate review, ordinary control flow, no prose policy regexes |
| Tests and fixtures | Preserve behavioral/crash coverage; remove obsolete architectural assertions |

Use existing utilities where appropriate; introducing a small ledger I/O or session-binding module is acceptable if it has one clear responsibility. Do not force SQL transaction-shaped APIs onto files simply to avoid changing callers. Do not move complexity into a new generic abstraction and count that as deletion.

## 12. Documentation and completion checklist

Update `README.md`, `docs/sdk.md`, `docs/authoring.md`, `docs/architecture.md`, `docs/cli.md`, `docs/testing.md`, relevant optimizer/lab documentation, Codex capability notes, and `skills/botpipe-workflow-authoring/SKILL.md`. Remove obsolete migration/legacy-support documentation and links, including `docs/migration.md` if it has no remaining purpose. A concise fresh-state setup note is sufficient. Codex capability probing concerns the installed external provider, not compatibility with old Botpipe releases, and remains required.

Documentation must explain the run layout, chronological reading, authoritative versus referenced data, fresh-state setup, cross-run session bindings, per-session process lifetime, retry uncertainty, shared workspaces, and the absence of rollback. Provide one small real generated example run; do not maintain a second hand-authored description of a different format.

The PR is complete only when:

- Every included area and its readers/consumers are migrated; no transitional dual store remains.
- Acceptance criteria A1–A16 have evidence, with environment limitations identified rather than hidden.
- Recovery/concurrency changes have an independent human review before merge.
- Removed tests and production responsibilities are accounted for; any API/model changes simplify the specified design, and every packaged consumer is updated without compatibility shims.
- Docs and the authoring skill describe the implemented behavior.
- No release tag, old-store deletion, historical-file rewrite, or unrelated repository mutation is bundled into the implementation.

## Appendix: basis for the architecture

This appendix is non-normative inspiration and confers no API or format compatibility requirement. The old Botpipe at `692e090b56cb47c69d72fc994bef3adacd3d78f8` wrote readable run folders, raw output files, and JSONL history directly. Reuse that organizational idea, not its graph engine or separate checkpoint authority. Its event writer reread the full log on every append; its trace/events/checkpoint paths could disagree after interruption. The new design deliberately uses one run history and incremental appends.

- [Old event writer](https://github.com/mrauter1/botpipe/blob/692e090b56cb47c69d72fc994bef3adacd3d78f8/botpipe/runtime/events.py)
- [Old trace writer](https://github.com/mrauter1/botpipe/blob/692e090b56cb47c69d72fc994bef3adacd3d78f8/botpipe/runtime/tracing.py)
- [Old filesystem stores](https://github.com/mrauter1/botpipe/blob/692e090b56cb47c69d72fc994bef3adacd3d78f8/botpipe/runtime/stores/filesystem.py)
- [Reviewed current architecture](https://github.com/mrauter1/botpipe/blob/12188c298e44e7f7b5230d2626b9dbd20c710548/docs/architecture.md)

The purpose is a smaller set of understandable responsibilities, not a smaller feature set disguised as cleanup.
