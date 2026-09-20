# Botpipe durable workflow authoring

Author workflows as ordinary typed Python functions decorated with `@workflow`.
The function owns branches, loops, exception handling, and nested workflow calls.

Use `Session` for provider turns. Declare immutable inputs with `reads`, provider
destinations with `Artifact` values in `writes`, and structured output with
`returns`. Give distinct long-lived roles distinct session keys. Use
`Session.task` for cross-run task continuity, `Session.work_item` for stable
work-item continuity, and `Session.fresh` for independent reviews.

Use `@activity` for custom filesystem or process I/O. Keep unsafe activities
small and do not claim exactly-once external effects. Use `ask` for durable user
input, `parallel` for independent branches, and nested decorated function calls
for durable child workflows.

Artifacts are explicit file contracts. Provider-written required artifacts must
be created in the current turn. Use returned `ArtifactHandle` snapshots as later
reads. Use `Worklist.from_artifact` when a generated JSON plan drives stable
items and call `complete` only after independent acceptance.

Return typed domain values. Do not recreate a generic graph interpreter, route
table, graph compiler, or state-machine abstraction around normal Python flow.
