# Authoring

Use the strict root `workflow` shim when authoring workflows:

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

Keep the root surface strict: do not import engine internals, compiler helpers, or compatibility modules from `workflow`.

## Package Contract

Workflow packages live under repo-root `workflows/` and are ordinary Python packages.

Each package must include:

- `__init__.py`
- `workflow.py`
- `workflow.toml`
- `prompts/`
- `assets/`

Package `__init__.py` must re-export the main workflow class:

```python
from .workflow import ChildWorkflow

__all__ = ["ChildWorkflow"]
```

If the workflow defines workflow-specific parameters, the package may also re-export `Parameters`:

```python
from .workflow import ChildWorkflow
from .params import Parameters

__all__ = ["ChildWorkflow", "Parameters"]
```

## Workflow Parameters

Top-level CLI runs pass workflow-specific parameters through repeatable `-wf` pairs:

```bash
autoloop run review task-42 \
  --message "Review this implementation" \
  -wf mode strict \
  -wf reviewer security
```

If a workflow supports parameters, export a `Parameters` model from the package. The runtime validates and coerces `-wf` values through that model before execution starts.

## Prompt And Artifact Resolution

Relative prompts and bundled assets resolve from the workflow package root, never from the current working directory.

```python
Prompt("prompts/ask.md")
Artifact("{run_folder}/request.md")
Artifact("{workflow_folder}/notes.md")
Artifact("{package_folder}/assets/template.txt")
```

Available runtime placeholders include:

- `task_folder`
- `workflow_folder`
- `run_folder`
- `package_folder`
- `workflow_name`
- `state.*`

`package_folder` is read-only package content. Mutable artifacts must never be written into the workflow package directory.

## Message Model

New runs are message-first:

- `autoloop run ... --message "..."` starts a new run
- `autoloop answer ... --answer "..."` resumes a paused run with an explicit answer

`message` and `answer` are distinct concepts. Resume and diagnostics do not accept a replacement message.

## Workflow Composition

Runtime-backed contexts can invoke child workflows by package name or imported main class:

```python
from workflows.child_workflow import ChildWorkflow

result = ctx.invoke_workflow(
    ChildWorkflow,
    message="Do the child task",
    parameters={"mode": "strict"},
)
```

```python
result = ctx.invoke_workflow(
    "child_workflow",
    message="Do the child task",
    parameters={"mode": "strict"},
)
```

Child workflows run as normal workflow packages with their own run ids and run-local artifacts. They are reusable building blocks, not a special execution mode.
