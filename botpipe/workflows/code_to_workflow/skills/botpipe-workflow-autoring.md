# Botpipe durable workflow authoring

Author workflows as ordinary typed Python functions decorated with `@workflow`.
The function owns branches, loops, exception handling, and nested workflow calls.

Use `Provider` for provider turns. Declare immutable inputs with `reads`, provider
destinations with `Artifact` values in `writes`, and structured output with
`returns`. Use `run` for effectful work, `query` for read-only discovery, and
`generate` for supplied-context judgments. A provider has managed continuity by
default. Pass `Session.task(...)` or `Session.work_item(...)` to
`Provider(session=...)` for stable cross-run continuity, and derive
`provider.with_config(session=None)` for independent review calls.

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
