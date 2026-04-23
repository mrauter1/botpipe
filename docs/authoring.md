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

## Runtime Config And Provider Selection

Workflow code does not construct providers directly. Operators select the built-in runtime backend through typed config and generic CLI flags.

Typed config lives in `autoloop.yaml` or `autoloop.config` and uses the runtime-owned provider schema:

```yaml
provider:
  name: codex
  model: gpt-5.4
  model_effort: medium
runtime:
  max_steps: 100
```

`provider.name` selects the built-in backend. Generic `provider.model` and `provider.model_effort` overrides target that selected provider.

Public CLI overrides stay generic:

```bash
autoloop run review task-42 \
  --provider claude \
  --model claude-opus \
  --model-effort max \
  --message "Review this implementation"
```

If a workflow or template documents operational usage, keep it on this typed surface. Do not document ad-hoc backend construction or out-of-band provider injection.

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

## Sessions And Resumability

The runtime persists resumability through an opaque `session_id` plus optional `provider_metadata`. Workflow code should treat session continuity as opaque runtime state and use the `Session` / context APIs rather than depending on persisted payload details.

Implications for authors:

- do not assume provider-specific naming for the continuation handle
- do not read or write session JSON directly from workflow logic
- keep provider-specific behavior inside provider adapters or provider-specific prompts, not workflow contracts

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

## Recursive And Package-Only Guidance

If a workflow, template, or recursive harness emits Autoloop instructions, keep them package-CLI-only and repo-layout-accurate:

- `autoloop run <workflow> <task-id> --root ... --message ...`
- `autoloop resume <workflow> <task-id> --root ...`
- `autoloop answer <workflow> <task-id> --root ... --answer ...`
- refer readers to `docs/architecture.md`, `docs/authoring.md`, `core/`, `runtime/`, `extensions/`, `stdlib/`, `workflows/`, and `.autoloop_recursive/`
