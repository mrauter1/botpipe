# Simple API

This is the public workflow authoring API. A workflow is a Python class that
declares typed inputs, typed params, durable state, steps, artifacts, routes,
sessions, and optional worklists. Public workflow code should import from
`botpipe`.

```python
from botpipe import (
    AWAIT_INPUT,
    FAIL,
    FINISH,
    SELF,
    Event,
    Fail,
    Goto,
    Json,
    Md,
    Prompt,
    RequestInput,
    Route,
    Text,
    Workflow,
    python_step,
    step,
)
```

`botpipe.core` is the lower-level runtime surface. Use it only when you are
working on framework internals or an intentional power-user extension.

## Smallest Workflow

```python
from pydantic import BaseModel

from botpipe import FINISH, Event, Md, Text, Prompt, Route, Workflow, python_step, step


class ReviewWorkflow(Workflow):
    class Input(BaseModel):
        topic: str

    class Params(BaseModel):
        mode: str = "normal"

    class State(BaseModel):
        published: bool = False

    draft = step(
        Prompt.inline("Review {{ input.topic }}. Request: {{ message }}"),
        writes=[Md("report", required=True)],
        routes={
            "done": Route.to("publish", required_writes=["report"]),
        },
    )

    @python_step(
        writes=[Text("receipt", required=True)],
        requires=[draft.report],
        routes={"done": FINISH},
    )
    def publish(ctx):
        ctx.artifacts.receipt.write_text(f"mode={ctx.params.mode}")
        ctx.state = ctx.state.model_copy(update={"published": True})
        return Event("done")
```

Run it with the SDK:

```python
from botpipe import Botpipe

client = Botpipe(workspace=".", provider="codex")
result = client.run(
    ReviewWorkflow,
    "Review the rollout plan.",
    input=ReviewWorkflow.Input(topic="rollout"),
    params={"mode": "strict"},
)
```

## Mental Model

- `Workflow` is the unit of authoring and execution.
- `Input` is structured run input. It must inherit from `pydantic.BaseModel`.
- `message` is separate from `Input` and is available as `ctx.message`.
- `Params` is workflow configuration. It is available as `ctx.params` and
  `ctx.workflow_params`.
- `State` is durable workflow state. Mutate it through `ctx.state`.
- Steps run in class-body order unless you set `entry` or route explicitly.
- Routes are named outcomes. A route target is another step, `SELF`, `FINISH`,
  `AWAIT_INPUT`, or `FAIL`.
- Artifacts are durable files. Steps declare what they read, require, and write.
- Provider-backed steps ask a model to choose a legal route and write declared
  outputs. Python steps run local Python and return the route/control decision.
- The compiler rejects static errors early. Runtime validation handles data that
  only exists during the run, such as generated artifacts and worklist contents.

## Workflow Shape

Botpipe discovers workflows from three roots:

- repo-local workflows under `{workspace}/workflows/`
- workspace-local workflows under `{workspace}/.botpipe/workflows/`
- package-installed workflows under `botpipe/workflows/`

Resolution precedence is `.botpipe/workflows/`, then `workflows/`, then
package-installed workflows.

Repo-local workflows live under:

```text
workflows/
  review.py
```

or:

```text
workflows/
  review/
    flow.py
    specs.py
    prompts/
    assets/
```

Workspace-local workflows use the same shapes under `.botpipe/workflows/`:

```text
.botpipe/workflows/
  review.py
```

or:

```text
.botpipe/workflows/
  review/
    flow.py
    specs.py
    prompts/
    assets/
```

Package-installed workflows live under `botpipe/workflows/<name>/` and should
re-export their main workflow class from `__init__.py`.

`workflow.toml`, when present, is metadata only: name, title, description, and
aliases. It does not define topology, prompts, params, routes, artifacts, or
execution behavior.

## Inputs, Params, State, Output

```python
from pydantic import BaseModel

from botpipe import Workflow


class MyWorkflow(Workflow):
    class Input(BaseModel):
        customer: str
        severity: str = "normal"

    class Params(BaseModel):
        reviewer: str = "default"

    class State(BaseModel):
        decision: str | None = None

    class Output(BaseModel):
        decision: str

    @staticmethod
    def build_output(state: State, ctx):
        return MyWorkflow.Output(decision=state.decision or "unknown")
```

Rules:

- `Input`, `Params`, `State`, and `Output` must be Pydantic models when present.
- `Input` must not declare a field named `message`.
- `ctx.input` is the raw `Workflow.Input` model instance, or `None`.
- `ctx.input_fields` is the raw `Workflow.Input` model instance, or `None`.
- `ctx.params` is the typed `Params` model.
- `ctx.workflow_params` is the raw parameter mapping.
- `build_output(state, ctx)` is required when `Output` is declared.

## Prompts

Use `Prompt.inline(...)` for short prompts and `Prompt.file(...)` for prompt
files. File prompts are Jinja templates by default.

```python
from botpipe import Prompt, step

draft = step(Prompt.inline("Draft a summary for {{ message }}."))
review = step(Prompt.file("prompts/review.md"))
```

Relative prompt files resolve from the workflow file or package directory, not
from the current shell directory.

File prompts receive a small Jinja context with short root names:

```jinja
# prompts/review.md

Review request:
{{ message }}

{% if input.customer is defined %}
Customer: {{ input.customer }}
{% endif %}

Reviewer: {{ params.reviewer }}
Decision: {{ state.decision }}
```

Provider prompts should describe the task. The runtime injects the available
routes, required writes, readable inputs, writable artifacts, and output contract.

## Artifacts

Use simple artifact helpers in step `writes`:

```python
from pydantic import BaseModel

from botpipe import Json, Md, Text, Raw


class Summary(BaseModel):
    title: str
    ready: bool


Json("summary", Summary, required=True)
Md("report")
Text("notes", path="{{ workflow.folder }}/notes.txt")
Raw("archive", path="{{ workflow.folder }}/archive.bin")
```

Step-local artifacts default to:

```text
{{ workflow.folder }}/{step_name}/{artifact_name}.{extension}
```

Important contracts:

- `reads` are optional context. Missing reads do not block step start.
- `requires` are hard preconditions. Missing required artifacts fail before the
  step runs.
- `writes` are governed output handles exposed as `ctx.artifacts.<name>`.
- `required=True` makes a write required on successful completion unless the
  selected route overrides required writes.
- `Json(..., schema=Model)` validates the JSON artifact on disk.
- Artifact schema is separate from `control_schema`, which validates provider
  `Outcome.payload`.

Downstream steps can refer to step-local writes through the declaration:

```python
draft = step("Draft.", writes=[Md("report", required=True)])
publish = step("Publish.", requires=[draft.report])
```

## Routes

Routes define legal outcomes and their targets.

```python
from botpipe import AWAIT_INPUT, FAIL, FINISH, SELF, Route

routes = {
    "done": FINISH,
    "retry": SELF,
    "question": AWAIT_INPUT,
    "failed": FAIL,
    "approved": Route.to(
        FINISH,
        summary="The review is complete.",
        required_writes=["report"],
    ),
}
```

Useful helpers:

- `Route.to(target, ...)`
- `Route.finish(...)`
- `Route.await_input(...)`
- `Route.fail(...)`
- `Route.question(...)`
- `Route.blocked(...)`
- `Route.failed(...)`
- `Route.hidden(target, ...)`
- `Route.disabled()`
- `Route.advance(...)`, `Route.complete_current(...)`, and
  `Route.complete_and_advance(...)` for worklist routes

If a simple step declares no routes, the framework supplies a small default:

- `step(...)`, `python_step(...)`, `workflow_step(...)`, `llm.step(...)`, and
  `classify.step(...)`: `done` goes to the next step, or `FINISH`.
- `produce_verify_step(...)`: `accepted` goes to the next step, or `FINISH`;
  `needs_rework` loops to the same step.
- Branch groups without a fan-in expose mechanical composite routes such as
  `done`, `partial`, `question`, and `failed`.

Once you declare `routes={...}` on a step, include every route that step may
return or provider output may select. Static validation rejects illegal route
targets and unknown route usage.

Provider outcomes use the canonical route envelope:

```json
{
  "outcome": {
    "tag": "done",
    "payload": {},
    "route_fields": {}
  }
}
```

`outcome.tag` selects the route. `outcome.payload` is business output validated
by `control_schema` or route payload schema. `outcome.route_fields` carries
route-specific fields such as clarification questions or failure reasons.

## Control Routes

`control_routes` controls framework helper routes such as provider questions.

```python
from botpipe import ControlRoutes, step

interactive = step("Ask when needed.", control_routes=ControlRoutes(question="auto"))
always_visible = step("May ask in full-auto too.", control_routes=ControlRoutes(question="always"))
no_questions = step("Never expose question.", control_routes=False)
```

`question` modes:

- `"auto"`: provider question routes are interactive-only.
- `"always"`: provider question routes remain visible in full-auto mode.
- `"never"`: suppress the helper question route.

Simple provider-backed `step(...)` and `produce_verify_step(...)` default to
`question="auto"`. `python_step(...)` and `workflow_step(...)` default to
`question="never"`.

## Step Types

### `step(...)`

Use for one provider-backed prompt turn.

```python
from botpipe import FINISH, Md, Prompt, Route, step

review = step(
    Prompt.file("prompts/review.md"),
    writes=[Md("review_report", required=True)],
    routes={
        "done": Route.finish(required_writes=["review_report"]),
    },
)
```

Common arguments:

- `prompt`
- `reads`, `requires`, `writes`
- `scope` and `item_state` for worklists
- `routes`
- `before`, `after`
- `control_schema`
- `retry`
- `session`
- `control_routes`
- `policy`

### `produce_verify_step(...)`

Use for a producer prompt followed by a verifier prompt.

```python
from botpipe import FINISH, Md, SELF, Route, produce_verify_step

review = produce_verify_step(
    producer_prompt="Draft the package.",
    verifier_prompt="Verify the package.",
    producer_writes=[Md("draft", required=True)],
    verifier_writes=[Md("review", required=True)],
    routes={
        "accepted": Route.to(FINISH, required_writes=["draft", "review"]),
        "needs_rework": Route.to(SELF),
    },
)
```

Producer writes and verifier writes are separate. Verifier reads automatically
include producer writes.

### `python_step(...)`

Use for deterministic local code.

```python
from botpipe import FINISH, Event, python_step


@python_step(routes={"done": FINISH})
def finalize(ctx):
    ctx.state = ctx.state.model_copy(update={"decision": "ship"})
    return Event("done")
```

Python handlers can return:

```python
None
"route_tag"
Event(...)
RequestInput(...)
Goto(...)
Fail(...)
Effects(...)
```

Python steps mutate `ctx` directly. Do not use `control_schema` on Python steps.

### `validation_step(...)`

Use for repairable deterministic validation.

```python
from botpipe import FINISH, Md, ValidationResult, validation_step

feedback = Md("feedback")


@validation_step(feedback=feedback, success=FINISH, repair="repair")
def validate(ctx):
    if ctx.artifacts.report.path.exists():
        return ValidationResult.valid()
    return ValidationResult.invalid("Report is missing.")
```

The helper lowers to a normal Python step, writes feedback when invalid, and
routes through the explicit repair route.

### `workflow_step(...)`

Use to invoke a child workflow as a step.

```python
from botpipe import FINISH, workflow_step

launch = workflow_step(
    ChildWorkflow,
    message="{{ message }}",
    input={"topic": "release"},
    routes={"done": FINISH},
)
```

For dynamic child calls inside Python hooks or handlers, use:

```python
result = ctx.invoke_workflow(
    ChildWorkflow,
    message="Run child",
    parameters={"mode": "strict"},
    input=ChildWorkflow.Input(topic="release"),
)
```

### `llm` and `classify`

Use inline operations inside Python steps:

```python
from botpipe import classify, llm

summary = llm("Summarize the findings.", returns=str)
label = classify("Pick a label.", choices=["ship", "hold"])
```

Or create operation steps:

```python
summarize = llm.step(prompt="Summarize.", returns=str)
decide = classify.step(prompt="Choose.", choices=["ship", "hold"])
```

## Hooks

Hooks use one argument: `ctx`.

```python
def before(ctx):
    ...


def after(ctx):
    ...


def on_taken(ctx):
    ...
```

Hook returns use the same control values as Python steps:

```python
None
"route_tag"
Event(...)
RequestInput(...)
Goto(...)
Fail(...)
Effects(...)
```

Use route-local hooks for route-owned behavior:

```python
from botpipe import RequestInput, Route

routes = {
    "needs_approval": Route.hidden("publish", on_taken=lambda ctx: RequestInput("Approve?")),
}
```

## Context Surface

The most useful `ctx` fields are:

- `ctx.root`
- `ctx.task_id`, `ctx.run_id`, `ctx.workflow_name`
- `ctx.task_folder`, `ctx.workflow_folder`, `ctx.run_folder`, `ctx.package_folder`
- `ctx.request.text`, `ctx.request.file`, `ctx.request.task_file`
- `ctx.message`
- `ctx.input`, `ctx.input_fields`
- `ctx.params`, `ctx.workflow_params`
- `ctx.state`
- `ctx.step_state`, `ctx.item_state`, `ctx.step_item_state`
- `ctx.artifacts`
- `ctx.values`
- `ctx.outcome`, `ctx.event`, `ctx.route`, `ctx.meta`
- `ctx.input_response`
- `ctx.history`
- `ctx.session`, `ctx.open_session(...)`, `ctx.get_session(...)`
- `ctx.worklist(...)`, `ctx.current_worklist`, `ctx.selection(...)`, `ctx.item`
- `ctx.read(...)`, `ctx.write(...)`, `ctx.read_json(...)`, `ctx.write_json(...)`
- `ctx.invoke_workflow(...)`

Artifact handles support `read_text`, `write_text`, `read_json`, `write_json`,
and schema-aware model helpers.

Step-local state can be declared as a Pydantic model or with `StateVar(...)`.
`state=` is currently available on `produce_verify_step(...)`; `item_state=` is
available on scoped provider-backed simple steps.

```python
from botpipe import StateVar, Worklist, produce_verify_step

items = Worklist.from_param("items", item_id="id", title="title")

review = produce_verify_step(
    producer_prompt="Draft.",
    verifier_prompt="Verify.",
    scope=items,
    state={"risk": StateVar("unknown")},
    item_state={"attempts": StateVar(0)},
)
```

## Sessions

Provider-backed steps use an implicit default session if no `session=` is set.
Declare explicit session slots when a workflow needs separate conversations.

```python
from botpipe import Continuity, Session, step

worker = Session(continuity=Continuity.work_item("gate"))
review = step("Review selected gate.", session=worker)
```

Continuity policies:

- `Continuity.run()`
- `Continuity.task()`
- `Continuity.work_item("name")`
- `Continuity.fresh()`
- `Continuity.key("stable-key")`

`ctx.open_session(session, scope="cluster-1")` is an explicit runtime override.
Treat provider continuation IDs as opaque runtime state.

## Worklists

Worklists scope repeated work to an explicit current item. They do not create
hidden loops.

```python
from botpipe import Route, SELF, Worklist, step

gates = Worklist.from_param("gates", item_id="id", title="title", status="status")

review = step(
    "Review the selected gate.",
    scope=gates,
    routes={
        "accepted": Route.complete_and_advance(SELF, exhausted="finalize"),
    },
)
```

Useful runtime helpers:

- `ctx.worklist("gates")`
- `ctx.current_worklist`
- `ctx.selection("gates")`
- `ctx.current_worklist.set_current_status("done")`
- `ctx.current_worklist.advance()`
- `ctx.current_worklist.advance_or(Goto("finalize"))`
- `ctx.current_worklist.validate()`

Declared worklists are lazy. The compiler validates the static contract, but the
runtime does not require the backing source to exist until a step or hook touches
that worklist.

## Branch Groups

Use `parallel(...)` for different branch step declarations and `fan_out(...)`
for one shared step over several branch inputs.

```python
from botpipe import FINISH, parallel, step

reviews = parallel(
    branches={
        "security": step("Review security."),
        "cost": step("Review cost."),
    },
    routes={"done": FINISH, "partial": FINISH},
)
```

Branch groups can use `fan_in=` to run a final aggregation step after branches.
Use branch groups for bounded parallel structure, not hidden unbounded loops.

## Signature Reference

Types are omitted here when they would obscure the shape. These are the public
authoring call forms.

```text
Json(name, schema=None, *, path=None, required=False)
Md(name, *, path=None, required=False)
Text(name, *, path=None, required=False)
Raw(name, *, path=None, required=False)
```

```text
step(
    prompt,
    *,
    name=None,
    reads=(),
    requires=(),
    writes=(),
    scope=None,
    item_state=None,
    routes=None,
    before=None,
    after=None,
    control_schema=None,
    retry=None,
    session=None,
    control_routes=True,
    policy=None,
)
```

```text
produce_verify_step(
    *,
    producer_prompt,
    verifier_prompt,
    name=None,
    reads=(),
    requires=(),
    verifier_reads=(),
    verifier_requires=(),
    producer_writes=(),
    verifier_writes=(),
    scope=None,
    routes=None,
    state=None,
    item_state=None,
    before_producer=None,
    after_producer=None,
    before_verifier=None,
    after_verifier=None,
    control_schema=None,
    retry=None,
    session=None,
    verifier_session=None,
    control_routes=True,
    policy=None,
)
```

```text
python_step(
    fn=None,
    *,
    name=None,
    reads=(),
    requires=(),
    writes=(),
    routes=None,
    before=None,
    after=None,
    control_routes=True,
    policy=None,
)
```

```text
validation_step(
    fn=None,
    *,
    name=None,
    feedback,
    success="done",
    repair="repair",
    failed=None,
    reads=(),
    requires=(),
    writes=(),
    routes=None,
    before=None,
    after=None,
    control_routes=True,
)
```

```text
workflow_step(
    workflow,
    *,
    name=None,
    message=None,
    message_from=None,
    params=None,
    input=None,
    reads=(),
    requires=(),
    writes=(),
    routes=None,
    before=None,
    after=None,
    control_routes=True,
    policy=None,
)
```

```text
parallel(
    *,
    branches,
    name=None,
    concurrency=None,
    settle="all",
    fan_in=None,
    outcome="all_done",
    success_routes=("done", "accepted"),
    routes=None,
)

fan_out(
    *,
    step,
    branches,
    name=None,
    concurrency=None,
    settle="all",
    fan_in=None,
    outcome="all_done",
    success_routes=("done", "accepted"),
    routes=None,
)
```

```text
llm(prompt, *, returns=str, retry=3, policy=None)
llm.step(*, prompt, returns=str, name=None, reads=(), requires=(), retry=3)

classify(prompt, *, choices, retry=3, policy=None)
classify.step(*, prompt, choices, name=None, reads=(), requires=(), retry=3)
```

## Policy

Use `Policy(...)` as an inheriting layer at workflow, step, SDK run, or operation
scope.

```python
from botpipe import ModelEffort, PermissionMode, Policy, Workflow, step


class MyWorkflow(Workflow):
    policy = Policy(permission_mode=PermissionMode.ASK)

    draft = step(
        "Draft.",
        policy=Policy(effort=ModelEffort.HIGH, read_only=True),
    )
```

Unset fields inherit from the runtime defaults and outer layers. A policy layer
is not a hard security cap by itself; strict enforcement belongs to runtime
provider policy configuration.

## Public Export Checklist

Root authoring exports include:

```text
Workflow, step, produce_verify_step, python_step, validation_step,
workflow_step, Step, PromptStep, ProduceVerifyStep, PythonStep,
ChildWorkflowStep, parallel, fan_out, llm, classify,
ControlRoutes, Prompt, Route, Session, Continuity, Worklist, FanIn,
WorklistEffect, StateVar,
Json, Md, Text, Raw,
Event, Outcome, RequestInput, Goto, Fail, Effects, ValidationResult,
FINISH, AWAIT_INPUT, FAIL, SELF,
Policy, ProviderName, ModelEffort, ModelVerbosity, ReasoningSummary,
SandboxMode, NetworkMode, PermissionMode
```

Prefer these names in all public workflow examples.

## Authoring Rules

- Import public workflow symbols from `botpipe`.
- Keep `workflow.toml` metadata-only.
- Prefer `flow.py` for package workflows, but `workflow.py` is supported.
- Keep topology in step-local `routes={...}`.
- Do not use `transitions` or `flow` in simple workflows.
- Keep provider instructions in prompt files or inline prompts.
- Let the runtime inject route, artifact, and output contracts.
- Use `requires` for hard dependencies and `reads` for optional context.
- Use `RequestInput(...)` for runtime-owned pauses.
- Use `Goto(...)` for direct jumps and `Fail(...)` for terminal failure.
- Use `Route.hidden(...)` for runtime-valid routes the provider must not see.
- Treat raw provider output as runtime telemetry, not prompt input.
- Keep deterministic validation in Python steps or `validation_step(...)`.
