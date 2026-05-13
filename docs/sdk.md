# SDK

The SDK is the public Python execution facade. Use it when application code,
tests, notebooks, or agents need to run Botpipe workflows or individual steps
without driving the CLI.

```python
from botpipe import Botpipe
```

One SDK call is one independent invocation. The SDK uses the runtime task, run,
checkpoint, artifact, and provider machinery internally, but it does not expose
manual task/run management, durable resume, event browsing, or trace browsing as
public SDK workflows.

## Smallest Use

```python
from botpipe import Botpipe

client = Botpipe(workspace=".", provider="codex")
result = client.run(ReviewWorkflow, "Review this change.")

if result.ok:
    print(result.state)
```

With typed input and params:

```python
result = client.run(
    ReviewWorkflow,
    message="Review this release.",
    input=ReviewWorkflow.Input(topic="checkout"),
    params={"mode": "strict"},
)
```

`message`, `input`, and `params` are separate:

- `message` is the natural-language request, visible as `ctx.message`.
- `input` is structured workflow input, visible as fields on `ctx.input` and
  temporarily also as the raw model on `ctx.input_fields`.
- `params` is configuration, visible as `ctx.params` and `ctx.workflow_params`.

## Client

```python
from pathlib import Path

from botpipe import Botpipe, Policy

client = Botpipe(
    workspace=Path("."),
    default_policy=Policy(read_only=True),
    provider="codex",
    model=None,
    model_effort=None,
    runtime_config=None,
    provider_policy_config=None,
    state_dir=None,
    retention=None,
)
```

Constructor arguments:

- `workspace`: project or repository working directory. This is not the internal
  `.botpipe` state directory.
- `default_policy`: SDK client-level policy layer inherited by workflow steps,
  direct operations, and SDK step calls unless overridden.
- `provider`: `None`, a provider name such as `"codex"` or `"claude"`, or an
  already constructed `LLMProvider`.
- `model`, `model_effort`: provider overrides.
- `runtime_config`: runtime options object. `None` uses config resolution.
- `provider_policy_config`: runtime provider policy config. `None` uses config
  resolution.
- `state_dir`: internal runtime state directory. `None` uses the workspace
  `.botpipe` state root.
- `retention`: default SDK retention policy. `None` uses
  `RetentionPolicy.sdk_default()`.

Policy layers inherit. `default_policy` and per-call `policy` are not hard
security caps by themselves; strict enforcement belongs to runtime provider
policy configuration.

## `run`

```text
result = client.run(
    workflow,
    message=None,
    *,
    policy=None,
    input=None,
    params=None,
    on_input=None,
    max_pauses=8,
    max_steps=None,
    provider_questions=None,
    options=None,
    retention=None,
)
```

Arguments:

- `workflow`: workflow class or workflow reference string.
- `message`: `str | None`.
- `policy`: per-run policy layer.
- `input`: `None`, a mapping, or an exact instance of the workflow's `Input`
  model. It is keyword-only.
- `params`: `None`, a mapping, or an instance of the workflow's `Params` model.
- `on_input`: handler for `RequestInput(...)` or provider question pauses.
- `max_pauses`: maximum handled pause/resume cycles before `TooManyPauses`.
- `max_steps`: forwarded to the runtime as the step budget.
- `provider_questions`: whether provider-selected question routes are allowed.
- `options`: advanced run options; normally omit.
- `retention`: per-call retention override.

Input validation:

- If the workflow does not declare `Input`, `input` must be `None`.
- If the workflow declares required `Input` fields, pass `input=...`.
- If `input` is a model, it must be the exact compiled `Workflow.Input` type.
- If `input` is a mapping, the SDK validates it through `Workflow.Input`.
- `client.run(Wf, "message", {"field": "value"})` is invalid because `input`
  is keyword-only.
- `params` rejects unknown fields and validates through `Workflow.Params`.

Workflow references can be names, files, modules, or explicit classes, matching
the runtime loader:

```python
client.run("review", "Review this.")
client.run("workflows/review.py", "Review this.")
client.run(".botpipe/workflows/review.py", "Review this.")
client.run(".botpipe/workflows/review/flow.py:ReviewWorkflow", "Review this.")
client.run("botpipe.workflows.review.workflow:ReviewWorkflow", "Review this.")
```

## Result

`client.run(...)` returns `WorkflowResult`.

```python
result.ok
result.status
result.terminal
result.state
result.output
result.output_validation_error
result.artifacts
result.history
result.last_event
result.last_outcome
result.handled_inputs
result.debug
result.retention
```

Status fields:

- `ok`: `True` only for completed successful runs.
- `status`: `"completed"`, `"failed"`, or `"awaiting_input"`.
- `terminal`: runtime terminal tag such as `FINISH`, `FAIL`, or `AWAIT_INPUT`.

`state` is the final typed workflow state model. `output` is the validated
workflow output when the workflow declares `Output` and `build_output(...)`.

`result.artifact(name)` is shorthand for `result.artifacts.require(name)`.

## Artifacts

Declared writes are exposed through `ArtifactMap`.

```python
report = result.artifacts.report
same_report = result.artifact("report")

report.exists()
report.read_text()
report.read_bytes()
report.read_json()
report.read_model()
report.materialize("exports/report.md")
```

`ResultArtifact` fields:

- `name`
- `path`
- `kind`
- `schema`
- `source_path`
- `promoted`
- `required`
- `qualified_name`

Only declared public writes that resolve to one root-stable path are returned.
Branch/fan-in, active-worklist, and worklist-selection-dependent writes are
recorded in their runtime manifests instead of being re-rendered from the root
SDK context. Runtime telemetry files are available through debug paths when
retained, but they are not part of the public artifact map.

## Pauses And Input Handlers

Workflows pause when workflow code returns `RequestInput(...)` or when a
provider-selected question route is allowed. Pass `on_input` to answer pauses.

```python
from botpipe import StaticInput

result = client.run(
    ApprovalWorkflow,
    "Ship the release.",
    input=ApprovalWorkflow.Input(topic="release"),
    on_input=StaticInput({"approved": True}),
)
```

A custom handler receives `InputRequest`:

```python
def answer(request):
    print(request.question)
    print(request.reason)
    return {"approved": True}


result = client.run(ApprovalWorkflow, "Ship it.", on_input=answer)
```

`InputRequest` fields:

- `pending_input_id`
- `question`
- `reason`
- `best_supposition`
- `source_step`
- `source_hook`
- `source_phase`
- `input_schema`
- `input_schema_model`
- `pause_index`
- `partial`

Handler return values may be `str`, Pydantic model, mapping, sequence, number,
boolean, or `None`. Mappings, models, lists, tuples, numbers, booleans, and
`None` are JSON-serialized before resume. Strings are passed as strings.

Built-in handlers:

- `StaticInput(value)`: always returns the same value.
- `MappingInput(mapping)`: matches by pending input ID, source step, or question.
- `BestSuppositionInput()`: returns `request.best_supposition`, or raises
  `InputRequired` if absent.
- `ConsoleInput()`: prints the question and reads from standard input.

If a workflow pauses and no handler is configured, the SDK raises
`InputRequired`. The exception includes `request` and `partial`.

`provider_questions` defaults to:

- `True` when `on_input` is provided.
- `False` when `on_input` is absent.

Direct workflow `RequestInput(...)` pauses are still surfaced even when provider
questions are disabled.

## Direct Operations

Use these for one-off provider calls without a workflow.

```python
summary = client.llm(
    "Summarize the incident.",
    returns=str,
    retry=3,
    policy=None,
)

label = client.classify(
    "Classify the request.",
    choices=["incident", "question"],
    retry=3,
    policy=None,
)
```

Direct operations inherit runtime policy, SDK default policy, and explicit
operation `policy`.

## Single-Step Execution

`client.step(...)` runs a single simple declaration or supported core step
through the same runtime engine path used by normal workflows.

```python
from botpipe import FINISH, Event, Text, python_step

emit = python_step(
    lambda ctx: (ctx.artifacts.report.write_text(ctx.message or ""), Event("done"))[1],
    name="emit",
    writes=[Text("report")],
    routes={"done": FINISH},
)

result = client.step(emit, "Write a report.")
```

Signature:

```text
step_result = client.step(
    step_def,
    message=None,
    *,
    policy=None,
    input=None,
    params=None,
    routes=None,
    on_input=None,
    max_pauses=8,
    max_steps=None,
    provider_questions=None,
    retention=None,
)
```

`StepResult` fields:

- `ok`
- `status`
- `route`
- `value`
- `state`
- `artifacts`
- `workflow_result`

`value` is currently `None`; use `workflow_result`, `state`, and `artifacts` for
outputs.

`client.step(...)` does not support branch-group declarations or worklist-scoped
declarations.

## Step Helpers

The SDK can build and run common step types directly.
The examples below assume the named symbols are imported from `botpipe`.

### `prompt_step`

```python
result = client.prompt_step(
    "Review {{ message }}.",
    "Review the rollout.",
    input=None,
    name="review",
    writes=[Md("report")],
    reads=(),
    requires=(),
    routes={"done": FINISH},
    session=None,
    retry=3,
    policy=None,
    on_input=None,
    max_pauses=8,
    max_steps=None,
    provider_questions=None,
    retention=None,
)
```

### `produce_verify_step`

```python
result = client.produce_verify_step(
    producer="Draft the package.",
    verifier="Verify the package.",
    message="Prepare release evidence.",
    input=None,
    name="produce_verify",
    writes=[Md("draft")],
    verifier_writes=[Md("review")],
    reads=(),
    requires=(),
    verifier_requires=(),
    routes={"accepted": FINISH, "needs_rework": SELF},
    session=None,
    verifier_session=None,
    retry=3,
    policy=None,
    on_input=None,
    max_pauses=8,
    max_steps=None,
    provider_questions=None,
    retention=None,
)
```

### `python_step`

```python
def handler(ctx):
    return Event("done")


result = client.python_step(
    handler,
    "Run local code.",
    input=None,
    name="python",
    writes=(),
    reads=(),
    requires=(),
    routes={"done": FINISH},
    policy=None,
    on_input=None,
    max_pauses=8,
    max_steps=None,
    retention=None,
)
```

`policy` on SDK Python steps applies to provider operations called inside the
handler. It does not sandbox the Python function itself.

### `workflow_step`

```python
result = client.workflow_step(
    ChildWorkflow,
    "Outer request.",
    input=None,
    child_message="Child request.",
    name="workflow",
    params={"mode": "strict"},
    writes=(),
    reads=(),
    requires=(),
    routes={"done": FINISH},
    policy=None,
    on_input=None,
    max_pauses=8,
    max_steps=None,
    provider_questions=None,
    retention=None,
)
```

`message` is the outer SDK invocation request. `child_message` is the child
workflow request; if omitted, the SDK uses `message`.

## Retention

The SDK writes normal runtime task/run state while executing. Retention controls
what remains after the call returns.

```python
from botpipe import RetentionPolicy

client = Botpipe(workspace=".", provider="codex", retention=RetentionPolicy.keep_all())
result = client.run(MyWorkflow, "Run it.", retention=RetentionPolicy.ephemeral())
```

Retention modes:

- `RetentionPolicy.sdk_default()`: `delete_task_scratch`. Successful task
  scratch is deleted, declared task-local writes are promoted, workspace writes
  remain in place, and failed or awaiting-input runs keep scratch by default.
- `RetentionPolicy.keep_all()`: keep the SDK task directory and declared writes
  in their runtime locations.
- `RetentionPolicy.ephemeral()`: delete all SDK-managed task scratch and omit
  task-local declared writes from the result artifact map; workspace writes stay.

`result.retention` records:

- `policy`
- `task_scratch_retained`
- `task_scratch_deleted`
- `promoted_artifacts`
- `retained_task_dir`

Use `promoted_writes_dir=` on `RetentionPolicy(...)` when promoted declared
writes should go to a specific directory.

## Cleanup

`cleanup(...)` deletes old SDK-managed task directories. It only considers task
directories carrying the SDK sentinel file.

```python
from datetime import timedelta

dry_run = client.cleanup(older_than=timedelta(days=2), dry_run=True)
deleted = client.cleanup(older_than=timedelta(days=2), include_failed=True)
```

Arguments:

- `older_than`: optional age filter.
- `include_failed`: include failed or awaiting-input SDK tasks. Defaults to
  `False`.
- `dry_run`: report candidates without deleting.

Return value: `CleanupResult(deleted, skipped, errors, dry_run)`.

## Debug Info

`result.debug` exposes internal paths for inspection when retained:

- `task_id`
- `run_id`
- `task_dir`
- `workflow_dir`
- `run_dir`
- `events_file`
- `trace_file`
- `checkpoint_file`

These are diagnostic handles, not the durable public SDK control surface. For
manual resume, event browsing, run listing, or trace browsing, use the runtime
CLI/API rather than treating SDK debug paths as stable orchestration state.

## Errors

All SDK-specific errors inherit from `BotpipeSDKError`.

- `WorkflowInputError`: invalid or missing workflow `input`.
- `WorkflowParameterError`: invalid workflow `params`.
- `InputRequired`: run paused and no handler was available.
- `TooManyPauses`: pause budget exceeded.
- `InputResponseValidationError`: handler response could not be serialized or
  failed runtime resume validation.
- `SDKExecutionError`: provider resolution, workflow resolution, runtime
  execution, retention, or cleanup failure at the SDK boundary.

`BotpipeSDKError.original_error` carries the wrapped exception when available.
`SDKExecutionError.task_dir` may point to retained runtime state after a failure.

## Public Export Checklist

Root SDK exports include:

```text
Botpipe,
WorkflowResult, StepResult,
ArtifactMap, ResultArtifact,
RetentionPolicy, RetentionInfo, CleanupResult,
InputRequest, HandledInput, SDKDebugInfo,
BotpipeSDKError, WorkflowInputError, WorkflowParameterError,
InputRequired, TooManyPauses, InputResponseValidationError, SDKExecutionError,
ConsoleInput, StaticInput, MappingInput, BestSuppositionInput
```

The root package also exports the simple authoring API, so most applications can
use one import module:

```python
from botpipe import Botpipe, Workflow, step, python_step
```

## SDK Rules

- Use `Botpipe(workspace=...)` with the real project root.
- Pass `input=` and `params=` by keyword.
- Keep `message`, `input`, and `params` separate.
- Use `on_input` for bounded automated pause handling.
- Set `provider_questions=True` only when provider-selected questions are part
  of the intended interaction model.
- Read declared outputs through `result.artifacts`.
- Inspect `result.debug` only for diagnostics.
- Use retention policies intentionally for long-running agents and test suites.
- Use the CLI/runtime APIs for durable task/run management and manual resume.
