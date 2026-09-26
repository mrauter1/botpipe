---
name: botpipe-workflow-authoring
description: Author, review, and test durable Botpipe 2.0 Python workflows. Use for workflow design, Provider or Codex calls, prompts, sessions, typed results, activities, artifacts, worklists, human input, concurrency, replay, recovery, and workflow packages.
---

# Botpipe workflow authoring

Start with `docs/authoring.md`, `docs/prompting.md`, and the relevant section of
`docs/sdk.md`. Load `README.md` for repository orientation, `docs/cli.md` for
operator recovery, `docs/testing.md` before changing tests, and
`docs/architecture.md` for runtime internals only as needed. Inspect a packaged
workflow and its tests when its pattern is relevant. Use the implementation as
authority if documentation conflicts with it.

Target the Codex-only 2.0 API. Use `Provider()` by default or `Codex()`
explicitly. Do not introduce removed 1.x APIs, other provider backends, graph
compilers, route tables, mutable workflow-state engines, a second checkpoint
store, or a legacy persistence path.

## Design before code

Answer these as design questions, not mandatory metadata or files:

1. What outcome and obligations define success?
2. What evidence is authoritative, untrusted, missing, or contradictory?
3. Can one capable provider turn finish the work? What concrete benefit requires
   a durable handoff, separate permission/session, independent review, parallel
   branch, or human decision?
4. What enters and leaves each step, what uncertainty remains, and what may the
   next step assume?
5. How do failure, exhaustion, ambiguity, and unsafe effects recover or escalate?

Keep goals and obligations stable while allowing methods to adapt to discovered
evidence. Start with one provider operation. Split only for a clear reliability,
authority, concurrency, reuse, or recovery benefit.

## Keep control explicit

Use `@workflow` on an ordinary typed sync or async function. Python owns
sequence, `if`/`match` branches, bounded loops, budgets, permissions, joins,
exception handling, and human escalation. Provider turns own semantic judgment,
investigation, and tool-driven work.

Use a nested decorated call for a durable child. Use `parallel` / `aparallel`
only for independent required work; a conditional branch selects one path, while
parallel work executes multiple paths and joins them. Give parallel branches
separate sessions and isolate source when concurrent writes or stable review
require it.

Bound rework and define exhaustion. Apply `provider_budget(...)` around the
whole provider-using workflow when a whole-workflow limit is intended; nested
budget scopes all apply. Do not describe run `timeout` as a wall-clock deadline
for arbitrary Python. A provider-budget breach suspends the run as
`budget_exceeded`; return a typed domain exhaustion result only by checking an
explicit domain bound before another dispatch.

## Choose operations truthfully

| Work | Operation |
| --- | --- |
| Edit, execute tests/builds, or use write-capable tools | `run` / `arun` |
| Inspect without write-producing checks | `query` / `aquery` |
| Transform supplied context; opt into any tools explicitly | `generate` / `agenerate` |
| Custom I/O, subprocesses, clocks, randomness, material reads | `@activity` |
| Typed human authority or missing information | `ask_human` |

`query` and `generate` are fixed read-only, network-off presets. Configure
sandbox, network, tool allowlists, retry policy, and budgets in code—not as
prompt promises. An explicitly enabled remote tool can still have remote effects.
`writes=()` declares no durable artifacts; it does not make a `run` read-only.

Keep every material observation or effect in a recorded operation. Ordinary
workflow Python reruns on resume. Keep custom activities narrow.

## Prompt and hand off evidence

Design prompts around goal, authoritative evidence, obligations, output,
uncertainty, verification, and escalation. Use direct language and only useful
examples. Do not force chain-of-thought or hard-code a long decision procedure
when the provider can adapt from current evidence.

Use `Prompt.file` for substantial colocated prompts and plain strings for short
ones. Prefer typed `input` and `returns`. A schema validates shape, not factual
correctness. Use artifacts only when a file is a deliverable or substantial
handoff. Pass independent reviewers primary evidence and relevant upstream and
current immutable artifacts, not only a producer summary.

Add a reviewer only when rejection changes control flow or protects a material
boundary. Separate its session from the producer. Use `run` if it must execute
checks and make it report passed, failed, and unavailable checks distinctly.
Use `query` for inspection only. Persist a typed review with an activity only if
a file consumer actually needs it. Keep rework bounded and feed exact findings
back to the responsible producer.

## Preserve replay and session semantics

Treat `ledger.jsonl` as the sole replay authority. Completed operations replay.
Prompt, input, read digest, output schema, or effective-configuration changes can
cause replay mismatch. Do not consult live files to skip recorded work or add an
independent resume mechanism.

`retry_safe=True` permits repetition after a confirmed stop; it does not prove
idempotence. Set it false for effects that must not repeat. Do not replace an
unknown or running effect; reconcile it or require operator resolution. Never
claim exactly-once execution.

Reuse a provider for conversation continuity. `with_config` shares its session
unless replaced. Use `Session.task`, `Session.work_item`, or `Session()` for
stable distinct conversations and `session=None` for independent turns. Keep
keys and operation order stable across resume.

Botpipe does not prepare, back up, restore, or roll back the workspace. Artifact
capture validates current bytes but does not prove writer attribution or an
atomic snapshot. Use returned `ArtifactHandle` values as immutable reads. Use
`Worklist.from_artifact` for stable item selection and call `complete` only after
acceptance.

## Validate outcomes

1. Import the workflow and inspect its typed callable contract.
2. Run focused tests with `FakeProvider`, without live credentials.
3. Cover the useful success path plus material rejection, exhaustion,
   pause/resume, and uncertain-effect paths. Confirm replay makes no new provider
   call for completed work.
4. Assert domain outcomes, artifacts, routing, budgets, and policy—not exact
   prompt prose, private model reasoning, or one exact tool sequence.
5. Run `botpipe workflows show module:function` when available.
6. Distinguish deterministic checks from live-provider validation and report any
   remaining runtime-dependent risk. Do not claim quality, cost, or performance
   improvements without measured evidence.
