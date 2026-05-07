Below is the revised SDK spec, tightened for implementation.

Grounding: v3 already exposes simple authoring symbols from `autoloop/__init__.py`, compiles `Workflow.Input` as `CompiledWorkflow.input_model`, stores `message` and `workflow_input` separately in runtime paths, and validates typed workflow input through `_coerce_workflow_input_payload`. 

## 1. Product boundary

* The SDK is a **simple pure-Python execution facade**.
* One SDK call equals one independent workflow invocation.
* The SDK must not expose:

  * public `task_id`,
  * public `run_id`,
  * public checkpoints,
  * public resume,
  * event browsing,
  * trace browsing,
  * durable observability controls.
* The standard workflow runtime/API remains responsible for:

  * durable resumability,
  * explicit task/run management,
  * event logs,
  * traces,
  * operational inspection,
  * manual resume.
* The SDK may still use runtime task/run/checkpoint machinery internally to complete one call.

## 2. Input model decision

* `message` is the **primary/default workflow input**.
* `Workflow.Input` is **additional typed input fields**.
* `Workflow.Params` is workflow configuration, not workflow input.
* `on_input` handles runtime pauses, not initial workflow input.
* The canonical SDK invocation shape is:

```python
result = client.run(
    EscalationWorkflow,
    "Checkout fails after deploy.",
    EscalationWorkflow.Input(customer="Acme", severity_hint="high"),
    on_input=handler,
)
```

* Message-only workflow:

```python
result = client.run(SummarizeWorkflow, "Summarize this document.")
```

* No-message/no-typed-input workflow:

```python
result = client.run(HealthCheckWorkflow)
```

## 3. Public SDK module

* Add `autoloop/sdk.py`.
* Export these from `autoloop/__init__.py`:

```python
from .sdk import (
    Autoloop,
    WorkflowResult,
    StepResult,
    ArtifactMap,
    InputRequest,
    HandledInput,
    SDKDebugInfo,
    AutoloopSDKError,
    WorkflowInputError,
    WorkflowParameterError,
    InputRequired,
    TooManyPauses,
    InputResponseValidationError,
    SDKExecutionError,
    ConsoleInput,
    StaticInput,
    MappingInput,
    BestSuppositionInput,
)
```

## 4. `Autoloop` constructor

```python
class Autoloop:
    def __init__(
        self,
        *,
        root: str | Path = ".",
        provider: str | LLMProvider | None = None,
        model: str | None = None,
        model_effort: str | None = None,
        runtime_config: RuntimeConfig | None = None,
        provider_policy_config: ProviderPolicyRuntimeConfig | None = None,
        state_dir: str | Path | None = None,
    ) -> None:
        ...
```

* `root` resolves to a workspace root.
* `provider` accepts:

  * an already constructed `LLMProvider`;
  * a provider name resolvable by the existing runtime provider backend;
  * `None`, meaning use existing runtime config/default resolution.
* If provider cannot be resolved, raise `SDKExecutionError` with an actionable message.
* `model` and `model_effort` are provider overrides.
* `runtime_config` defaults to `RuntimeConfig()`.
* `provider_policy_config` defaults to `ProviderPolicyRuntimeConfig()`.
* `state_dir` defaults to the existing runtime state directory.
* MVP must keep generated artifacts on disk. Do not implement cleanup yet.

## 5. `Autoloop.run` signature

Use positional-only workflow, message, typed input.

```python
def run(
    self,
    workflow: type[Workflow] | str,
    message: str | None = None,
    typed_input: BaseModel | None = None,
    /,
    *,
    params: BaseModel | Mapping[str, Any] | None = None,
    on_input: InputHandler | None = None,
    max_pauses: int = 8,
    max_steps: int | None = None,
    provider_questions: bool | None = None,
    options: RunOptions | None = None,
) -> WorkflowResult:
    ...
```

* Public docs should describe the third positional argument as `Workflow.Input(...)`, even though the internal parameter name is `typed_input`.
* `workflow` must resolve to a workflow class.
* `message` must be `str | None`.
* `typed_input` must be `None` or an **exact instance** of the compiled workflow’s `Input` model.
* Do not accept `dict` as `typed_input`.
* Do not support `client.run(Wf, **input_fields)`.
* Do not support `client.run(Wf, input={...})`.
* `params` may be `None`, mapping, or `Workflow.Params` instance.
* `max_pauses` must be an integer `>= 0`.
* `max_steps` is forwarded into runtime options.
* `provider_questions` default:

  * `True` if `on_input is not None`;
  * `False` if `on_input is None`.

## 6. Typed input validation rules

* Compile/resolve the workflow before validating typed input.
* If the workflow does not declare `Input`:

  * `typed_input` must be `None`;
  * otherwise raise `WorkflowInputError`.
* If the workflow declares `Input` and `typed_input is None`:

  * try `compiled.input_model()`;
  * if it succeeds, use that default/optional typed input;
  * if it fails because required fields are missing, raise `WorkflowInputError`.
* If `typed_input is not None`:

  * require `type(typed_input) is compiled.input_model`;
  * do not accept subclasses in MVP;
  * serialize with `typed_input.model_dump(mode="json")`.
* `Workflow.Input` must not declare a field named `message`.
* Add compile/definition validation error:

```text
<WorkflowName>.Input must not declare field 'message'; message is provided by client.run(..., message).
```

## 7. Runtime context input view

Implement a composite input view without losing the raw typed input model.

### Add to `Context`

* Add constructor argument:

```python
message: str | None = None
```

* Store separate fields:

```python
self._message = message
self._input_fields = workflow_input
```

* Add properties:

```python
@property
def message(self) -> str | None:
    return self._message

@property
def input_fields(self) -> BaseModel | None:
    return self._input_fields

@property
def input(self) -> WorkflowInputView:
    return WorkflowInputView(message=self._message, fields=self._input_fields)
```

### Add `WorkflowInputView`

```python
@dataclass(frozen=True)
class WorkflowInputView:
    message: str | None
    fields: BaseModel | None = None

    def __getattr__(self, name: str) -> Any:
        if name == "message":
            return self.message
        if self.fields is not None:
            return getattr(self.fields, name)
        raise AttributeError(name)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = {"message": self.message}
        if self.fields is not None:
            payload.update(self.fields.model_dump(*args, **kwargs))
        return payload
```

* `ctx.input.message` must always exist.
* `ctx.input.<field>` resolves to `Workflow.Input.<field>`.
* `ctx.input_fields` exposes the raw `Workflow.Input` instance or `None`.
* `ctx.message` is a direct alias for the message.
* Do not persist `message` inside `workflow_input`.

## 8. Context propagation

* Update every `Context(...)` construction path to pass `message`.
* `Engine.run(...)` must accept and pass `message` into root `Context`.
* `Engine.resume(...)` must accept and pass the same `message` into resumed `Context`.
* Branch child contexts must copy:

```python
message=parent.message
workflow_input=parent.input_fields
```

* Do **not** pass `workflow_input=parent.input`, because `parent.input` is now the composite view.
* Fan-in contexts must use the same rule.
* Child workflow invocation keeps separate `message` and typed `input`.

## 9. Prompt validation/rendering

* `{input.message}` is always a valid placeholder.
* `{input.<field>}` is valid only when `<field>` is declared on `Workflow.Input`.
* Unknown input placeholders remain validation errors.
* If `message is None`, `{input.message}` renders as an empty string.
* If an optional typed field is `None`, render as an empty string.
* Required typed fields are validated before execution.
* Artifact path rendering through runtime templates must also support `input.message`.

## 10. Runtime persistence model

* Preserve existing separation:

  * `message` goes to task/run request text.
  * `workflow_input` stores only serialized `Workflow.Input` fields.
  * `workflow_params` stores configuration.
* Do not store this inside `workflow_input`:

```json
{"message": "...", "customer": "Acme"}
```

* Correct `workflow_input` example:

```json
{"customer": "Acme", "severity_hint": "high"}
```

## 11. Internal run algorithm

`Autoloop.run(...)` must use the existing runtime runner first, not a parallel engine implementation.

Pseudo-code:

```python
def run(...):
    resolved = resolve_workflow_reference(root, workflow)
    compiled = compile_workflow(resolved.workflow_cls)

    structured_input_payload = coerce_sdk_typed_input(compiled, typed_input)
    structured_params_payload = coerce_workflow_parameter_mapping(
        resolved.parameters_cls,
        params,
    )

    task_id = generate_sdk_task_id(compiled.workflow_name)
    run_id = None
    resume = False
    answer = None
    handled_inputs = []

    for pause_index in range(max_pauses + 1):
        execution = execute_workflow_package(
            resolved.workflow_cls,
            provider=self._provider,
            options=RunnerOptions(
                root=self.root,
                task_id=task_id,
                run_id=run_id,
                message=message,
                resume=resume,
                answer=answer,
                state_dir=self.state_dir,
                max_steps=max_steps,
                workflow_params=structured_params_payload,
                workflow_input=structured_input_payload,
                runtime_config=runtime_config_with_provider_question_policy,
                provider_policy_config=self.provider_policy_config,
            ),
        )

        result = WorkflowResult.from_execution(
            execution,
            handled_inputs=tuple(handled_inputs),
        )

        if result.terminal != AWAIT_INPUT:
            return result

        request = InputRequest.from_execution(
            execution,
            pause_index=pause_index,
            partial=result,
        )

        if on_input is None:
            raise InputRequired(request=request, partial=result)

        response = on_input(request)
        answer = serialize_input_response(response)

        handled_inputs.append(
            HandledInput(request=request, response=response)
        )

        run_id = execution.run_workspace.run_id
        resume = True

    raise TooManyPauses(max_pauses=max_pauses, partial=result)
```

* `task_id` remains stable across internal pause/resume segments.
* `run_id` is captured from the first execution and reused for internal resume.
* `message`, `workflow_input`, and `workflow_params` must remain stable across internal resumes.
* The SDK does not expose `client.resume(...)`.

## 12. SDK task IDs

* Generate internally.
* Format:

```text
sdk-<workflow-name>-<utc-yyyymmddThhmmssZ>-<8hex>
```

* Example:

```text
sdk-escalation-workflow-20260507T142233Z-a1b2c3d4
```

* Must be path-safe.
* Retry on collision.
* Expose only under `result.debug.task_id`.

## 13. Provider questions

* Add `provider_questions` to `client.run`.
* Effective value:

  * if explicitly passed, use it;
  * otherwise `on_input is not None`.
* If `provider_questions=True`, provider-visible question routes are allowed.
* If `provider_questions=False`, provider-visible question routes are suppressed.
* Direct Python `RequestInput(...)` pauses must still work regardless of this setting.
* Do not rely only on incidental `full_auto` semantics if a clearer runtime interaction policy hook exists.
* If current runtime only exposes this through `RuntimeConfig.full_auto`, adapt the SDK runtime config in one helper function.

## 14. Pause handling

### Input handler type

```python
InputResponse = (
    str
    | BaseModel
    | Mapping[str, Any]
    | Sequence[Any]
    | int
    | float
    | bool
    | None
)

InputHandler = Callable[[InputRequest], InputResponse]
```

### `InputRequest`

```python
@dataclass(frozen=True)
class InputRequest:
    pending_input_id: str | None
    question: str
    reason: str | None
    best_supposition: str | None
    source_step: str | None
    source_hook: str | None
    source_phase: str | None
    input_schema: dict[str, Any] | None
    input_schema_model: str | None
    pause_index: int
    partial: WorkflowResult
```

* Prefer checkpoint pending input metadata.
* Fallback to last question-style event only when pending input metadata is unavailable.
* `partial` is a `WorkflowResult` for the paused execution.

### Response serialization

```python
def serialize_input_response(value: InputResponse) -> str:
    if isinstance(value, BaseModel):
        return json.dumps(value.model_dump(mode="json"), ensure_ascii=False)
    if isinstance(value, Mapping):
        return json.dumps(dict(value), ensure_ascii=False)
    if isinstance(value, tuple):
        return json.dumps(list(value), ensure_ascii=False)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float, bool)) or value is None:
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        return value
    raise TypeError(...)
```

* Runtime resume can parse JSON answers and validate them against pending schemas.
* If serialization fails, raise `InputResponseValidationError`.
* If runtime rejects the answer schema, wrap the runtime error in `InputResponseValidationError`.

## 15. Pause errors

```python
class InputRequired(AutoloopSDKError):
    request: InputRequest
    partial: WorkflowResult

class TooManyPauses(AutoloopSDKError):
    max_pauses: int
    partial: WorkflowResult | None

class InputResponseValidationError(AutoloopSDKError):
    request: InputRequest
    response: object
    original_error: Exception
```

* If workflow pauses and `on_input is None`, raise `InputRequired`.
* If pauses exceed `max_pauses`, raise `TooManyPauses`.
* If handler raises an exception, let it propagate unless wrapping is needed to add SDK context. If wrapped, preserve `.original_error`.

## 16. Built-in input handlers

### `StaticInput`

```python
class StaticInput:
    def __init__(self, value: InputResponse) -> None: ...
    def __call__(self, request: InputRequest) -> InputResponse: ...
```

* Always returns the configured value.

### `BestSuppositionInput`

```python
class BestSuppositionInput:
    def __call__(self, request: InputRequest) -> str:
        if request.best_supposition:
            return request.best_supposition
        raise InputRequired(request=request, partial=request.partial)
```

### `MappingInput`

```python
class MappingInput:
    def __init__(self, mapping: Mapping[str, InputResponse]) -> None: ...
    def __call__(self, request: InputRequest) -> InputResponse: ...
```

Lookup order:

1. `pending_input_id`
2. `source_step`
3. `question`

* If no key matches, raise `InputRequired`.

### `ConsoleInput`

```python
class ConsoleInput:
    def __call__(self, request: InputRequest) -> str:
        ...
```

* Print question.
* Print reason if available.
* Print best supposition if available.
* Return `input("> ")`.
* Must be opt-in only. The SDK must never call `input()` by default.

## 17. `WorkflowResult`

```python
@dataclass(frozen=True)
class WorkflowResult:
    ok: bool
    status: Literal["completed", "failed", "awaiting_input"]
    terminal: str
    state: BaseModel
    output: Any | None
    output_validation_error: str | None
    artifacts: ArtifactMap
    history: tuple[str, ...]
    last_event: Event | None
    last_outcome: Outcome | None
    handled_inputs: tuple[HandledInput, ...]
    debug: SDKDebugInfo
```

Status mapping:

* `terminal == FINISH`:

  * `status="completed"`
  * `ok=True`
* `terminal == FAIL`:

  * `status="failed"`
  * `ok=False`
* `terminal == AWAIT_INPUT`:

  * `status="awaiting_input"`
  * `ok=False`
* Unknown terminal:

  * `status="failed"`
  * `ok=False`

## 18. `HandledInput`

```python
@dataclass(frozen=True)
class HandledInput:
    request: InputRequest
    response: object
```

* Store raw handler response.
* Do not require response to be JSON-serializable after the run; serialization already happened before resume.

## 19. `SDKDebugInfo`

```python
@dataclass(frozen=True)
class SDKDebugInfo:
    task_id: str
    run_id: str
    task_dir: Path
    workflow_dir: Path
    run_dir: Path
    events_file: Path
    trace_file: Path | None
    checkpoint_file: Path | None
```

* This is for debugging only.
* Do not use it in primary docs except for troubleshooting.

## 20. Artifact result API

```python
class ArtifactMap(Mapping[str, ArtifactHandle]):
    def __getattr__(self, name: str) -> ArtifactHandle: ...
    def require(self, name: str) -> ArtifactHandle: ...
```

* `result.artifacts.brief.read_json()` must work.
* `result.artifact("brief")` convenience method may be added.
* Missing artifact raises `KeyError` or `MissingArtifactError`.
* Build artifact handles from compiled public artifacts:

  * use `compiled.artifact_items(authoritative=False)`;
  * resolve each compiled artifact template against the completed run context/workspace.
* Do not rely only on output metadata.
* Use existing artifact resolution helpers where possible.

## 21. `Autoloop.llm`

```python
def llm(
    self,
    prompt: str | Path | Prompt,
    *,
    returns: Any = str,
    retry: int = 3,
    policy: ProviderPolicy | ProviderPolicyOverride | None = None,
) -> Any:
    ...
```

* Delegate to existing `llm_call(...)`.
* Pass explicit SDK provider.
* Use an SDK operation folder for replay if needed.
* No workflow task/checkpoint semantics.
* No pause handling.

## 22. `Autoloop.classify`

```python
def classify(
    self,
    prompt: str | Path | Prompt,
    *,
    choices: Sequence[str],
    retry: int = 3,
    policy: ProviderPolicy | ProviderPolicyOverride | None = None,
) -> str:
    ...
```

* Delegate to existing `classify_call(...)`.
* Pass explicit SDK provider.
* Return exactly one declared choice.
* Let existing operation validation reject invalid provider output.

## 23. `Autoloop.step`

```python
def step(
    self,
    declaration: object,
    message: str | None = None,
    typed_input: BaseModel | None = None,
    /,
    *,
    on_input: InputHandler | None = None,
    max_pauses: int = 8,
    max_steps: int | None = None,
) -> StepResult:
    ...
```

MVP accepted declarations:

* simple named step declaration from `autoloop.simple`;
* core `Step` instance only if it can compile inside a synthetic one-step workflow.

MVP rejected declarations:

* worklist-scoped steps;
* branch-group steps;
* steps requiring workflow-level artifacts not present in synthetic workflow;
* child-workflow steps unless child workflow reference is directly resolvable.

Implementation:

* Create an internal one-step workflow class.
* If `typed_input` is provided, set internal workflow `Input = type(typed_input)`.
* If no terminal route is declared, add default `done -> FINISH`.
* Execute through `client.run(...)`.
* Return `StepResult`.

```python
@dataclass(frozen=True)
class StepResult:
    ok: bool
    route: str | None
    value: Any | None
    state: BaseModel
    artifacts: ArtifactMap
    workflow_result: WorkflowResult
```

* Do not bypass the engine.
* Operation-backed steps must execute inside workflow runtime.

## 24. Params handling

* `params` are workflow configuration.
* `params` remain visible through `ctx.params`.
* `params` must not appear on `ctx.input`.
* Accept:

  * `None`,
  * mapping,
  * exact or valid `Workflow.Params` Pydantic instance.
* Use existing parameter coercion path.
* If workflow has no `Params` but params are provided:

  * preserve existing runtime behavior if it supports free mapping;
  * otherwise raise `WorkflowParameterError`.

## 25. Child workflow invocation alignment

* `ctx.invoke_workflow(...)` should preserve the same conceptual model:

  * `message` is primary input;
  * `input` is additional typed fields;
  * `parameters` are config.
* It may continue accepting a dict for `input` internally for runtime compatibility, but SDK public `client.run(...)` must not accept dict typed input.
* Child workflow result remains the existing `ChildWorkflowResult`.

## 26. Error classes

```python
class AutoloopSDKError(Exception): ...

class WorkflowInputError(AutoloopSDKError): ...
class WorkflowParameterError(AutoloopSDKError): ...
class InputRequired(AutoloopSDKError): ...
class TooManyPauses(AutoloopSDKError): ...
class InputResponseValidationError(AutoloopSDKError): ...
class SDKExecutionError(AutoloopSDKError): ...
```

* Preserve `.original_error` where wrapping runtime/provider exceptions.
* Error messages should name:

  * workflow class,
  * expected input type,
  * received type,
  * missing required fields where available.

## 27. No cleanup in MVP

* Keep generated `.autoloop` task/run folders.
* Do not implement `keep_artifacts=False` in MVP.
* Do not return artifact handles pointing to deleted files.
* Cleanup can be added later as an explicit in-memory snapshot feature.

## 28. Async API

* Optional after sync MVP.
* If implemented:

```python
async def arun(...): ...
async def astep(...): ...
async def allm(...): ...
async def aclassify(...): ...
```

* Sync methods must not silently bridge an active event loop if existing runtime cannot support that.
* If sync method is called inside an active event loop and cannot proceed, raise a clear `SDKExecutionError` suggesting async API.

## 29. Acceptance tests

### `message` and typed input

* `client.run(Wf, "hello")` makes `ctx.input.message == "hello"`.
* `client.run(Wf, None)` makes `ctx.input.message is None`.
* `client.run(Wf, "hello", Wf.Input(foo="bar"))` makes:

  * `ctx.input.message == "hello"`;
  * `ctx.input.foo == "bar"`;
  * `ctx.input_fields.foo == "bar"`.
* `ctx.message == ctx.input.message`.
* `ctx.input.model_dump()` includes `message` plus typed fields.
* `workflow_input` persisted metadata does not include `message`.

### Input validation

* `Workflow.Input.message` field fails compile/definition validation.
* Workflow with required `Input` fields fails when `typed_input` is omitted.
* Workflow with optional/default-only `Input` fields runs when `typed_input` is omitted.
* Passing `OtherWorkflow.Input(...)` fails.
* Passing plain dict as third positional argument fails.
* Passing subclass of `Workflow.Input` fails in MVP.

### Params

* `params` available as `ctx.params`.
* `params` not available as `ctx.input`.
* `Workflow.Params` instance works.
* Mapping params work if runtime supports them.

### Pause handling

* Python step returning `RequestInput(...)` pauses.
* `on_input` receives `InputRequest`.
* Handler returning dict resumes.
* Handler returning `BaseModel` resumes.
* Handler returning string resumes.
* Schema mismatch raises `InputResponseValidationError`.
* No handler raises `InputRequired`.
* Exceeding `max_pauses` raises `TooManyPauses`.

### Provider questions

* With `on_input`, provider questions are enabled by default.
* Without `on_input`, provider questions are disabled by default.
* Explicit `provider_questions=True` permits provider question pauses.
* Explicit `provider_questions=False` suppresses provider question routes.
* Direct `RequestInput(...)` still pauses regardless.

### Results

* FINISH maps to `ok=True`, `status="completed"`.
* FAIL maps to `ok=False`, `status="failed"`.
* AWAIT_INPUT partial maps to `ok=False`, `status="awaiting_input"`.
* `result.artifacts.<name>.read_json()` works.
* `result.debug.task_id` and `result.debug.run_id` exist.

### Standalone operations

* `client.llm(...)` delegates to existing operation path.
* `client.classify(..., choices=[...])` returns one declared choice.
* `client.step(...)` executes through generated one-step workflow.
* Operation-backed steps work through `client.step(...)`.

## 30. Non-goals

* No public `client.resume(...)`.
* No public checkpoint API.
* No public task/run lifecycle API.
* No event-log browsing API.
* No trace inspection API.
* No `client.run(Wf, **input_fields)`.
* No `client.run(Wf, input={...})`.
* No dict typed input in public SDK.
* No automatic console input.
* No cleanup/deletion of task/run folders in MVP.

## 31. Final examples

### Message-only

```python
client = Autoloop(provider="codex")

result = client.run(
    SummarizeWorkflow,
    "Summarize this incident report.",
)
```

### Message plus typed additional input

```python
result = client.run(
    EscalationWorkflow,
    "Checkout fails after the latest deploy.",
    EscalationWorkflow.Input(
        customer="Acme",
        severity_hint="high",
    ),
)
```

### Pause handling

```python
def approve(req: InputRequest):
    return {"approved": True, "comment": "Proceed"}

result = client.run(
    EscalationWorkflow,
    "Checkout fails after the latest deploy.",
    EscalationWorkflow.Input(customer="Acme"),
    on_input=approve,
)
```

### Standalone LLM/classify

```python
summary = client.llm("Summarize this in one paragraph: ...")

label = client.classify(
    "Customer cannot complete checkout.",
    choices=["incident", "feature_request", "question"],
)
```

### Standalone step

```python
step_result = client.step(
    SomeStepDeclaration,
    "Run this step against the following request.",
    on_input=approve,
)
```

