# Architecture

This redesign is greenfield.

Backward compatibility is not a goal for CLI syntax, package names, config filenames, runtime payloads, or on-disk layout. Feature compatibility is still required: pause/resume, checkpoint recovery, tracing, workflow composition, reusable workflow packages, and Autoloop-v1 operational parity must remain available through the new architecture.

## Internal Layout

The internal workflow kernel lives under:

- `core/`
- `runtime/`
- `stdlib/`
- `extensions/`

The public authoring contract does not point workflow authors at internal modules. Authors import the strict root shims:

- `workflow`
- `workflow.primitives`

## Workflow Surfaces

Repo-root `workflows/` remains the common discovery root, but the framework no longer requires one package minimum shape. A workflow may be authored as:

- a single Python file such as `workflows/release_review.py`
- a flow-first package such as `workflows/release_review/flow.py` plus optional `specs.py`
- a mature package such as `workflows/release_review/flow.py` or `workflow.py` plus optional `workflow.toml`, `prompts/`, `assets/`, docs, and tests

Recommended serious-workflow shape:

```text
workflows/
  release_review/
    flow.py
    specs.py
```

`flow.py` plus `specs.py` is the recommended serious-workflow shape, but it is not required.

Supported mature package shape:

```text
workflows/
  release_review/
    __init__.py
    flow.py or workflow.py
    specs.py
    workflow.toml
    prompts/
    assets/
```

Legacy `workflow.py` packages remain supported. A single Python file is also a first-class runnable entrypoint. The framework does not enforce one folder structure for execution.

Workflow packages are still reusable building blocks. When a package uses `__init__.py`, it should re-export the main workflow class so direct imports remain first-class:

```python
from workflows.autoloop_v1 import AutoloopV1
```

`workflow.toml` is optional for execution and metadata-only when present. It is limited to human-facing fields such as `name`, `title`, `description`, and `aliases`. It does not define topology, prompts, transitions, parameters, route policy, artifacts, or execution semantics.

Shallow workflow discovery stays import-free and scans:

- `<root>/workflows/*/workflow.toml`
- `<root>/workflows/*/flow.py`
- `<root>/workflows/*/workflow.py`
- `<root>/workflows/*.py`

Deep inspection and execution may import and compile workflow modules. That richer seam reports compiled step contracts, parameters, prompt paths, support-file paths, and source metadata without widening `workflow.toml`.

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
autoloop run workflows/release_review.py task-1 --message "Review this release"
autoloop run workflows/release_review/flow.py:ReleaseReview task-1 --message "Review this release"
autoloop run workflows.release_review.flow:ReleaseReview task-1 --message "Review this release"
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

Built-in runtime adapters live under `runtime/providers/` and are selected only through `runtime/provider_backends.py`. Those adapters satisfy the existing `LLMProvider` protocol directly:

- `run_producer(...) -> ProducerResponse`
- `run_verifier(...) -> OutcomeResponse`
- `run_llm(...) -> OutcomeResponse`

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

## Recursive Operation

Recursive automation under `recursive_autoloop/` keeps the public name-first package/message-oriented wrapper contract.

- Wrapper start commands use `autoloop run <workflow> <task-id> --root ... --message ...`
- Wrapper resume commands use `autoloop resume <workflow> <task-id> --root ...`
- Recursive memory lives under `.autoloop_recursive/`
- Recursive templates and guidance point readers at `docs/architecture.md`, `docs/authoring.md`, `core/`, `runtime/`, `extensions/`, `stdlib/`, and repo-root `workflows/`

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

Autoloop-v1 parity is now package-local under `workflows/autoloop_v1/`. Framework-owned parity helpers and custom runners are not part of the architecture anymore.
