# Authoring

Use the strict root `workflow` shim when authoring workflows:

```python
from workflow import (
    Workflow,
    Context,
    Session,
    Artifact,
    Prompt,
    RouteContract,
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

## Step Control Contracts

Provider-owned steps may declare narrow machine-readable control contracts directly on `PairStep` and `LLMStep`.

```python
from pydantic import BaseModel


class ReviewPayload(BaseModel):
    summary: str


review = PairStep(
    name="review",
    producer="prompts/review_producer.md",
    verifier="prompts/review_verifier.md",
    expected_output_schema=ReviewPayload,
    route_contracts={
        "review_complete": RouteContract(
            summary="Review artifacts and verdict are complete.",
            required_artifacts=["review_report"],
            work_item_effect="Advances the review package to the next declared step.",
        )
    },
)
```

Runtime behavior:

- `expected_output_schema` defines the JSON-schema-like contract for `Outcome.payload`
- `available_routes` is derived mechanically from the declared workflow transitions plus reserved routes
- `route_contracts` is optional step-owned metadata for legal application routes only
- route contracts normalize to `summary`, `required_artifacts`, and `work_item_effect`
- mapping-style declarations remain valid; legacy `state_effect` values normalize to `work_item_effect`

Authoring rules:

- keep provider-facing operational guidance in the prompt templates, not in runtime-only metadata
- reserve runtime-injected control data for `expected_output_schema`, `available_routes`, and `route_contracts`
- continue using `Outcome.tag` as the route carrier
- use `needs_rework` when the current work-item boundary still holds and `needs_replan` when the boundary changed materially
- do not declare `expected_output_schema` or `route_contracts` on `SystemStep`

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

Concrete runtime adapters live under `runtime/providers/`, but that package is framework-owned implementation detail. Workflow authors should target the typed runtime config surface and the generic CLI flags rather than importing provider adapters or describing non-public factory hooks.

For `PairStep` verifiers and `LLMStep` prompts, treat the provider-facing completion contract as strict JSON. The runtime now validates verifier and single-LLM outcomes locally, so prompts should ask for one JSON object matching the declared routes and payload contract rather than free-form prose.

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
- do not document or depend on any legacy provider-specific continuation alias outside the canonical `session_id` contract

## Optional Lifecycle Helpers

`stdlib/lifecycle.py` provides a small opt-in helper seam for deterministic authoring tasks such as opening declared sessions and writing workflow-local JSON artifacts like invocation contracts and publication receipts.

```python
from autoloop_v3.stdlib import (
    open_workflow_sessions,
    write_invocation_contract,
    write_publication_receipt,
)
```

Use it only as authoring support inside explicit workflow hooks such as `on_bootstrap(...)` or `on_publish_* (...)`.

- these helpers do not create hidden runtime sequencing or automatic system steps
- they only operate on the workflow-owned `ctx` surface and `ctx.workflow_folder`
- they do not widen the runtime-injected control contract beyond `expected_output_schema`, `available_routes`, and `route_contracts`
- publication-artifact validation and any workflow-specific receipt semantics still belong in workflow code

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

For optional authoring-level composition helpers, `stdlib/composition.py` keeps the same runtime semantics while making artifact adoption explicit in workflow code:

```python
from autoloop_v3.stdlib import adopt_child_artifacts, run_child_workflow

child = run_child_workflow(
    ctx,
    "child_workflow",
    message="Do the child task",
    parameters={"mode": "strict"},
)
adopted = adopt_child_artifacts(
    ctx,
    child,
    mapping={"evidence_pack": "adopted/evidence_pack.md"},
)
```

Composition helper boundary:

- `run_child_workflow(...)` is a thin authoring wrapper over `ctx.invoke_workflow(...)`
- `adopt_child_artifacts(...)` copies explicitly named child artifacts into `ctx.workflow_folder`
- these helpers do not create hidden runtime sequencing, automatic system steps, or new child-run metadata
- they do not widen the runtime-injected control contract beyond `expected_output_schema`, `available_routes`, and `route_contracts`
- parent workflows still own which child artifacts are adopted, where they land, and whether overwriting those parent-local files is acceptable

## Recursive And Package-Only Guidance

If a workflow, template, or recursive harness emits Autoloop instructions, keep them package-CLI-only and repo-layout-accurate:

- `autoloop run <workflow> <task-id> --root ... --message ...`
- `autoloop resume <workflow> <task-id> --root ...`
- `autoloop answer <workflow> <task-id> --root ... --answer ...`
- refer readers to `docs/architecture.md`, `docs/authoring.md`, `core/`, `runtime/`, `extensions/`, `stdlib/`, `workflows/`, and `.autoloop_recursive/`
