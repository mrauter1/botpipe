---
name: botpipe-workflow-authoring
description: Author and review durable Botpipe Python workflows, prompts, activities, artifacts, worklists, and tests.
---

# Botpipe workflow authoring

Inspect the repository's current `README.md`, `docs/authoring.md`, and compact
workflows under `botpipe/workflows/` before editing. Repository behavior wins if
this skill is stale.

## Invariant

Python owns control flow. Every material observation or external effect goes
through a recorded Botpipe operation.

Use `@workflow` on an ordinary typed sync or async function. Express decisions,
loops, composition, and returns in Python. Use a nested decorated call for a
durable child and `parallel()` for independent branches. Do not introduce route
tables, transition objects, graph compilation, or mutable workflow-state models.

## Choose the operation boundary

Use `Session.run` or `Session.arun` for provider work. Use `@activity` for custom
I/O such as an API call, subprocess, clock, random source, or material file read.
Use `ask` for typed human input. Use `current_run().operation` only when building
a lower-level integration.

An activity with uncertain external effects should keep `retry_safe=False`.
Interrupted work then requires explicit operator reconciliation. Never describe
Botpipe or a provider conversation as exactly once.

## Prompts, results, and artifacts

Use a plain string for an inline prompt and `Prompt.file` for a prompt beside the
workflow. Prefer typed `input` and `returns` contracts. A strong provider prompt
states the goal, relevant evidence, required output, constraints, validation,
and done criteria without prescribing unnecessary implementation details.

Declare provider destinations with `Artifact.json`, `.md`, `.text`, or `.raw` in
`writes=`. Mark outputs required when later behavior depends on them. Read the
immutable `ArtifactHandle` from `Result.artifacts`; do not treat a live workspace
file as historical state.

Use `Worklist.from_artifact` when code needs durable item selection and
completion. Item IDs must be unique. The runtime snapshots the original
selection, so do not reselect items from a changed live file on resume.

## Sessions and concurrency

Use one session for consecutive calls that benefit from provider conversation
continuity. Use `Session.task(key)` for task continuity and
`Session.work_item(item, key)` for per-item continuity. Use `Session.fresh()` for
independent review. Parallel branches need separate sessions. They may share the
application workspace only for read-only provider work; editing branches require
explicit, isolated `workspace=` paths and distinct artifact destinations.

## Validate

Before finishing:

1. Import the workflow and inspect its typed callable contract.
2. Run focused tests with `FakeProvider`.
3. Cover the meaningful branch, pause, replay, or interruption behavior.
4. Run `botpipe workflows show module:function` when the CLI is available.
5. Report the commands run and any remaining runtime-dependent risk.
