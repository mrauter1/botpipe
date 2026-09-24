# Botpipe 2.0 — Codex-first, simplified

September 22, 2026. This revision supersedes the provider-first 1.3 design.

This revision also replaces the earlier 2.0 rule that treated every `run` as
unsafe to retry while read-only presets always retried. The user-selected
contract is one explicit `retry_safe` policy, defaulting to `True`, across all
provider presets and their async forms.

The September 24 shared-workspace amendment removes workspace writer locks and
unresolved-effect fences. Distinct sessions may run writable calls concurrently
in one repository. Botpipe never prepares, backs up, restores, or rolls back the
workspace; retry and resolution operate on current state.

## Product decision

Botpipe lets a developer drive a coding agent from ordinary Python and resume
long agent work after a crash without paying for completed turns twice.
Providers perform work, sessions carry conversation continuity, Python expresses
the process, and the runtime records operations and outcomes.

2.0 has one provider (Codex), one transport (`codex app-server`), and one execution
primitive (`run`). `query` and `generate` are fixed presets. Codex supplies
sandbox/tool configuration; Botpipe audits observed events and records which
mechanism enforced each restriction. Installed capabilities are probed, not
compared against a reviewed-version allowlist.

This implementation starts from current `main` and is delivered in one new PR,
as requested. The previous rewrite branch is retained as a reference. It is not
the implementation base. Recovery and concurrency changes require human review
in the new PR. Release tagging follows the credentialed platform smoke gate.

## Invariants

1. Workflows are plain Python functions, without a graph language or DSL.
2. Provider turns, activities, human input and nested workflows are journaled;
   resume replays committed results.
3. A provider attempt is retried automatically only when recorded/current policy
   permits repetition and recovery confirms the previous attempt stopped.
4. Declared typed outputs and artifacts are validated, repaired within a bound,
   and captured immutably.
5. Conversation continuity is explicit and survives restarts.
6. Enforcement records distinguish Codex configuration from Botpipe observations.

## Scope

Keep the durable runtime: journal, attempts, recovery, reconciliation,
activities, nested workflows, parallel/aparallel, worklists, limits, typed
outputs, artifacts, human input and all packaged workflows, labs and optimizer
scenarios. Add the Provider/Codex SDK, managed sessions, immutable derived
configuration, async calls, event callbacks, doctor, and current Codex contracts.

Exclude other providers, JEV/decide, exact argv grants, Botpipe-owned tool
mediation, streaming iterators, namespaces, hierarchical ownership registries,
cross-host coordination, prompt-cache optimizations and 1.x API/journal
compatibility. A small adapter boundary is the future extension point.

## SDK contract

`Provider()` and `Codex()` are lazy constructors. `run` accepts prompt, input,
reads, writes, returns, session, sandbox, network, tools, timeout,
output_retries, retry_safe and on_event. None-valued configuration inherits.
Default run sandbox is workspace-write, network off. Query fixes read-only/
network off/no writes. Generate fixes those and takes allowed_tools (empty by
default). All presets default to `retry_safe=True`. Explicit fixed-parameter
overrides raise TypeError. Async forms are identical.

with_config derives instructions/model/effort/workspace/sandbox/network/tools/
timeout/output_retries/retry_safe/name/settings and optionally session. The
enclosing run policy is a ceiling. Settings reject secrets. Precedence is
per-call, derived, constructor, file, built-in defaults. The `[codex]` TOML table
also accepts `retry_safe`. Full access is explicit.

A provider owns one lazy session; reuse continues one Codex thread. Derived
providers share it unless replaced; session=None is independent. Session.task
and Session.work_item supply durable scoped identities. Same-session turns
serialize; parallel branches use distinct sessions and may write the same
repository concurrently. Results contain value, artifacts, usage, operation_id,
run_id and metadata. Replays emit a single event.

## Adapter and probe

Probe executable path/size/mtime, --version, generated app-server schema and
available configuration/features. Cache the result and journal its hash. Require
thread/start, thread/resume, turn/start, per-turn sandboxPolicy and turn/interrupt.
outputSchema is optional; prompt schema plus local validation is the fallback.
A call requiring unavailable tool/MCP controls fails before dispatch, naming the
missing capability. Unused schema item versions do not veto an installation.
Probe hashes and computed execution profiles are audit evidence rather than
durable identity vetoes; a required capability still fails when the call needs
it. Codex login and model selection remain Codex concerns.

Use approval never, workspace plus declared artifact parents and Codex native
temporary writable roots, read-only presets and ambient MCP disabled unless
explicitly named. For an explicit allowlist, disable known discovered
tool-enabling features while preserving unrelated and unknown feature flags.
Audit events and fail on an actual disallowed observed tool with retained
evidence. Audit cannot undo remote effects. Sandbox policy is per turn; tool
configuration applies to a thread and changes through unsubscribe/resume of the
same history. Do not silently preserve a wider tool profile when that transition
cannot apply the requested restriction.

The adapter exposes probe, start_turn, interrupt and close. It returns final
message, usage, thread/turn ids, tool evidence and terminal status. One app-server
belongs to a runtime and multiplexes sessions. Failed thread resume becomes a
SessionError; completed replay never needs Codex.

## Durability and lifecycle

Retain SQLite tables; add only thread/turn/preset/enforcement/probe metadata.
Bump user_version and reject 1.x stores untouched. Direct SDK calls are durable
one-operation runs, inspectable/resumable/resolvable from the CLI.

Fingerprint preset, prompt, input, read digests, output schema and resolved
configuration. A committed mismatch fails before a new effect. Every model
dispatch is a recorded budgeted attempt. Repairs (default at most two) run on the
same thread. Completed turns advance sessions before output validation.

After dispatch without a terminal response, reconcile to one of four states:
adopt `Completed`; retry `Stopped` only when recorded and current `retry_safe`
policy permit; make a targeted bounded interrupt/reconciliation attempt for
`Running`; and keep `Unknown` unresolved for operator action. The flag permits
repetition and does not prove idempotence. `retry_safe=False` suppresses new
automatic retries and new output-repair dispatches, but a completed repair
response remains adoptable. Record automatic versus operator retry origin.
Cancellation ends the current invocation without redispatch; a later explicit
resume can retry subject to policy and remaining limits. A recorded terminal
response is validated and captured without redispatch. Resolve supports explicit
retry, current-workspace acceptance and failure. Output failures do not roll
back repository changes. Botpipe does not prepare, move, back up, restore, or
roll back workspace files around an attempt. Retries use current repository
state. Declared `writes` validate and capture the current files, including valid
files that predate the attempt; immutable capture is not exclusive-writer
attribution or an atomic repository snapshot.

Classify `Stopped` only from durable quiescence evidence: either a pre-ack receipt
recording failure and completed local teardown, or failed/interrupted/cancelled
native history followed by background cleanup and a bounded paginated inventory
proving empty. Historical status and cleanup-request acceptance alone remain
`Unknown`.

Use a journal+run lock for whole execution and resolution; concurrent execution
of the same run fails fast with `RunBusy`. Durable session locks serialize turns
sharing a session. There is no workspace writer lock, lock timeout, or
unresolved-effect fence. Distinct sessions can dispatch writable calls against
the same repository concurrently, while reads and writes may observe intermediate
state. Unresolved effects remain operation/run concerns and are never silently
retried; they do not reserve the workspace globally. Use worktrees when the
application requires source isolation.

POSIX process groups and Windows kill-on-close Jobs contain app-server children.
Cancellation interrupts, waits the configurable grace (default ten seconds),
then attempts to kill the group/Job. Killing a shared server may affect all its
active turns, so independent cancellation is not guaranteed. Async cancellation
waits for the bounded cleanup attempt. Every affected operation is reconciled
from cleanup evidence as `Completed`, `Stopped`, or `Unknown`; failure to confirm
cleanup leaves that operation `Unknown`. Escaped or detached daemons are outside
the containment guarantee; Botpipe does not claim they were stopped. Codex owns
command sandboxing on every platform.

## Migration and release

Rename ask to ask_human, Session.run to Provider.run, and migrate every packaged
workflow/lab/optimizer. Pure inspection reviews use typed query; verifiers that
execute tests or builds use typed run without declared output artifacts and
report failures for producer repair. Activities save any required review file.
Version 2.0.0 supports Python 3.12/3.13; dependencies remain jinja2, pydantic,
jsonschema and PyYAML. Update README, SDK, authoring, CLI, architecture, one-page
migration and Codex compatibility docs. Remove obsolete vendor/exec and 1.3
acceptance evidence rather than preserving unsupported contracts.

## Acceptance criteria

| ID | Required outcome | Evidence |
| --- | --- | --- |
| C1 | All presets complete against latest stable Codex on Linux/macOS/Windows | Local fixture contract CI and credentialed pre-release smoke |
| C2 | Provider reuse, independent calls, derived sessions and work-item restart behave correctly | Fake adapter/server suite |
| C3 | Query asked to write leaves workspace byte-identical; record says codex:read-only | Native local fixture contracts |
| C4 | Tool-free generation observes no calls; injected disallowed call fails with evidence | Fake server and native contracts |
| C5 | Typed output validates; repairs are bounded and budgeted | Deterministic runtime suite |
| C6 | Kill after two of three operations; resume does not dispatch the first two | Recovery suite |
| C7 | All presets obey retry_safe; only confirmed stopped work auto-retries; all resolutions work | Recovery suite |
| C8 | Concurrent resume gets RunBusy; same-session turns serialize; distinct-session writers can overlap in one repository; unresolved work does not reserve it | Cross-process suite |
| C9 | Interrupt/kill contains descendants; async cancellation waits for cleanup; every sibling affected through the shared server is reconciled without claiming independent cancellation | Platform contract suite |
| C10 | Actual missing required capability fails before dispatch; irrelevant schema variation does not veto | Fake server suite |
| C11 | Every workflow, lab and optimizer retains deterministic scenarios | Full suite |
| C12 | Net production source growth about 4,500 lines or less; wheel/imports/strict public types pass | CI |

CI runs deterministic tests without Codex or network, and required latest-stable
Codex local fixture contracts on all three platforms. The nightly schedule
runs the same contract suite. Before release, credentialed real-model smoke
runs on all platforms remain mandatory. Passing fake/local-fixture tests must
not be described as passing the credentialed gate.

## Deferred work

Additional providers return through adapters after a named user need. JEV can
use the activity API in a separate package. Mediated enforcement/exact command
grants, hierarchical claims and streaming iterators require concrete demand.
Prompt-cache work requires measured cost data. None is a 2.0 prerequisite.
