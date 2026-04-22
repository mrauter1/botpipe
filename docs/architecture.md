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

## Workflow Packages

Repo-root `workflows/` is a regular Python package reserved for actual workflow packages. Each workflow package is also a regular package and must include:

- `__init__.py`
- `workflow.py`
- `workflow.toml`
- `prompts/`
- `assets/`

Minimum structure:

```text
workflows/
  __init__.py
  child_workflow/
    __init__.py
    workflow.toml
    workflow.py
    prompts/
    assets/
```

Workflow packages are both runnable entrypoints and reusable building blocks. Package `__init__.py` must re-export the main workflow class so direct imports remain first-class:

```python
from workflows.autoloop_v1 import AutoloopV1
```

`workflow.toml` is metadata-only discovery input. It is limited to human-facing fields such as `name`, `title`, `description`, and `aliases`. It does not define topology, prompts, transitions, parameters, or execution semantics.

Workflow discovery scans `<root>/workflows/*/workflow.toml`, then loads the main workflow class from `workflows.<package>.workflow`.

## CLI Contract

The public executable name is `autoloop`.

The CLI is package-based only:

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

There is no public raw execution mode. The CLI does not accept raw workflow files, module paths, class names, `autoloop exec`, `--class-name`, or legacy request/intent flags.

`autoloop run` is message-first and accepts repeatable workflow-specific parameters through `-wf <name> <value>`.

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
