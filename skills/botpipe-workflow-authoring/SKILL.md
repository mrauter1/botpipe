---
name: botpipe-workflow-authoring
description: Author and review Botpipe 2.0 provider-first workflows, prompts, activities, artifacts, worklists, and tests.
---

# Botpipe workflow authoring

Read the repository's current `README.md`, `docs/authoring.md`, and nearby
packaged workflows before editing. Repository behavior wins if this skill is
stale.

## Core rule

Providers perform work; sessions carry conversation continuity; Python
expresses the process; the runtime records operations and outcomes.

Use `@workflow` on an ordinary typed sync or async function. Express decisions,
loops, composition, and returns in Python. Use a nested decorated call for a
durable child and `parallel`/`aparallel` for independent branches. Do not add a
graph, route table, or mutable workflow-state model.

## Choose provider authority

Use a `Provider`, never `Session.run`, for provider work.

- `generate` consumes supplied context. It has no autonomous tools or commands
  by default. When essential, grant a complete exact read-only argv tuple with
  `allow_commands`; do not grant patterns or shell strings.
- `query` may gather information through enforced read-only tools and commands
  inside its effective scope. It cannot write or mutate remote state.
- `run` may edit and invoke effects within policy. Use it for checks with side
  effects and for provider-written artifacts.
- `decide` preserves a decision provider's native typed question/answer model.

Use `output_retries` only for bounded typed-output repair. Do not describe it as
transport retry or uncertain-effect recovery.

Use `@activity` for application I/O such as an API call, subprocess, clock,
random source, or material file read. Set `retry_safe=False` when an unfinished
call needs explicit reconciliation before repetition. Use `ask_human` for typed
operator input; answers target the pending operation ID.

## Sessions and configuration

`Provider()` is the ordinary spelling and uses configured default selection.
Do not hardcode a vendor in a reusable workflow. There is no implicit Codex
fallback.

One provider has a managed session by default. Derive roles with
`provider.with_config(...)`; variants share the selected backend and session.
Use `Provider(session=Session())` or a variant with a new `Session()` for an
independent continuing conversation. Use `session=None` for independent calls.
Never call provider operations on a Session.

Parallel branches need distinct sessions. Editing branches additionally need
isolated workspaces and distinct artifact destinations.

## Prompts, results, and artifacts

Use plain strings for inline prompts and `Prompt.file` for prompts beside the
workflow. Prefer typed `input` and `returns`. Put reusable Pydantic models,
dataclasses, and enums at module scope so recovery can import their contracts.

Declare provider outputs with `Artifact.json`, `.md`, `.text`, or `.raw` in
`writes=`. Mark outputs required when later behavior depends on them. Read
immutable handles from `Result.artifacts`; never treat a live workspace file as
historical evidence. Preserve every distinct required and optional document in
an existing workflow contract.

Use `Worklist.from_artifact` for durable item selection and completion. Item IDs
must be unique. Resume keeps the recorded selection, order, and payload.

## Validation

Before finishing:

1. Import the workflow and inspect its typed callable contract.
2. Run focused tests with deterministic fake providers.
3. Cover meaningful branch, pause, replay, and interruption behavior.
4. Confirm catalog listing does not import workflow modules.
5. Report commands run and native-provider behavior that remains unproven.

Fake-provider tests prove runtime behavior only. Do not claim native adapter
support without integration evidence for the advertised operation, including
fresh and resumed sessions where applicable.
