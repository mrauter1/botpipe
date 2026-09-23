# Botpipe 2.0 — Codex-first, simplified

September 22, 2026. This revision supersedes the provider-first 1.3 design.

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
3. Uncertain writable effects are never silently retried.
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
output_retries and on_event. None-valued configuration inherits. Default run
sandbox is workspace-write, network off. Query fixes read-only/network off/no
writes. Generate fixes those and takes allowed_tools (empty by default).
Explicit fixed-parameter overrides raise TypeError. Async forms are identical.

with_config derives instructions/model/effort/workspace/sandbox/network/tools/
timeout/output_retries/name/settings and optionally session. The enclosing run
policy is a ceiling. Settings reject secrets. Precedence is per-call, derived,
constructor, file, built-in defaults. Full access is explicit.

A provider owns one lazy session; reuse continues one Codex thread. Derived
providers share it unless replaced; session=None is independent. Session.task
and Session.work_item supply durable scoped identities. Same-session turns
serialize; parallel branches use distinct sessions. Results contain value,
artifacts, usage, operation_id, run_id and metadata. Replays emit a single event.

## Adapter and probe

Probe executable path/size/mtime, --version, generated app-server schema and
available configuration/features. Cache the result and journal its hash. Require
thread/start, thread/resume, turn/start, per-turn sandboxPolicy and turn/interrupt.
outputSchema is optional; prompt schema plus local validation is the fallback.
A preset requiring unavailable tool/MCP controls fails before dispatch, naming
the missing capability. The default run remains usable when optional preset
controls are unavailable. Codex login and model selection remain Codex concerns.

Use approval never, workspace plus declared artifact parent writable roots,
read-only presets and ambient MCP disabled unless explicitly named. Generation
configures discovered tools/features and audits events. A disallowed observed
tool fails with retained evidence. Do not silently preserve a wider tool profile
when a resumed thread cannot accept the requested restriction.

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

After dispatch without a terminal response, query/generate can retry; run asks
Codex for status, adopts authoritative completion, handles running turns and
otherwise remains unresolved. A recorded terminal response is validated and
captured without redispatch. Resolve supports explicit retry, current-workspace
acceptance and failure. Output failures do not roll back repository changes.

Use two file locks outside workspaces: journal+run for whole execution (fail fast
RunBusy), and canonical workspace root for writer turns (timeout bounded,
WorkspaceBusy). An unresolved-effect fence blocks other runs' writers on that
root and names the owner; resolving the owner clears it. Reads ignore locks and
fences and may observe mid-edit state. Overlapping roots and separate hosts are
not coordinated; use worktrees for independent writers.

POSIX process groups and Windows kill-on-close Jobs contain app-server children.
Cancellation interrupts, waits the configurable grace (default ten seconds),
then kills the group/Job. Killing a shared server affects all its active turns.
Async cancellation waits for cleanup. Escaped process-group descendants are
outside the guarantee. Codex owns command sandboxing on every platform.

## Migration and release

Rename ask to ask_human, Session.run to Provider.run, and migrate every packaged
workflow/lab/optimizer. Reviews use typed query; activities save any required
review file. Version 2.0.0 supports Python 3.12/3.13; dependencies remain jinja2,
pydantic, jsonschema and PyYAML. Update README, SDK, authoring, CLI, architecture,
one-page migration and Codex compatibility docs. Remove obsolete vendor/exec
and 1.3 acceptance evidence rather than preserving unsupported contracts.

## Acceptance criteria

| ID | Required outcome | Evidence |
| --- | --- | --- |
| C1 | All presets complete against latest stable Codex on Linux/macOS/Windows | Local fixture contract CI and credentialed pre-release smoke |
| C2 | Provider reuse, independent calls, derived sessions and work-item restart behave correctly | Fake adapter/server suite |
| C3 | Query asked to write leaves workspace byte-identical; record says codex:read-only | Native local fixture contracts |
| C4 | Tool-free generation observes no calls; injected disallowed call fails with evidence | Fake server and native contracts |
| C5 | Typed output validates; repairs are bounded and budgeted | Deterministic runtime suite |
| C6 | Kill after two of three operations; resume does not dispatch the first two | Recovery suite |
| C7 | Writable interruption blocks; all three resolutions work; query retries | Recovery suite |
| C8 | Concurrent resume gets RunBusy; writers serialize; fence blocks writers only | Cross-process suite |
| C9 | Interrupt/kill contains descendants; async cancellation waits for cleanup | Platform contract suite |
| C10 | Missing required schema method makes doctor and call fail before dispatch | Fake server suite |
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
