# Botpipe durable workflow authoring

Design before coding. Identify the outcome and stable obligations, authoritative
and untrusted evidence, human authority, and material failure modes. For each
step, keep its goal, inputs, output, uncertainty, verification, and next-step
assumptions coherent. These are design questions, not required metadata files.

Start with one capable provider operation. Split only when a durable handoff,
different permission or session, independent decision, safe parallelism, reuse,
or failure isolation provides clear value. Python owns branching, bounded loops,
budgets, joins, escalation, and exception handling. Providers own semantic
judgment, investigation, and tool-driven work. Do not generate a generic graph
interpreter, route table, graph compiler, or mutable workflow-state engine.

Use `@workflow` for a durable function and nested decorated calls for durable
children. A conditional branch selects one path; `parallel` executes multiple
independent required paths. Parallel branches need separate sessions and safe
workspace writes. Use `ask_human` for typed authority or missing information.

Choose operations truthfully:

- `run` edits or executes tests/builds;
- `query` performs inspection-only review;
- `generate` transforms supplied context, with any tools explicitly opted in; and
- `@activity` records custom I/O or deterministic file/process work.

Configure sandbox, network, tools, retry policy, and provider budgets in code.
`writes=()` means no durable artifacts, not a read-only call. Never claim tests
ran from a `query`. A response schema validates shape, not correctness.
Provider-budget exhaustion suspends the run as `budget_exceeded`; use a separate
explicit domain bound when the workflow must return a typed exhaustion result.

Use direct prompts that state the goal, evidence priority, obligations, expected
domain output, uncertainty, verification, and escalation. Let methods adapt to
the evidence. Use only examples that teach a stable boundary; do not require
chain-of-thought or hard-code long prose procedures.

Use typed values for decisions and `Artifact` values for file deliverables or
substantial handoffs. Pass returned immutable handles through `reads`. Give an
independent reviewer a separate session plus primary upstream and current
evidence, not only a producer summary. Add review only where rejection changes
control flow or protects a material boundary. Bound rework and feed exact
findings back to the responsible producer.

Reuse a provider for conversation continuity. Use `Session.task` for task
continuity, `Session.work_item` for stable item continuity, `Session()` for a
distinct durable conversation, and `session=None` for independent turns.

Keep every material observation or effect in a recorded operation. Treat
`ledger.jsonl` as the replay authority; do not add a second checkpoint or receipt
store. `retry_safe=True` permits repetition after a confirmed stop but does not
prove idempotence. Unknown effects require reconciliation or operator resolution.
Botpipe does not snapshot or roll back repository edits, and artifact capture
does not prove exclusive writer attribution.

Test with `FakeProvider`. Assert observable domain outcomes, artifacts, routing,
bounds, and replay behavior rather than exact prompt wording or one internal
execution path. Distinguish deterministic tests from live-provider validation.
