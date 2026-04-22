This plan is grounded in the uploaded codebase and explicitly replaces its current raw-target CLI, `autoloop_v3.workflow` / `autoloop_v3.workflows` internal layout, direct `tasks/<task>/runs/<run>` runtime layout, and retained operational compatibility posture.   

````markdown
# Autoloop Greenfield Redesign Plan

## 0. Non-negotiable project stance

This project is **greenfield**.

It is **not** required to preserve backward compatibility in:
- CLI syntax
- Python module/package names
- import paths
- config filenames
- config wire formats
- on-disk workspace layout
- persisted session payload formats
- legacy status strings
- raw parsing formats
- compatibility shims of any kind

What **is** required is:
- **functional compatibility**
- **feature compatibility**
- improvements over the old implementation are explicitly allowed
- **feature regressions are not allowed**

Interpretation:
- preserve or improve the capabilities the system supports
- preserve or improve user-visible workflow behavior and outcomes
- do not preserve legacy quirks just because they existed
- prefer stricter, typed, explicit designs over legacy loose formats

Examples of acceptable improvements:
- replacing raw YAML parsing with JSON validated by schema
- replacing free-form parsing with structured outputs
- replacing compatibility shims with one strict canonical model
- changing folder structure if capabilities are preserved or improved
- changing CLI syntax if the new CLI fully covers the old capabilities

Examples of unacceptable regressions:
- losing pause/resume
- losing checkpointed recovery
- losing tracing or git tracking where still needed
- losing workflow composition / sub-workflows
- losing Autoloop-v1 behaviors that matter operationally
- losing workflow package reuse as building blocks

In short:
- **wire compatibility may break**
- **capability compatibility may not**

---

## 1. Final architecture

### 1.1 Internal framework package layout

Rename the internal strict kernel from:

- `autoloop_v3.workflow`

to:

- `autoloop_v3.core`

Final internal framework layout:

```text
autoloop_v3/
  core/
  runtime/
  stdlib/
  extensions/
````

### 1.2 Workflow package namespace

Reserve repo-root `workflows/` exclusively for actual workflow packages.

Final layout:

```text
workflows/
  __init__.py
  <workflow_name>/
    __init__.py
    workflow.toml
    workflow.py
    prompts/
    assets/
```

Delete framework-owned `autoloop_v3.workflows`.

Any parity helpers, conventions, sidecar logic, or workflow-specific support code must live inside the workflow package that needs them.

### 1.3 Public authoring shim

Keep the root `workflow` import surface as a **strict re-export-only authoring shim** so authors continue to write:

```python
from workflow import (
    Workflow,
    Context,
    Session,
    Artifact,
    Prompt,
    PairStep,
    LLMStep,
    SystemStep,
    SUCCESS,
    PAUSE,
    FAIL,
    GLOBAL,
)
from workflow.primitives import Event, Outcome, Checkpoint, ResolvedArtifacts
```

Rules:

* keep the authoring surface strict and minimal
* do not expose engine/compiler internals at the root
* do not expose compatibility aliases
* do not expose old legacy symbols

---

## 2. Workflow packages

## 2.1 Every workflow is a regular Python package

Every workflow package must:

* live under `workflows/<workflow_name>/`
* include `__init__.py`
* include `workflow.py`
* include `workflow.toml`
* be importable as a normal Python package

Top-level `workflows/` must also be a regular package and include `workflows/__init__.py`.

This is intentional. We are **not** using namespace packages here.

## 2.2 Workflow packages are both runnable units and reusable building blocks

A workflow package’s main workflow class is:

* a top-level runnable workflow
* a reusable building block for other workflows

This is a first-class design goal.

Direct imports like this are explicitly supported:

```python
from workflows.child_workflow import ChildWorkflow
```

This is not a workaround. It is part of the architecture.

## 2.3 Required package structure

Minimum required structure:

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

Recommended optional structure:

```text
workflows/
  <workflow_name>/
    params.py
    parity.py
    conventions.py
    helpers.py
    api.py
    contracts.py
    tests/
```

## 2.4 Required `__init__.py` behavior

Every workflow package must re-export its main workflow class from `__init__.py`.

Required pattern:

```python
from .workflow import ChildWorkflow

__all__ = ["ChildWorkflow"]
```

If the workflow defines parameters, it may also re-export them:

```python
from .workflow import ChildWorkflow
from .params import Parameters

__all__ = ["ChildWorkflow", "Parameters"]
```

---

## 3. Workflow manifest contract

Each workflow package must contain `workflow.toml`.

Purpose of `workflow.toml`:

* discovery metadata only
* human-facing metadata only
* aliases/title/description only

It must **not** become a second DSL.

It must **not** define:

* topology
* transitions
* session behavior
* prompts
* domain semantics
* workflow logic

Recommended schema:

```toml
name = "child_workflow"
title = "Child Workflow"
description = "Reusable child workflow package"
aliases = ["child"]
```

Discovery behavior:

* CLI discovers packages by scanning `<root>/workflows/*/workflow.toml`
* workflow package convention is authoritative
* execution entrypoint is `workflows.<name>.workflow`
* the main workflow class is discovered from that module
* metadata comes from `workflow.toml`

---

## 4. Final CLI contract

## 4.1 Delete raw execution

Delete the public raw-target execution model entirely.

There must be no public:

* `autoloop exec`
* raw workflow file path execution
* raw import string execution
* public `--class-name`
* public raw module/class loader workflow targeting

The public CLI must be fully package-based.

## 4.2 Required commands

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

## 4.3 Behavioral rules

### `autoloop run`

* starts a new run of a discovered workflow package
* requires `--message`
* accepts repeatable `-wf` parameter pairs

### `autoloop resume`

* resumes the latest resumable run for the given workflow/task if `--run-id` is omitted
* may target a specific run with `--run-id`

### `autoloop answer`

* resumes a paused run with an explicit answer
* answer remains distinct from message
* may target a specific run with `--run-id`

### `autoloop runs show` and `autoloop logs`

* `--run-id` is diagnostic/advanced
* normal users should not need to know run ids most of the time

---

## 5. Workflow-specific parameters

Support repeatable workflow-specific parameters through:

```bash
-wf <parameter_name> <value>
```

Example:

```bash
autoloop run child_workflow task-1 \
  --message "Do this" \
  -wf mode strict \
  -wf reviewer security \
  -wf fast true
```

Rules:

* `-wf` is repeatable
* parse as ordered name/value pairs
* resolve into a dict
* validate and coerce with the target workflow package’s parameters model
* persist resolved parameters in run metadata
* parameters are immutable for the life of that run
* unknown workflow parameters must fail before execution starts
* `-wf` must never override generic runtime/provider controls

---

## 6. Message model

Replace public “intent” terminology with “message” everywhere.

Remove public concepts like:

* `intent_mode`
* `product_intent`
* public `request_text` semantics

Final message model:

* `--message` is the first-class input to `autoloop run`
* task scope stores append-only `messages.jsonl`
* task scope stores rendered current snapshot in `request.md`
* each run stores its own immutable `request.md` snapshot at run start
* `answer` remains distinct from `message`

If any overwrite or preserve operations are still needed, expose them through explicit task-management commands later, not as generic run flags.

---

## 7. Final filesystem layout

Keep:

* `.autoloop/tasks/` plural
* `runs/` as the run directory name

Final workspace layout:

```text
.autoloop/
  tasks/
    <task-id>/
      task.json
      request.md
      messages.jsonl
      {top-level shared task files}

      wf_<workflow_name>/
        workflow.json
        {workflow-specific task-level files}

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

## 7.1 Scope semantics

### Task scope

Shared across all workflows on that task:

* `task.json`
* `request.md`
* `messages.jsonl`
* any top-level task files

### Workflow scope

Persistent across multiple runs of the same workflow on the same task:

* `.autoloop/tasks/<task-id>/wf_<workflow_name>/...`

### Run scope

Immutable or run-local execution artifacts:

* run-local `request.md`
* `run.json`
* `events.jsonl`
* `checkpoint.json`
* `sessions/`
* `trace.jsonl`
* run-local sidecars

Rules:

* `wf_<workflow_name>` must sit above `runs/`
* do not place `wf_<workflow_name>` inside `runs/<run-id>/`
* do not flatten workflow scope away; it exists for persistent workflow-level files across runs

---

## 8. Placeholder model

Keep existing placeholders:

* `task_folder`
* `run_folder`
* `state.*`

Add new required placeholders:

* `workflow_folder`
* `package_folder`
* `workflow_name`

Definitions:

* `task_folder` = `.autoloop/tasks/<task-id>`
* `workflow_folder` = `.autoloop/tasks/<task-id>/wf_<workflow_name>`
* `run_folder` = `.autoloop/tasks/<task-id>/wf_<workflow_name>/runs/<run-id>`
* `package_folder` = `<root>/workflows/<workflow_name>`
* `workflow_name` = discovered workflow package name

Recommended request artifact rule for new workflows:

* canonical run request input should be `Artifact("{run_folder}/request.md")`
* current task request remains available at `Artifact("{task_folder}/request.md")` when needed

Rule:

* `package_folder` is read-only package content location
* mutable artifacts must never be written into `package_folder`

---

## 9. Context model

Extend `Context` with:

* `workflow_name`
* `workflow_folder`
* `package_folder`
* `workflow_params`
* `invoke_workflow(...)`

Keep:

* `task_id`
* `run_id`
* `task_folder`
* `run_folder`
* `state`
* session accessors
* `answer`

Rules:

* do not remove `run_id`
* do not remove `run_folder`
* sub-workflow invocation must be available through `Context`
* `workflow_params` must expose validated/coerced workflow parameters

---

## 10. Binding model

Extend `RunBinding` with:

* `workflow_folder`
* `package_folder`

Keep:

* `root`
* `task_id`
* `run_id`
* `workflow_name`
* `task_folder`
* `run_folder`

Do not rename `run` to `invocation`. Keep `run`.

---

## 11. Loader and discovery model

## 11.1 Public discovery

Public CLI discovery must scan:

* `<root>/workflows/*/workflow.toml`

Rules:

* `workflows/` is a regular package
* each workflow package is a regular package
* workflow directory name is the canonical key unless manifest overrides it
* package metadata is sourced from `workflow.toml`
* main workflow class is sourced from `workflow.py`

## 11.2 Internal loading

Support:

* loading by workflow package name
* loading by imported workflow class for sub-workflow composition

When passed a workflow class, the runtime must derive:

* workflow name
* package root
* parameters model
* package metadata

Class-based sub-workflow invocation is first-class and supported.

---

## 12. Prompt and asset resolution

Package-local prompts and assets are first-class.

Final resolution order:

1. workflow package root
2. explicit absolute path when author explicitly uses one
3. never current working directory

Rules:

* `Prompt("prompts/ask.md")` resolves relative to the workflow package root
* bundled templates/assets resolve relative to the package root
* mutable artifacts must never be written into the package root
* package contents are inputs only

---

## 13. Workflow parameter model

Each workflow package may define an optional Python parameters model.

Convention:

* package may export `Parameters`
* `__init__.py` may re-export `Parameters`
* implementation may live in `params.py`

Loader behavior:

* if `Parameters` exists, validate/coerce `-wf` input through it
* if `Parameters` does not exist, reject any `-wf` usage for that workflow

Persist resolved parameters into `run.json`.

---

## 14. Sub-workflows

## 14.1 Core rule

Sub-workflows are first-class and must support both:

* being run top-level from the CLI
* being imported and invoked as building blocks by other workflows

## 14.2 Supported invocation forms

By imported class:

```python
from workflows.child_workflow import ChildWorkflow

result = ctx.invoke_workflow(
    ChildWorkflow,
    message="Do the child task",
    parameters={"mode": "strict"},
)
```

By workflow package name:

```python
result = ctx.invoke_workflow(
    "child_workflow",
    message="Do the child task",
    parameters={"mode": "strict"},
)
```

## 14.3 Invocation rules

* callable from runtime-backed contexts
* supported from `SystemStep` handlers
* child workflow runs under the same `task_id`
* child workflow gets its own `run_id`
* child workflow gets its own workflow namespace
* child workflow gets its own `events.jsonl`
* child workflow gets its own `checkpoint.json`
* child workflow gets its own `sessions/`
* child workflow gets its own run-local `request.md`
* no implicit session inheritance from parent to child
* parent-child relationship is metadata, not nested folder structure

## 14.4 Child folder structure

Example:

```text
.autoloop/tasks/task-1/
  wf_parent/
    runs/run-parent/
      children.jsonl

  wf_child/
    runs/run-child/
      request.md
      events.jsonl
      checkpoint.json
      sessions/
      parent.json
```

Rules:

* do not physically nest child runs under parent run folders
* parent run keeps `children.jsonl`
* child run keeps `parent.json`

## 14.5 Return contract

`ctx.invoke_workflow(...)` must return a structured result object including at least:

* child workflow name
* child run id
* terminal status
* last event
* selected output metadata / references
* child run path references as needed

---

## 15. Extension seam

Keep the current minimal extension seam philosophy.

Do **not** introduce:

* a plugin platform
* a generic event bus
* arbitrary runtime hooks
* a second execution model

The extension seam remains for orthogonal side effects only.

## 15.1 Required change for parity without custom runners

Because custom runners are forbidden in the new architecture, enrich `StepFinish` enough so workflow-package-owned parity code can implement its side effects through the general runtime.

Required additions:

* `producer_raw_output: str | None`
* optionally `verifier_raw_output: str | None`

This is required so workflows like `autoloop_v1` can reconstruct raw pair-step logs without a special provider wrapper or special harness.

Keep:

* generic `events.jsonl`
* workflow-owned sidecars outside the generic event stream

---

## 16. Autoloop-v1 migration

Move Autoloop-v1 into a real workflow package:

```text
workflows/
  autoloop_v1/
    __init__.py
    workflow.toml
    workflow.py
    prompts/
    assets/
    parity.py
    conventions.py
```

Delete framework-owned:

* `autoloop_v3.workflows.autoloop_v1_parity`
* `autoloop_v3.workflows.autoloop_v1_conventions`

Do not keep `run_autoloop_v1(...)`.

Autoloop-v1 must run through the same general CLI/runtime path as everything else.

Recreate parity through package-local code:

* package-local session path strategy
* package-local parity extension(s)
* package-local helper modules
* general runtime only

Parity behaviors that must still exist:

* `sessions/plan.json`
* `sessions/phases/{phase}.json`
* `raw_phase_log.md`
* `decisions.txt`
* clarification persistence
* question / blocked / failed mapping

Implementation details may change.
Capabilities may not regress.

---

## 17. Git tracking

Tracing remains run-local.

Git tracking must change default scope from **task scope** to **workflow scope**.

Reason:

* once multiple workflows share one task, task-scoped git tracking is too broad

Required changes:

* default GitTracking scope = `workflow_folder`
* not `task_folder`
* rename helper utilities accordingly
* update all tests that assume task-scoped git behavior

---

## 18. Runtime/config cleanup

This is greenfield. Remove compatibility-only runtime behavior unless it still serves the new architecture on its own merits.

Delete or redesign compatibility-only behaviors such as:

* legacy `thread_id` payload handling
* legacy-readable status values
* legacy config discovery such as `superloop.*`
* resume-root compatibility for old layouts
* compatibility-only tests

Generic config remains small and typed, but it is no longer obligated to preserve old wire formats or old filenames.

---

## 19. Module-by-module changes

### `autoloop_v3/core/*`

* rename `workflow/` to `core/`
* update internal imports
* preserve strict root `workflow` shim
* add new placeholders
* add new `Context` fields
* add `Context.invoke_workflow(...)`
* extend `RunBinding`
* enrich `StepFinish`
* add narrow internal workflow invoker protocol

### `runtime/cli.py`

* replace single raw-target parser with subcommand tree
* remove raw-target public execution
* remove public `--class-name`
* remove public raw file/module targeting
* add all required package-based commands
* add repeatable `-wf`

### `runtime/runner.py`

* public execution path becomes package-based
* keep `run_id`
* replace public request/intent semantics with message semantics
* add workflow discovery
* add parameters validation
* add sub-workflow invocation support
* support class-based and name-based child invocation

### `runtime/workspace.py`

* change layout to task -> workflow -> runs
* add workflow workspace abstraction
* add `messages.jsonl`
* keep task-level `request.md`
* keep run-level immutable `request.md`
* update resume-state logic

### `runtime/prompts.py`

* resolve relative to workflow package root
* never depend on cwd

### `runtime/loader.py`

* add workflow package discovery helpers
* support imported workflow class resolution
* keep raw loader internal only if still needed for tests

### `runtime/stores/filesystem.py`

* update filesystem paths to the new layout
* keep session files run-local
* remove compatibility-only wire handling unless still explicitly chosen

### `extensions/git/*`

* change default path scoping from task to workflow
* rename helpers accordingly

### `extensions/session_paths.py`

* keep session path strategy run-scoped:

  * `path_for(run_dir, ref_name, scope)`

---

## 20. Documentation rewrite

Rewrite docs so they no longer describe:

* `autoloop_v3.workflow` as the internal kernel package
* `autoloop_v3.workflows` as framework-owned parity helpers
* raw-target public CLI
* retained operational compatibility as a requirement
* direct `tasks/<task>/runs/<run>` layout
* special `run_autoloop_v1(...)` harness

Docs must now describe:

* `autoloop_v3.core`
* repo-root `workflows/` as actual workflow packages
* regular Python packages with `__init__.py`
* direct import of main workflow classes between workflows
* class-based and name-based `ctx.invoke_workflow(...)`
* package-based CLI
* message-first contract
* task -> workflow -> runs layout
* greenfield / no backward compatibility
* feature compatibility only
* improvements over legacy parsing/formatting are encouraged

---

## 21. Tests

Update or replace all tests that currently pin:

* old namespace layout
* raw-target public CLI
* old workspace structure
* compatibility-only features
* task-scoped git tracking
* custom Autoloop-v1 runner

Required new coverage:

1. workflow package discovery from repo-root `workflows/`
2. required `__init__.py` import contract
3. direct import of main workflow classes
4. package-based CLI commands
5. `-wf` parsing and validation
6. task -> workflow -> runs workspace creation
7. task-level `messages.jsonl`
8. run-level immutable request snapshots
9. package-root prompt resolution
10. workflow-folder placeholder resolution
11. class-based sub-workflow invocation
12. name-based sub-workflow invocation
13. parent-child linkage metadata
14. git tracking scoped to `workflow_folder`
15. tracing still run-local
16. Autoloop-v1 parity via package-local code only
17. root `workflow` shim still exposing only strict authoring surface

---

## 22. Implementation order

Execute in this order:

1. Rename internal kernel package to `core`, preserve strict root `workflow` shim.
2. Create repo-root `workflows/` regular package.
3. Implement workflow package discovery.
4. Enforce workflow package `__init__.py` export contract.
5. Add task -> workflow -> runs workspace model.
6. Add message ledger and run-local immutable request snapshots.
7. Add `workflow_folder`, `package_folder`, and `workflow_params`.
8. Redesign public CLI around workflow packages.
9. Add `-wf` parsing and parameters validation.
10. Add `Context.invoke_workflow(...)`.
11. Support imported workflow classes as child building blocks.
12. Add parent-child metadata and child run creation.
13. Enrich `StepFinish` for package-local parity reconstruction.
14. Migrate Autoloop-v1 into `workflows/autoloop_v1/`.
15. Delete framework-owned parity modules.
16. Change git tracking default scope to workflow scope.
17. Rewrite docs.
18. Rewrite tests.
19. Remove old public raw-target CLI path completely.
20. Remove legacy compatibility-only code.

---

## 23. Definition of done

The redesign is complete only when all of the following are true:

* internal kernel code lives under `autoloop_v3.core`
* root `workflow` remains a strict authoring shim
* repo-root `workflows/` is a regular package
* every workflow package is a regular package with `__init__.py`
* workflows can import each other’s main workflow classes directly
* public CLI never accepts raw workflow file/module/class targets
* public CLI is fully package-based
* `message` is first-class and public intent terminology is gone
* `-wf` works and is package-validated
* workspace layout is `tasks/<task-id>/wf_<workflow>/runs/<run-id>`
* sub-workflows run as first-class child runs
* `ctx.invoke_workflow(...)` supports imported workflow classes as building blocks
* Autoloop-v1 runs through the general runtime with no custom runner
* package-local parity helpers fully replace framework-owned parity modules
* git tracking scopes to workflow folder by default
* tracing remains run-local
* backward compatibility is not treated as a requirement anywhere
* feature regressions are rejected
* all docs and tests pass under the new architecture

```
```
CLI CONTRACT:
```
````markdown id="k5mmhv"
# Standalone CLI Contract Plan

## 1. Goal

Design a package-based CLI for a workflow framework where:

- workflows are first-class named packages
- the CLI is the primary user-facing execution interface
- the CLI is message-first
- workflows may be run directly or composed by other workflows
- workflow-specific parameters are supported
- raw file/module/class execution is not part of the public CLI

This is a greenfield CLI contract. Backward compatibility with legacy CLI syntax is not required. Feature regressions are not allowed.

---

## 2. Core CLI principles

The CLI must follow these principles:

1. **Workflow-first**
   - Users invoke workflows by workflow package name, not by Python path or module path.

2. **Message-first**
   - The main input for a new workflow run is a `--message` argument.
   - Resume answers are a separate concept and use `--answer`.

3. **No raw execution mode**
   - There is no public `exec` command.
   - There is no public command that accepts raw Python files, module names, or class names.

4. **Package discovery**
   - The CLI operates on discovered workflow packages only.

5. **Simple primary path, powerful secondary controls**
   - Most users should not need run ids.
   - Advanced diagnostics may still use `--run-id`.

6. **Strict namespacing**
   - Generic runtime/provider options stay separate from workflow-specific parameters.

---

## 3. Public command surface

The public command tree must be:

```bash
flowpath workflows list
flowpath workflows show <workflow>

flowpath run <workflow> <task-id> --message "..."
flowpath resume <workflow> <task-id> [--run-id <run-id>]
flowpath answer <workflow> <task-id> --answer "..." [--run-id <run-id>]

flowpath runs list [--workflow <workflow>] [--task <task-id>] [--status <status>]
flowpath runs show <workflow> <task-id> [--run-id <run-id>]
flowpath logs <workflow> <task-id> [--run-id <run-id>] [--events|--trace|--raw]

flowpath init workflow <name>
````

---

## 4. Command semantics

## 4.1 `workflows list`

Purpose:

* list all discovered workflow packages available to the framework

Behavior:

* returns one row/item per workflow package
* shows at minimum:

  * workflow name
  * title (if available)
  * description (if available)
  * aliases (if available)

Rules:

* must not import arbitrary workflow code just to render the list if metadata can be read from manifests
* should be fast and deterministic

Example:

```bash id="xr9huh"
flowpath workflows list
```

---

## 4.2 `workflows show <workflow>`

Purpose:

* display detailed information about one workflow package

Behavior:

* resolves the named workflow
* shows:

  * canonical name
  * title
  * description
  * aliases
  * whether workflow-specific parameters are supported
  * parameter names and types if available
  * package location
  * main workflow class name if available

Rules:

* `<workflow>` may be either canonical name or alias
* if ambiguous, fail clearly and show matches

Example:

```bash id="qh64vb"
flowpath workflows show child_workflow
```

---

## 4.3 `run <workflow> <task-id> --message "..."`

Purpose:

* start a new run of a workflow for a task

Required arguments:

* `<workflow>`
* `<task-id>`
* `--message`

Optional arguments:

* repeatable `-wf <name> <value>`
* generic runtime/provider flags
* optional verbosity/output flags

Behavior:

* resolves workflow package
* validates workflow-specific parameters
* creates a new run
* records the current message snapshot for that run
* starts execution

Rules:

* `--message` is required
* every `run` creates a new run id
* command must not silently resume an existing run
* if workflow parameters are invalid, fail before execution starts
* if workflow is unknown, fail before execution starts

Example:

```bash id="fo6yyo"
flowpath run child_workflow task-1 --message "Do the analysis"
```

Example with workflow parameters:

```bash id="monscs"
flowpath run child_workflow task-1 \
  --message "Do the analysis" \
  -wf mode strict \
  -wf reviewer security
```

---

## 4.4 `resume <workflow> <task-id> [--run-id <run-id>]`

Purpose:

* resume a previously interrupted or paused run

Behavior:

* if `--run-id` is provided, resume that run
* if `--run-id` is omitted, resume the latest resumable run for the given workflow/task
* if no resumable run exists, fail clearly

Rules:

* must not create a new run
* must preserve the original run id
* must not require `--message`
* may optionally accept generic runtime/provider options only if they are explicitly allowed to affect resumption behavior

Example:

```bash id="x93c3j"
flowpath resume child_workflow task-1
```

Example with explicit run id:

```bash id="g46b8w"
flowpath resume child_workflow task-1 --run-id run-20260422-001
```

---

## 4.5 `answer <workflow> <task-id> --answer "..." [--run-id <run-id>]`

Purpose:

* resume a paused run by supplying an answer to its pending question

Required arguments:

* `<workflow>`
* `<task-id>`
* `--answer`

Behavior:

* if `--run-id` is provided, answer that run
* if omitted, answer the latest paused run for the workflow/task
* inject the answer into the paused run
* continue execution from the paused checkpoint

Rules:

* `--answer` is required
* `--message` must not be accepted here for answer injection
* if the target run is not paused, fail clearly
* must not create a new run

Example:

```bash id="icl66d"
flowpath answer child_workflow task-1 --answer "Use OAuth"
```

Example with explicit run id:

```bash id="xgcay1"
flowpath answer child_workflow task-1 \
  --run-id run-20260422-001 \
  --answer "Use OAuth"
```

---

## 4.6 `runs list`

Purpose:

* list historical or active runs

Optional filters:

* `--workflow <workflow>`
* `--task <task-id>`
* `--status <status>`

Behavior:

* returns runs matching the filters
* shows at minimum:

  * workflow
  * task id
  * run id
  * status
  * created/updated timestamps
  * whether resumable or paused

Rules:

* if no filters are provided, show all runs visible in the current root/workspace
* statuses should be normalized and clearly documented

Example:

```bash id="hu3faa"
flowpath runs list --status paused
```

Example:

```bash id="bi6qkz"
flowpath runs list --workflow child_workflow --task task-1
```

---

## 4.7 `runs show <workflow> <task-id> [--run-id <run-id>]`

Purpose:

* show detailed metadata for a specific run

Behavior:

* resolves a specific run
* if `--run-id` is omitted, show the latest run for that workflow/task
* displays at minimum:

  * workflow
  * task id
  * run id
  * current status
  * created/updated timestamps
  * whether checkpoint exists
  * whether pending question exists
  * resolved workflow parameters
  * run paths or references to key artifacts

Rules:

* this is a diagnostic command
* must not mutate state

Example:

```bash id="d0s0xm"
flowpath runs show child_workflow task-1
```

---

## 4.8 `logs <workflow> <task-id> [--run-id <run-id>] [--events|--trace|--raw]`

Purpose:

* inspect log outputs for a run

Behavior:

* resolves target run
* defaults to a sensible primary log view if no log type flag is provided
* explicit flags select log stream:

  * `--events` for event log
  * `--trace` for trace log
  * `--raw` for workflow-owned raw sidecar logs, if present

Rules:

* if selected log does not exist, fail clearly
* if `--run-id` is omitted, use latest run for the workflow/task
* command is read-only

Example:

```bash id="46hxrq"
flowpath logs child_workflow task-1 --events
```

Example:

```bash id="wfssiy"
flowpath logs child_workflow task-1 --run-id run-20260422-001 --raw
```

---

## 4.9 `init workflow <name>`

Purpose:

* scaffold a new workflow package

Behavior:

* creates a new package under the configured workflows root
* generates at minimum:

  * package directory
  * `__init__.py`
  * `workflow.toml`
  * `workflow.py`
  * `prompts/`
  * `assets/`

Rules:

* must fail if the target name already exists unless an explicit overwrite flag is introduced later
* generated workflow must conform to the framework’s workflow package contract

Example:

```bash id="f3m1wn"
flowpath init workflow child_workflow
```

---

## 5. Workflow-specific parameters (`-wf`)

Workflow-specific parameters are passed using repeatable pairs:

```bash id="hiafcp"
-wf <parameter_name> <value>
```

Example:

```bash id="c8izm7"
flowpath run review task-42 \
  --message "Review this implementation" \
  -wf strict true \
  -wf branch main
```

Rules:

* `-wf` is repeatable
* order is preserved when parsing
* repeated keys are allowed only if the workflow parameter model explicitly supports them
* values arrive as strings at the CLI boundary
* the framework must validate/coerce them through the workflow package’s parameter model
* invalid parameters must fail before execution starts
* unknown parameters must fail before execution starts

Separation rule:

* `-wf` is only for workflow-specific parameters
* generic runtime/provider flags must never be tunneled through `-wf`

---

## 6. Workflow resolution rules

Workflow resolution applies to all commands that take `<workflow>`.

Resolution behavior:

1. match canonical workflow name first
2. if no canonical match, match alias
3. if exactly one alias match exists, use it
4. if multiple matches exist, fail clearly and show candidates
5. if no match exists, fail clearly

Rules:

* workflow names are case-sensitive or case-normalized according to the implementation choice, but the choice must be consistent and documented
* aliases must never silently shadow canonical names

---

## 7. Run resolution rules

Commands that operate on existing runs (`resume`, `answer`, `runs show`, `logs`) must follow these rules.

If `--run-id` is provided:

* use that exact run
* fail if not found

If `--run-id` is omitted:

* `resume` resolves latest resumable run
* `answer` resolves latest paused run
* `runs show` resolves latest run
* `logs` resolves latest run

If resolution finds no valid run:

* fail clearly
* do not create a new run
* do not guess across workflows

If multiple runs are candidates and “latest” cannot be determined deterministically:

* fail clearly
* require `--run-id`

---

## 8. Message and answer semantics

### `--message`

Used for:

* starting a new run

Semantic meaning:

* initial input/request for this run

Rules:

* required on `run`
* not accepted on `resume`
* not accepted for answer injection on `answer`

### `--answer`

Used for:

* resuming a paused run with an explicit answer

Rules:

* required on `answer`
* not interchangeable with `--message`

---

## 9. Generic runtime/provider flags

The CLI may expose generic framework-level flags, but they must remain clearly separate from workflow-specific flags.

Examples of acceptable generic flags:

* root/workspace selection
* provider selection
* model selection
* tracing enablement
* output verbosity

Rules:

* generic flags apply consistently across workflows
* generic flags must not be encoded through `-wf`
* workflow-specific meanings must stay in workflow parameters, not generic runtime config

---

## 10. Output contract

Each mutating command (`run`, `resume`, `answer`) should print a concise machine- and human-usable result summary.

Minimum recommended fields:

* workflow
* task id
* run id
* terminal or current status
* whether paused
* pending question if paused
* path/reference to main run artifacts if useful

Each read-only command should present deterministic structured output suitable for terminal use.

Optional implementation choice:

* support a `--json` output mode for all commands

If implemented, `--json` must be consistent across commands.

---

## 11. Exit code contract

Required exit-code semantics:

* `0` — success
* non-zero — failure

Recommended distinctions:

* `2` — usage/validation error
* distinct non-zero code for runtime execution failure
* distinct non-zero code for resolution/not-found failure if desired

Rules:

* invalid workflow name must fail non-zero
* invalid `-wf` input must fail non-zero before execution
* no resumable run found must fail non-zero
* no paused run found for `answer` must fail non-zero

---

## 12. Error behavior

All commands must fail clearly and specifically.

Required error cases:

* unknown workflow
* ambiguous workflow alias
* invalid workflow-specific parameter
* missing required `--message`
* missing required `--answer`
* no resumable run found
* no paused run found
* unknown run id
* requested log stream missing

Rules:

* do not fall back silently
* do not auto-create a new run when resume/answer/show/logs fails to find one
* do not blur message and answer semantics

---

## 13. Non-goals

The public CLI must **not** support:

* raw Python file execution
* raw module path execution
* explicit class-name selection
* public `exec` mode
* hidden compatibility flags for old CLI syntax

This is intentional.

---

## 14. Required implementation invariants

Any implementation of this CLI contract must preserve these invariants:

1. workflows are addressed by package name in the public CLI
2. the main entry path is package-based, not raw-path-based
3. message is first-class for new runs
4. answer is first-class for paused resumes
5. workflow-specific parameters are explicit and validated
6. run ids remain real runtime concepts even if many users never type them
7. the CLI remains compatible with workflows being used both:

   * as end-to-end entrypoints
   * as reusable building blocks inside other workflows

---

## 15. Acceptance criteria

The CLI contract is successfully implemented when all of the following are true:

* public commands exactly cover the command surface in this document
* no public raw execution surface exists
* workflows are discovered and addressed by workflow package name
* `run` requires `--message`
* `answer` requires `--answer`
* `-wf` is repeatable and validated through workflow parameter models
* run selection behaves deterministically with or without `--run-id`
* errors are explicit and non-silent
* the CLI remains suitable both for top-level workflow execution and for a framework where workflows compose other workflows

```
```

See Workflow_Instructions.md for further workflow authoring and provider boundaries instructions.
