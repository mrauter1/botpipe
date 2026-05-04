# Architecture

This project is greenfield. The runtime keeps deterministic execution, package discovery, `workflow.toml` metadata-only behavior, `ctx.invoke_workflow(...)`, checkpoint/resume behavior, tracing, and provider/session boundaries while exposing one active public authoring surface.

## Internal Layout

The internal workflow kernel lives under:

- `core/`
- `runtime/`
- `stdlib/`
- `extensions/`

The public authoring contract does not point workflow authors at internal modules.
Public workflow code imports from `autoloop`.

`autoloop` is the active public authoring surface:

- `Workflow`
- `step`, `produce_verify_step`, `workflow_step`, `python_step`
- `Json`, `Md`, `Text`, `Raw`
- `Prompt`, `Route`, `FINISH`, `SELF`

Legacy aliases are intentionally removed from the active public contract; workflow authoring stays on the canonical `autoloop` surface.

`autoloop.core` remains the internal and power-user kernel surface for strict runtime code and tests. It is not the default public authoring API.

## Workflow Surfaces

Autoloop has exactly two first-class workflow discovery roots:

- package-installed workflows under `autoloop/workflows/`
- workspace-local workflows under `{workspace}/.autoloop/workflows/`

Workspace-local workflow names and aliases override package workflow names and aliases. `{workspace}/workflows/` is not a discovery root.

Package-installed workflows use package directories:

```text
autoloop/workflows/
  release_review/
    __init__.py
    flow.py or workflow.py
    specs.py optional
    workflow.toml
    prompts/
    assets/
```

Workspace-local workflows may be package directories or single files:

```text
{workspace}/.autoloop/workflows/
  release_review/
    flow.py or workflow.py
    specs.py optional
    workflow.toml optional
    prompts/ optional
    assets/ optional

{workspace}/.autoloop/workflows/release_review.py
```

`flow.py` is the preferred scaffold and documentation shape. `workflow.py` remains supported. Workspace-local single-file workflows are supported; package-installed single-file workflows are not.

Workspace-local single Python file workflows remain first-class runnable entries.

Workflow packages are still reusable building blocks. Package-installed workflows should re-export the main workflow class from package `__init__.py`, and package-installed workflows that export `Params` should include `"Params"` in `__all__`.

`workflow.toml` is optional for execution and metadata-only when present. It is limited to human-facing fields such as `name`, `title`, `description`, and `aliases`. It does not define topology, prompts, transitions, parameters, route policy, artifacts, or execution semantics.

Shallow workflow discovery stays import-free and scans only:

- `autoloop/workflows/*/workflow.toml`
- `autoloop/workflows/*/flow.py`
- `autoloop/workflows/*/workflow.py`
- `{workspace}/.autoloop/workflows/*/workflow.toml`
- `{workspace}/.autoloop/workflows/*/flow.py`
- `{workspace}/.autoloop/workflows/*/workflow.py`
- `{workspace}/.autoloop/workflows/*.py`

Deep inspection and execution may import and compile workflow modules. That richer seam reports compiled step contracts, parameters, prompt paths, support-file paths, and source metadata without widening `workflow.toml`.

Route declarations are ordinary Python objects, not a string DSL. Dict transition shorthand still works, but richer public contracts use step-local `routes={...}` plus `Route.to(...)`.

Validation is intentionally split across compile time and runtime. Compile time owns workflow topology, declared names, route legality, declared worklists, artifact-reference ambiguity, callback existence, and schema shape. Runtime owns worklist contents, generated boards, runtime-created prompt context, item-scoped artifact paths, provider failures, and semantic validation that depends on data created during the run.

Provider control routing is intentionally narrow. `question` is the only default runtime control route, and it is provider-visible only when the engine interaction policy allows provider questions. `blocked` and `failed` are never injected by default; if a workflow authors those names explicitly they remain ordinary application routes, while transport and validation failures stay runtime-owned.

Worklists are lazy runtime resources. The compiler validates the declared worklist contract, but the engine does not require the backing source to exist at workflow start. Selection materialization happens when the run first touches the worklist through scoped execution, prompt rendering, session continuity, or explicit context access.

## CLI Contract

The public executable name is `autoloop`.

The CLI remains message-first and workflow-reference oriented:

```bash
autoloop workflows list
autoloop workflows show <workflow>

autoloop run <workflow> <task-id> --message "..."
autoloop resume <workflow> <task-id> [--run-id <run-id>]
autoloop answer <workflow> <task-id> --answer "..." [--run-id <run-id>]

autoloop runs list [--workflow <workflow>] [--task <task-id>] [--status <status>]
autoloop runs show <workflow> <task-id> [--run-id <run-id>]
autoloop logs <workflow> <task-id> [--run-id <run-id>] [--events|--trace|--raw]

autoloop init workflow <name>
```

Workflow references may be names, files, modules, or explicit classes:

```bash
autoloop run release_review task-1 --message "Review this release"
autoloop run .autoloop/workflows/release_review.py task-1 --message "Review this release"
autoloop run .autoloop/workflows/release_review/flow.py:ReleaseReview task-1 --message "Review this release"
autoloop run autoloop.workflows.release_review.workflow:ReleaseReview task-1 --message "Review this release"
```

There is no public raw execution mode. File and module refs resolve through the same workflow runtime path as named workflows rather than bypassing the engine.

`autoloop run` is message-first and accepts repeatable workflow-specific parameters through `-wf <name> <value>`.

Mutating commands also accept generic runtime controls:

- `--provider`
- `--model`
- `--model-effort`
- `--max-steps`

## Provider Selection

Public provider selection is typed and package-runtime-owned. The runtime discovers `autoloop.yaml` or `autoloop.config` from the user config directory and the repo root, then merges those layers with CLI overrides.

Typed example:

```yaml
provider:
  name: claude
  model: claude-sonnet
  model_effort: high
  claude:
    permission_strategy: inherit
runtime:
  max_steps: 100
```

Contract:

- `provider.name` selects the built-in backend, currently `codex` or `claude`
- `provider.model` and `provider.model_effort` are generic typed overrides that target the selected provider
- provider-specific blocks such as `provider.codex.*` and `provider.claude.*` remain typed config, not ad-hoc loader strings
- CLI overrides use `--provider`, `--model`, and `--model-effort`
- provider construction is framework-owned and resolved from the typed provider name

Built-in runtime adapters live under `runtime/providers/` and are selected only through `runtime/provider_backends.py`.

CLI-backed providers now cross the runtime boundary through a shared layered seam:

- `LLMProvider`: the existing semantic engine-facing surface
- `RenderedLLMProvider`: shared runtime prompt rendering plus verifier/LLM outcome parsing
- `ProviderTransport`: CLI transport only

That means Codex and Claude transports receive only shared rendered turns and return only raw assistant text plus session metadata. They do not render workflow prompts, inject workflow contracts, or parse workflow outcome JSON themselves.

The shared renderer injects a compact human-readable Runtime Step Contract with readable inputs, required inputs, writable artifacts, route-specific output requirements, explicit expected output payload requirements, available routes, route summaries, optional route handoff, and optional retry feedback.

Provider raw output is runtime telemetry. It remains available to logs, traces, extension events, debugging, and replay, but it is not rendered back into provider prompts.

Provider loading is not a public factory surface. Operators stay on typed config plus the generic CLI flags above.

## Resumability

Provider resumability is modeled as an opaque continuation token stored in `session_id`.

Framework-owned persisted session payloads use canonical fields such as:

- `provider`
- `session_id`
- `provider_metadata`
- `model_override`
- `effort_override`
- `pending_clarification_note`
- timestamps

`session_id` is the only cross-provider continuation handle in the runtime model. Provider-specific extra state belongs under `provider_metadata`.

Verifier and single-LLM turns remain strict runtime contracts: built-in CLI adapters must return machine-parseable JSON outcomes that the runtime validates locally before the workflow engine accepts them. Provider-specific continuation aliases do not leak into framework-owned session payloads.

Sessions now distinguish slot, default continuity policy, and explicit runtime overrides:

- `Session` names a provider conversation slot
- `Continuity` defines the default reuse policy for that slot
- `ctx.open_session(..., scope=...)` remains supported as an explicit runtime binding override

`scope=` is not deprecated. `ctx.open_session(session)`, `ctx.open_session(session, scope="cluster-1")`, and positional `ctx.open_session(session, "cluster-1")` remain valid public behavior.

Artifact contracts and provider-output contracts are separate:

- artifact schema validates files written to disk
- `expected_output_schema` validates `Outcome.payload`

## Workspace Layout

Runtime data lives under task, workflow, and run scopes:

```text
.autoloop/
  tasks/
    <task-id>/
      task.json
      request.md
      messages.jsonl

      wf_<workflow_name>/
        workflow.json
        runs/
          <run-id>/
            request.md
            run.json
            events.jsonl
            checkpoint.json
            sessions/
            trace.jsonl
            raw/
            children.jsonl
            parent.json
```

Semantics:

- task scope stores shared task files plus the append-only `messages.jsonl` ledger
- workflow scope stores persistent workflow-level state for one workflow on one task
- run scope stores immutable request snapshots and run-local execution artifacts

The task `request.md` is the latest rendered request snapshot for the task. Each run also stores its own immutable `request.md` snapshot at run start.

## Runtime Observability

Runtime observability is runtime-owned and enabled by default.

- Runtime git tracking uses `git add --all` plus deterministic `autoloop: ...` commit messages.
- The repository must be clean before a git-tracked run or resume starts.
- Git commits are the workspace replay boundary.
- Autoloop does not classify changed paths for replay.
- `trace.jsonl`, `git_tracking.jsonl`, `static_step_graph.json`, and runtime-owned `raw/` outputs are written without requiring workflow declarations.

Normal runs write runtime-owned evidence under each run folder:

- `trace.jsonl`
- `git_tracking.jsonl`
- `static_step_graph.json`
- `raw/`

`run.json` summarizes the runtime-owned tracing and git-tracking state.

Workflows do not declare `GitTracking` or `Tracing`; runtime observability is configured only through `autoloop.runtime.config`.

`workflow_run_traces_to_optimization_candidates` consumes runtime-owned `run.json`, `events.jsonl`, `trace.jsonl`, `git_tracking.jsonl`, `static_step_graph.json`, and `raw/` evidence.

The optimizer is a bundled authoring-only workflow:

- it emits candidate-only optimization artifacts plus `workflow_refinement_evidence.json`
- it does not mutate the selected workflow source
- it does not run the selected workflow by default
- it does not execute ablations by default

## Recursive Operation

Recursive automation under `recursive_autoloop/` keeps the globally installed Autoloop CLI contract.

- Wrapper start commands use `autoloop --workspace ... --task-id ... --intent ... --pairs ...`
- Wrapper resume commands use `autoloop --workspace ... --task-id ... --resume`
- Recursive memory lives under `.autoloop_recursive/`
- Recursive templates and guidance point readers at `docs/architecture.md`, `docs/authoring.md`, `core/`, `runtime/`, `extensions/`, `stdlib/`, `autoloop/workflows/`, and `.autoloop/workflows/`

## Composition And Parity

Sub-workflows are first-class. Runtime-backed contexts expose:

```python
ctx.invoke_workflow(...)
```

Supported forms:

```python
ctx.invoke_workflow("child_workflow", message="Do the child task", parameters={"mode": "strict"})
ctx.invoke_workflow(ChildWorkflow, message="Do the child task", parameters={"mode": "strict"})
```

Child runs stay under the same task but get their own workflow namespace, run id, checkpoint, event log, trace, sessions, and run-local request snapshot. Parent-child linkage is metadata-only through `children.jsonl` and `parent.json`; child runs are never nested under parent run folders.

Autoloop-v1 parity is now package-local under `autoloop/workflows/autoloop_v1/`. Framework-owned parity helpers and custom runners are not part of the architecture anymore.
