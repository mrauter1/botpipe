# Botpipe durable workflow authoring

Author workflows as ordinary typed Python functions decorated with `@workflow`.
The function owns branches, loops, exception handling, and nested workflow calls.

Use `Provider` for Codex turns. Declare immutable inputs with `reads`, provider
destinations with `Artifact` values in `writes`, and structured output with
`returns`. A provider owns a lazy session; derive role-specific providers with
`with_config`. Pass `Session.task` for cross-run task continuity,
`Session.work_item` for stable work-item continuity, and `session=None` for an
independent review. Use `query` with a typed verdict for read-only reviews and
persist any requested review file in a deterministic `@activity`. Use `run` when
a review must execute tests. Add reviewers only at material gates where their
typed verdict changes the next action.

Use `@activity` for custom filesystem or process I/O. Keep unsafe activities
small and do not claim exactly-once external effects. Use `ask_human` for durable user
input, `parallel` for independent branches, and nested decorated function calls
for durable child workflows.

Artifacts are explicit file contracts. Provider-written required artifacts must
be created in the current turn. Use returned `ArtifactHandle` snapshots as later
reads. Use `Worklist.from_artifact` when a generated JSON plan drives stable
items and call `complete` only after independent acceptance.

Return typed domain values. Do not recreate a generic graph interpreter, route
table, graph compiler, or state-machine abstraction around normal Python flow.
Do not create a second durable checkpoint or receipt store; the run ledger owns
history and replay, and session bindings own conversation continuity.
