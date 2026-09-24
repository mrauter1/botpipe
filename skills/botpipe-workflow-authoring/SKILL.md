---
name: botpipe-workflow-authoring
description: Author, migrate, review, and test durable Botpipe 2.0 Python workflows. Use for Provider and Codex calls, sessions, prompts, typed results, activities, artifacts, worklists, human input, replay, recovery, and workflow labs.
---

# Botpipe workflow authoring

Read the repository's current `README.md`, `docs/authoring.md`, and `docs/sdk.md`
before editing. Inspect a relevant workflow under `botpipe/workflows/` or
`labs/workflows/`; use `ralph_loop` for artifact/worklist composition. Consult
`docs/cli.md` for recovery commands and `docs/testing.md` for test selection.
Treat the current implementation as authoritative if this skill is stale.

Target the Codex-only 2.0 API. Use `Provider()` by default or `Codex()` explicitly;
both are lazy and bind to the active workflow runtime. Do not introduce removed
1.x APIs (`Session.run`, `ask`, `Session.fresh`), other provider backends,
`decide`, `allow_commands`, or streaming iterators. Use `on_event` only for
best-effort progress, never durable control flow. Do not migrate 1.x journals;
use a new state directory.

## Invariant

Python owns control flow. Every material observation or external effect goes
through a recorded Botpipe operation.

Use `@workflow` on an ordinary typed sync or async function. Express decisions,
loops, composition, and returns in Python. Use a nested decorated call for a
durable child and `parallel()` / `aparallel()` for independent branches. Do not
introduce route tables, transition objects, graph compilation, or mutable
workflow-state models.
Prefer a small function composed from existing Botpipe primitives over a new
runner, checkpoint format, or generic orchestration layer. Bound rework loops
with explicit acceptance conditions and a provider budget or attempt limit.

## Choose the operation boundary

Choose the smallest operation that can perform the required work:

| Work | Operation |
| --- | --- |
| Implement code, execute tests or builds | `provider.run` / `arun` |
| Inspect files or review without executing write-producing checks | `provider.query` / `aquery` |
| Produce an answer from supplied context without tools | `provider.generate` / `agenerate` |
| Custom I/O: API calls, subprocesses, clocks, randomness, material file reads | `@activity` |
| Typed human decision | `ask_human(question, returns=Model)` |

Treat `query` and `generate` as fixed read-only, network-off presets of `run`.
Neither accepts `writes`, `sandbox`, or `network`. Use `query(tools=...)` or
`generate(allowed_tools=...)` for explicit tool names, not command patterns.
An opted-in remote tool can still have remote effects; sandbox restrictions and
tool-call auditing are not proof that those effects cannot occur.

Use `run` for verifiers expected to execute tests, even with `writes=()`:
no declared outputs does not mean no workspace writes. Preserve native temporary
directory access; do not request full access just for test caches. Make the
verifier report executed checks, failures, and unavailable checks distinctly;
do not silently replace execution with inspection or let it repair the producer's
work unless that is explicitly its role.

Keep custom effects inside activities; ordinary workflow Python reruns on
resume. Use `current_run().operation` only for lower-level integrations.

## Retry safety and replay

Treat `retry_safe=True`, the default for activities and all provider presets,
as permission to repeat, not proof of idempotence. Set
`@activity(retry_safe=False)` or `provider.run(..., retry_safe=False)` for effects
that must not repeat, such as payments, publishing, or non-idempotent remote
mutations. Provider configuration and `with_config` also accept `retry_safe`.
Setting it to `False` disables new provider output-repair turns as well as
automatic recovery attempts. Activity exception retries are separate and
default to zero.

Let the runtime adopt completed provider responses. Automatic provider retry
requires a confirmed stopped attempt and both recorded and current retry
permission. Leave unknown effects unresolved; do not catch them and launch a
replacement turn. Use operator resolution after inspecting the run. Unresolved
work belongs to its operation and run; it does not reserve the workspace. Never
claim exactly-once execution.

Preserve recorded operation scopes, order, and contracts across resume. Changes
to prompts, inputs, read digests, output schemas, or effective configuration can
cause replay mismatches. Do not skip already-completed work by consulting live
files or add an independent resume/checkpoint mechanism.

## Prompts, results, and artifacts

Use a plain string for an inline prompt and `Prompt.file` for a prompt beside the
workflow. Prefer typed `input` and `returns` contracts. A strong provider prompt
states the goal, relevant evidence, required output, constraints, validation,
and done criteria without prescribing unnecessary implementation details.
Use `result.value` for the validated return. Request typed review verdicts and
save them through an activity if a review file is needed; do not ask `query` to
write a review file. Allow bounded output repair (`output_retries=2` by default)
when retry policy permits it. Repairs consume provider turns and do not roll
back edits made by invalid attempts.

Declare provider destinations with `Artifact.json`, `.md`, `.text`, or `.raw` in
`run(..., writes=...)`. Mark outputs required when later behavior depends on them.
Read the immutable `ArtifactHandle` from `Result.artifacts`; do not treat a live
workspace file as historical state. A valid current destination may predate the
attempt, and capture does not establish exclusive writer attribution or an atomic
repository snapshot. Pass captured handles through `reads` for durable inputs;
do not claim this limits all other files Codex can inspect.

Botpipe does not prepare, move, back up, restore, or roll back workspace files
around provider work. A failed attempt leaves its edits in place, and any retry
works from current repository state.

Use `Worklist.from_artifact` when code needs durable item selection and
completion. Item IDs must be unique. The runtime snapshots the original
selection, including completed items on replay. Do not reselect from a changed
live file or filter out completed items on resume. Call `items.complete(item)`
only after acceptance; use the resulting `items.artifact` as the updated snapshot.

## Sessions and concurrency

Reuse a provider to continue its conversation. Use `with_config(instructions=...)`
for roles; it shares the original session unless replaced. Pass `session=Session()`
for a separate conversation or `session=None` for independent turns. Use
`Session.task(key)` and `Session.work_item(item, key="default")` for durable task
and work-item identities. Keep their keys stable across resume.

Give parallel branches separate sessions. Distinct sessions may run writable
calls concurrently in the same canonical workspace; turns sharing one session
serialize. Design prompts and artifact destinations for shared mutable state,
or use separate worktrees when edits require isolation. Read-only calls may
observe a concurrent writer mid-edit, so isolate the source when a review needs
a stable tree.

Cancellation escalation on a shared app-server may interrupt sibling turns.
Do not promise independent cancellation. Each affected operation must be
reconciled from cleanup evidence as `Completed`, `Stopped`, or `Unknown`.

Use `provider_budget(max_turns=..., max_seconds=..., turn_timeout_seconds=...)`
for durable provider limits shared by nested and parallel work. Repairs count;
replaying or adopting completed results does not dispatch again. Do not describe
the run's `timeout` as a wall-clock deadline for arbitrary workflow Python.

## Validate

Before finishing:

1. Import the workflow and inspect its typed callable contract.
2. Run focused behavioral tests with `FakeProvider`, without live credentials.
3. Cover acceptance, bounded rework, and relevant pause/resume or interruption
   paths. Check that replay makes no new provider calls for completed work.
   Assert outcomes, captured artifacts, and meaningful policies rather than
   exact prompt wording, private call order, or timing-sensitive sleeps.
4. Run `botpipe workflows show module:function` when the CLI is available.
5. Report commands and results, distinguish deterministic checks from real
   Codex validation, and state any remaining runtime-dependent risk. Do not claim
   quality, performance, or cost improvements without measured evidence.
