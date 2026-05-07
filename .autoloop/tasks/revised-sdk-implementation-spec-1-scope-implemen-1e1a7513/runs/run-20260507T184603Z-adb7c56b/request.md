# Revised SDK implementation spec

## 1. Scope

* Implement the missing SDK features on top of the current pasted implementation.
* Do not replace the existing engine, runner, checkpoint, provider, artifact, or workflow compiler paths.
* Keep SDK execution as a thin facade over `execute_workflow_package(...)`.
* Preserve the current SDK mental model:

  * `message` is the primary/default workflow input.
  * `Workflow.Input` is additional typed input.
  * `Workflow.Params` is configuration.
  * `on_input` handles pauses inside one SDK call.
* Add:

  * concrete step class exports,
  * step helper methods,
  * result-safe retained artifacts,
  * write-contract retention,
  * SDK task sentinel files,
  * safe SDK task deletion,
  * cleanup utility,
  * prompt rendering for `{input.message}`,
  * correct one-step produce/verify routing.

## 2. Public exports

Update `autoloop/__init__.py`.

### 2.1 Export concrete step classes

Add:

```python
from autoloop.core.steps import (
    Step,
    PromptStep,
    ProduceVerifyStep,
    PythonStep,
    ChildWorkflowStep,
)
```

Add to `__all__`:

```python
"Step",
"PromptStep",
"ProduceVerifyStep",
"PythonStep",
"ChildWorkflowStep",
```

Do **not** export `BranchGroupStep` in the SDK MVP.

### 2.2 Export retention/result classes

Add these imports from `.sdk`:

```python
ResultArtifact,
RetentionInfo,
RetentionPolicy,
CleanupResult,
```

Add to `__all__`:

```python
"ResultArtifact",
"RetentionInfo",
"RetentionPolicy",
"CleanupResult",
```

### 2.3 Keep existing exports

* Keep existing simple factory exports:

  * `step`
  * `produce_verify_step`
  * `python_step`
  * `validation_step`
  * `workflow_step`
* Keep existing SDK exports:

  * `Autoloop`
  * `WorkflowResult`
  * `StepResult`
  * `ArtifactMap`
  * `InputRequest`
  * `InputRequired`
  * etc.
* The recommended SDK authoring path should be:

  * concrete step classes,
  * `client.prompt_step(...)`,
  * `client.produce_verify_step(...)`,
  * `client.python_step(...)`,
  * `client.workflow_step(...)`.

## 3. `sdk.py` imports

Update `autoloop/sdk.py` imports.

Current implementation imports only a subset of step classes. Replace the step import with:

```python
from autoloop.core.steps import (
    BranchGroupStep,
    ChildWorkflowStep,
    PromptStep,
    ProduceVerifyStep,
    PythonStep,
    Step,
)
```

Also import or define:

```python
shutil
timedelta
datetime
timezone
Literal
```

as needed for retention, promotion, sentinel, and cleanup.

## 4. Prompt rendering fix

The current validation permits `{input.message}`, but provider prompt rendering must also replace it.

### 4.1 Update `Engine._resolve_prompt`

Change:

```python
replace_roots=frozenset({"ctx", "item", "worklist", "branch", "fan_in"})
```

to:

```python
replace_roots=frozenset({"ctx", "input", "item", "worklist", "branch", "fan_in"})
```

### 4.2 Keep both message styles

Both must work:

```text
{input.message}
{ctx.message}
```

Both must resolve to the same runtime message value.

### 4.3 Preserve artifact-path restriction

Do not allow `ctx.*` in artifact paths. The current `_reject_ctx_placeholders_in_artifact_template(...)` behavior should remain.

## 5. Retention policy

Add write-contract retention to `autoloop/sdk.py`.

### 5.1 Retention model

Default successful SDK behavior:

```text
delete SDK-generated .autoloop task scratch
keep explicitly declared writes
keep normal workspace writes
```

### 5.2 Define scratch vs writes

* **SDK task scratch**

  * `.autoloop/tasks/<sdk-task-id>/...`
  * request snapshots
  * run metadata
  * checkpoints
  * traces
  * events
  * raw provider outputs
  * generated workflow package files
  * undeclared files under the SDK task directory

* **Declared writes**

  * compiled public artifacts from workflow/step `writes`
  * route-required artifact writes when represented as compiled artifacts
  * artifacts surfaced through `compiled.artifact_items(authoritative=False)`

* **Workspace writes**

  * files outside `.autoloop/tasks/<sdk-task-id>/...`
  * user repository files
  * side-effect files produced by Python steps
  * explicitly declared artifacts whose paths resolve outside task scratch

### 5.3 Define `RetentionPolicy`

```python
RetentionMode = Literal[
    "keep_all",
    "delete_task_scratch",
    "delete_all_sdk_managed",
]


@dataclass(frozen=True)
class RetentionPolicy:
    mode: RetentionMode = "delete_task_scratch"

    keep_declared_writes: bool = True
    keep_workspace_writes: bool = True

    keep_on_failure: bool = True
    keep_on_input_required: bool = True
    keep_on_too_many_pauses: bool = True

    promote_task_writes: bool = True
    promoted_writes_dir: Path | None = None

    @classmethod
    def sdk_default(cls) -> "RetentionPolicy":
        return cls(mode="delete_task_scratch")

    @classmethod
    def keep_all(cls) -> "RetentionPolicy":
        return cls(mode="keep_all")

    @classmethod
    def ephemeral(cls) -> "RetentionPolicy":
        return cls(
            mode="delete_all_sdk_managed",
            keep_declared_writes=False,
            keep_workspace_writes=True,
            keep_on_failure=False,
            keep_on_input_required=False,
            keep_on_too_many_pauses=False,
        )
```

### 5.4 `delete_all_sdk_managed` semantics

Define it precisely:

* delete SDK task scratch;
* do not promote task-local declared writes when `keep_declared_writes=False`;
* never delete workspace writes;
* never delete promoted outputs from previous runs;
* never delete files outside the generated SDK task directory except files explicitly promoted by the current call.

### 5.5 Scope of retention

* Retention applies to `client.run(...)`, `client.step(...)`, and step helpers.
* Retention does **not** apply to `client.llm(...)` and `client.classify(...)` in MVP, unless those helpers are later changed to create SDK task directories.
* If `llm` or `classify` create operation replay folders, cleanup for those folders is future work.

## 6. Add retention to `Autoloop.__init__`

Update constructor:

```python
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
    retention: RetentionPolicy | None = None,
) -> None:
    ...
```

Implementation:

```python
self.retention = retention or RetentionPolicy.sdk_default()
```

## 7. Add per-call `retention=`

Add:

```python
retention: RetentionPolicy | None = None
```

to:

* `Autoloop.run(...)`
* `Autoloop.step(...)`
* `Autoloop.prompt_step(...)`
* `Autoloop.produce_verify_step(...)`
* `Autoloop.python_step(...)`
* `Autoloop.workflow_step(...)`

Effective policy:

```python
effective_retention = retention or self.retention
```

## 8. SDK task sentinel

Every SDK-generated task directory must include:

```text
.autoloop/tasks/<sdk-task-id>/.autoloop-sdk-task.json
```

Payload:

```json
{
  "schema": "autoloop.sdk_task/v1",
  "generated_by": "autoloop.sdk",
  "task_id": "sdk-summarize-20260507T142233Z-a1b2c3d4",
  "created_at": "2026-05-07T14:22:33Z",
  "retention_mode": "delete_task_scratch"
}
```

### 8.1 Creation timing

* Create the sentinel after the task workspace is resolved.
* Create it before `execute_workflow_package(...)` starts.
* Create it for:

  * `client.run(...)`
  * `client.step(...)`
  * all step helper methods, indirectly through `client.step(...)`.

### 8.2 Sentinel helper

Add:

```python
def _write_sdk_task_sentinel(
    *,
    task_dir: Path,
    task_id: str,
    policy: RetentionPolicy,
) -> None:
    ...
```

## 9. Safe deletion guard

Add:

```python
def _safe_delete_sdk_task_dir(
    *,
    task_dir: Path,
    task_id: str,
    tasks_root: Path,
) -> None:
    ...
```

Before deletion, require all:

* `task_id.startswith("sdk-")`
* `task_dir.name == task_id`
* `task_dir.resolve()` is under `tasks_root.resolve()`
* sentinel exists at `task_dir / ".autoloop-sdk-task.json"`
* sentinel JSON has:

  * `"schema": "autoloop.sdk_task/v1"`
  * `"generated_by": "autoloop.sdk"`
  * `"task_id": task_dir.name`
* resolved `task_dir` is not:

  * workspace root
  * `.autoloop`
  * `.autoloop/tasks`
  * user home
  * filesystem root

On guard failure:

```python
raise SDKExecutionError("refusing to delete non-SDK or unsafe task directory ...")
```

Do not delete anything.

## 10. Result artifact model

Replace public SDK result artifacts from raw `ArtifactHandle` to retained `ResultArtifact`.

### 10.1 Define `ResultArtifact`

```python
@dataclass(frozen=True)
class ResultArtifact:
    name: str
    path: Path
    kind: str
    schema: type[BaseModel] | dict[str, object] | None = None
    source_path: Path | None = None
    promoted: bool = False
    required: bool = False
    qualified_name: str | None = None

    def exists(self) -> bool:
        return self.path.exists()

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()

    def read_text(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def read_json(self) -> object:
        return json.loads(self.read_text())

    def read_model(self) -> BaseModel:
        if self.schema is None:
            raise TypeError("artifact has no schema")
        if not isinstance(self.schema, type) or not issubclass(self.schema, BaseModel):
            raise TypeError("read_model only supports Pydantic BaseModel schemas")
        return self.schema.model_validate(self.read_json())

    def materialize(self, destination: str | Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.read_bytes())
        return destination
```

### 10.2 Update `ArtifactMap`

Change:

```python
class ArtifactMap(Mapping[str, ArtifactHandle])
```

to:

```python
class ArtifactMap(Mapping[str, ResultArtifact])
```

Methods:

```python
def __getitem__(self, key: str) -> ResultArtifact: ...
def __getattr__(self, name: str) -> ResultArtifact: ...
def require(self, name: str) -> ResultArtifact: ...
```

### 10.3 Update `WorkflowResult.artifact(...)`

Change return type:

```python
def artifact(self, name: str) -> ResultArtifact:
    return self.artifacts.require(name)
```

## 11. Retention info

Add:

```python
@dataclass(frozen=True)
class RetentionInfo:
    policy: RetentionPolicy
    task_scratch_retained: bool
    task_scratch_deleted: bool
    promoted_artifacts: tuple[str, ...]
    retained_task_dir: Path | None
```

Update `WorkflowResult`:

```python
retention: RetentionInfo | None
```

Rules:

* Internally, a pre-retention result may have `retention=None`.
* Any returned public result must have non-`None` retention.
* Any partial result attached to `InputRequired` or `TooManyPauses` must also have retention populated.

## 12. Declared write collection

Add:

```python
@dataclass(frozen=True)
class DeclaredWriteArtifact:
    name: str
    path: Path
    kind: str
    schema: type[BaseModel] | dict[str, object] | None
    required: bool
    qualified_name: str | None
```

Add:

```python
def _collect_declared_write_artifacts(
    execution: RunExecution,
    *,
    message: str | None,
) -> dict[str, DeclaredWriteArtifact]:
    ...
```

Rules:

* Use `execution.compiled.artifact_items(authoritative=False)`.
* Resolve each compiled artifact template against a runtime `Context` equivalent to the completed run.
* Preserve:

  * artifact name,
  * path,
  * kind,
  * schema,
  * required,
  * qualified name.
* Do not include:

  * events file,
  * trace file,
  * checkpoint file,
  * request file,
  * raw provider outputs,
  * undeclared files in artifact directories.

### 12.1 Context for artifact resolution

The context must include:

* `root`
* `task_id`
* `run_id`
* `workflow_name`
* `task_folder`
* `workflow_folder`
* `run_folder`
* `package_folder`
* `request_file`
* `task_request_file`
* final state
* params
* workflow params
* message
* typed workflow input
* session store

Use existing runtime resolution helpers where possible.

## 13. Promotion of task-local declared writes

Add:

```python
def _promote_declared_write(
    *,
    artifact: DeclaredWriteArtifact,
    root: Path,
    task_id: str,
    task_dir: Path,
    policy: RetentionPolicy,
) -> Path:
    ...
```

Rules:

* Source must be inside `task_dir`.
* Destination must be outside `task_dir`.
* Default destination base:

```text
<root>/.autoloop/outputs/sdk/<task-id>/
```

* If `policy.promoted_writes_dir` is not `None`, use that as base.
* Preserve file extension.
* Use binary copy.
* Prevent path traversal.
* Create parent directories.
* Directory artifacts:

  * reject in MVP with `SDKExecutionError`, or
  * recursively copy only if implemented safely.
* If destination exists:

  * overwrite only if destination is inside this task’s promotion directory;
  * otherwise add a unique suffix.

## 14. Apply retention

Add:

```python
def _apply_retention(
    *,
    execution: RunExecution,
    result: WorkflowResult,
    policy: RetentionPolicy,
    message: str | None,
    too_many_pauses: bool = False,
) -> WorkflowResult:
    ...
```

Algorithm:

1. Resolve:

   * `task_dir`
   * `task_id`
   * `tasks_root`
   * `root`
2. If `policy.mode == "keep_all"`:

   * build retained artifact map from declared writes;
   * do not delete task dir;
   * return result with `RetentionInfo(task_scratch_retained=True)`.
3. If `result.status == "failed"` and `policy.keep_on_failure`:

   * keep task dir.
4. If `result.status == "awaiting_input"` and `policy.keep_on_input_required`:

   * keep task dir.
5. If `too_many_pauses` and `policy.keep_on_too_many_pauses`:

   * keep task dir.
6. Collect declared writes.
7. For each declared write:

   * if missing:

     * include a `ResultArtifact` pointing to intended path if useful for diagnostics;
     * do not fail retention solely because an optional declared artifact is missing.
   * if outside task dir:

     * keep original path.
   * if inside task dir:

     * if `policy.keep_declared_writes=False`, omit it.
     * else if `policy.promote_task_writes=True`, promote it and point to promoted path.
     * else raise `SDKExecutionError`.
8. If `policy.mode in {"delete_task_scratch", "delete_all_sdk_managed"}`:

   * call `_safe_delete_sdk_task_dir(...)`.
9. Return a copy of `WorkflowResult` with:

   * retained `ArtifactMap`
   * populated `RetentionInfo`

## 15. Retention behavior on exceptions

### 15.1 Runtime exception before `WorkflowResult`

If `execute_workflow_package(...)` raises before a result can be built:

* do not delete task dir by default;
* ensure sentinel exists if task dir was created;
* wrap in `SDKExecutionError` only if adding SDK context is helpful;
* preserve original error as `.original_error`;
* include task dir on the exception if practical.

Optional:

```python
class SDKExecutionError(AutoloopSDKError):
    task_dir: Path | None = None
```

### 15.2 `InputRequired`

When the run pauses and `on_input is None`:

* build partial `WorkflowResult`;
* apply retention with status `awaiting_input`;
* raise:

```python
InputRequired(request=request, partial=retained_partial)
```

Default policy keeps task scratch.

### 15.3 `TooManyPauses`

When pause loop exceeds `max_pauses`:

* build retained partial result with `too_many_pauses=True`;
* raise:

```python
TooManyPauses(max_pauses=max_pauses, partial=retained_partial)
```

Default policy keeps task scratch.

### 15.4 Handler serialization/resume validation error

If input handler response cannot serialize or runtime rejects resumed input:

* keep scratch by default;
* raise `InputResponseValidationError`;
* preserve original error;
* attach request and response as currently implemented.

## 16. Thread retention through `Autoloop.run`

Update `run(...)` signature:

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
    retention: RetentionPolicy | None = None,
) -> WorkflowResult:
    ...
```

Implementation requirements:

* Determine effective retention before generating task id.
* Generate task id.
* Resolve task workspace.
* Write sentinel.
* Execute.
* Convert execution to draft `WorkflowResult`.
* Apply retention before returning final result or raising partial-result exceptions.

## 17. Step helper routing model

Do not mutate step instances with routes if constructors do not support route maps.

Use canonical approach:

* helper constructs a concrete `Step`;
* helper passes `routes` into `client.step(...)`;
* `client.step(...)` synthetic workflow builder sets transitions for that step.

Update `client.step(...)` signature:

```python
def step(
    self,
    step_def: Step,
    message: str | None = None,
    typed_input: BaseModel | None = None,
    /,
    *,
    params: BaseModel | Mapping[str, Any] | None = None,
    routes: Mapping[str, Any] | None = None,
    on_input: InputHandler | None = None,
    max_pauses: int = 8,
    max_steps: int | None = None,
    provider_questions: bool | None = None,
    retention: RetentionPolicy | None = None,
) -> StepResult:
    ...
```

## 18. Correct synthetic workflow routes

Synthetic route builder must follow these rules.

### 18.1 If `routes` is provided

* Use exactly `routes`.
* Preserve:

  * `SELF`
  * `FINISH`
  * `AWAIT_INPUT`
  * `FAIL`
  * `Route(...)`
  * concrete step targets if any are valid
* Do not rewrite all non-question routes to `FINISH`.

### 18.2 If `routes is None`

Defaults:

* `PromptStep`:

```python
{"done": FINISH}
```

* `PythonStep`:

```python
{"done": FINISH}
```

* `ChildWorkflowStep`:

```python
{"done": FINISH}
```

* `ProduceVerifyStep`:

```python
{
    "accepted": FINISH,
    "needs_rework": SELF,
}
```

### 18.3 Branch groups

* Reject `BranchGroupStep` in SDK MVP before route generation.

## 19. `Autoloop.step(...)`

Rules:

* Canonical accepted input is concrete `Step`.
* Backward compatibility with simple `_NamedDeclaration` may remain, but docs should not center it.
* Reject:

  * `BranchGroupStep`
  * scoped/worklist steps
  * child workflow steps with unresolved workflow refs
  * invalid/malformed steps
* If `typed_input` is provided:

  * synthetic workflow gets `Input = type(typed_input)`.
* Synthetic workflow should:

  * have a unique class name;
  * have `name = "sdk_step_<step-name>"` or path-safe equivalent;
  * contain exactly one step;
  * set `entry = step_def` or `entry = step_def.name` according to what discovery accepts;
  * set transitions according to section 18.
* Execute via `self.run(...)`.
* Pass `retention=` through.

## 20. `StepResult`

Current `StepResult.value = workflow_result.output` is misleading.

Revise:

```python
@dataclass(frozen=True, slots=True)
class StepResult:
    ok: bool
    status: Literal["completed", "failed", "awaiting_input"]
    route: str | None
    value: Any | None
    state: BaseModel
    artifacts: ArtifactMap
    workflow_result: WorkflowResult
```

Rules:

* `ok = workflow_result.ok`
* `status = workflow_result.status`
* `state = workflow_result.state`
* `artifacts = workflow_result.artifacts`
* `workflow_result = workflow_result`
* `route`:

  * prefer `workflow_result.last_event.tag` if present;
  * else use `workflow_result.debug`/transition data if available;
  * else `None`.
* `value = None` in MVP unless a truthful capture mechanism is implemented.
* Do not assign `workflow_result.output` to `value`.

## 21. `Autoloop.prompt_step(...)`

Add:

```python
def prompt_step(
    self,
    prompt: str | Prompt,
    message: str | None = None,
    typed_input: BaseModel | None = None,
    /,
    *,
    name: str = "prompt",
    writes: Mapping[str, Artifact] | None = None,
    reads: Sequence[Artifact | str | Path] = (),
    requires: Sequence[Artifact | str | Path] = (),
    routes: Mapping[str, Any] | None = None,
    session: Session | None = None,
    retry: int | ProviderRetryPolicy | None = None,
    on_input: InputHandler | None = None,
    max_pauses: int = 8,
    max_steps: int | None = None,
    provider_questions: bool | None = None,
    retention: RetentionPolicy | None = None,
) -> StepResult:
    ...
```

Implementation:

* Convert `str` prompt to `Prompt.inline(prompt)`.
* Normalize retry to `ProviderRetryPolicy` if needed.
* Construct `PromptStep`.
* Delegate:

```python
return self.step(
    step_def,
    message,
    typed_input,
    routes=routes,
    on_input=on_input,
    max_pauses=max_pauses,
    max_steps=max_steps,
    provider_questions=provider_questions,
    retention=retention,
)
```

## 22. `Autoloop.produce_verify_step(...)`

Add:

```python
def produce_verify_step(
    self,
    *,
    producer: str | Prompt,
    verifier: str | Prompt,
    message: str | None = None,
    typed_input: BaseModel | None = None,
    name: str = "produce_verify",
    writes: Mapping[str, Artifact] | None = None,
    verifier_writes: Mapping[str, Artifact] | None = None,
    reads: Sequence[Artifact | str | Path] = (),
    requires: Sequence[Artifact | str | Path] = (),
    verifier_requires: Sequence[Artifact | str | Path] = (),
    routes: Mapping[str, Any] | None = None,
    session: Session | None = None,
    verifier_session: Session | None = None,
    retry: int | ProviderRetryPolicy | None = None,
    on_input: InputHandler | None = None,
    max_pauses: int = 8,
    max_steps: int | None = None,
    provider_questions: bool | None = None,
    retention: RetentionPolicy | None = None,
) -> StepResult:
    ...
```

Implementation:

* Convert string prompts to `Prompt.inline(...)`.
* Construct `ProduceVerifyStep`.
* If `routes is None`, `client.step(...)` applies default produce/verify routes.
* Delegate to `client.step(...)`.

## 23. `Autoloop.python_step(...)`

Add:

```python
def python_step(
    self,
    handler: Callable[..., Any],
    message: str | None = None,
    typed_input: BaseModel | None = None,
    /,
    *,
    name: str = "python",
    writes: Mapping[str, Artifact] | None = None,
    reads: Sequence[Artifact | str | Path] = (),
    requires: Sequence[Artifact | str | Path] = (),
    routes: Mapping[str, Any] | None = None,
    on_input: InputHandler | None = None,
    max_pauses: int = 8,
    max_steps: int | None = None,
    retention: RetentionPolicy | None = None,
) -> StepResult:
    ...
```

Implementation:

* Construct `PythonStep`.
* Delegate to `client.step(...)`.
* Existing compiler validates handler arity.

## 24. `Autoloop.workflow_step(...)`

Avoid ambiguous message handling.

Add:

```python
def workflow_step(
    self,
    workflow: type[Workflow] | str,
    message: str | None = None,
    typed_input: BaseModel | None = None,
    /,
    *,
    child_message: str | None = None,
    name: str = "workflow",
    params: BaseModel | Mapping[str, Any] | None = None,
    writes: Mapping[str, Artifact] | None = None,
    reads: Sequence[Artifact | str | Path] = (),
    requires: Sequence[Artifact | str | Path] = (),
    routes: Mapping[str, Any] | None = None,
    on_input: InputHandler | None = None,
    max_pauses: int = 8,
    max_steps: int | None = None,
    provider_questions: bool | None = None,
    retention: RetentionPolicy | None = None,
) -> StepResult:
    ...
```

Rules:

* `message` is the outer one-step SDK message.
* `child_message` is the message passed to the child workflow step.
* If `child_message is None`, use `message`.
* Construct `ChildWorkflowStep` with:

  * `message=child_message or message`
  * `input=typed_input`
  * `params=params`
* Delegate to `client.step(...)`.

## 25. Cleanup utility

Add method:

```python
def cleanup(
    self,
    *,
    older_than: timedelta | None = None,
    include_failed: bool = False,
    dry_run: bool = False,
) -> CleanupResult:
    ...
```

Add:

```python
@dataclass(frozen=True)
class CleanupResult:
    deleted: tuple[Path, ...]
    skipped: tuple[Path, ...]
    errors: Mapping[Path, str]
    dry_run: bool
```

Behavior:

* Scan only `.autoloop/tasks/*` under the configured state root.
* Consider only directories with valid SDK sentinel.
* If `older_than` is provided:

  * compare against sentinel `created_at` or directory mtime.
* If `include_failed=False`:

  * skip directories that appear to contain failed/awaiting-input checkpoints or failure metadata.
  * Exact detection can be conservative; when uncertain, skip.
* `dry_run=True` returns candidates without deletion.
* Use `_safe_delete_sdk_task_dir(...)`.

## 26. Standalone `llm` / `classify`

* Do not add retention to `llm` or `classify` in MVP.
* Document that `RetentionPolicy` applies only to workflow/step task directories.
* Future work may add operation replay cleanup.

## 27. Internal helper summary

Add or revise these helpers in `autoloop/sdk.py`:

```python
_write_sdk_task_sentinel(...)
_safe_delete_sdk_task_dir(...)
_collect_declared_write_artifacts(...)
_promote_declared_write(...)
_apply_retention(...)
_result_artifact_map_from_declared_writes(...)
_is_inside_path(...)
_sdk_tasks_root(...)
_normalize_retry_policy(...)
_normalize_prompt(...)
_default_routes_for_step(...)
_build_synthetic_step_workflow(...)
```

## 28. Acceptance tests: public exports

* `from autoloop import Step`
* `from autoloop import PromptStep`
* `from autoloop import ProduceVerifyStep`
* `from autoloop import PythonStep`
* `from autoloop import ChildWorkflowStep`
* `from autoloop import ResultArtifact`
* `from autoloop import RetentionPolicy`
* `from autoloop import RetentionInfo`
* `from autoloop import CleanupResult`

all succeed.

## 29. Acceptance tests: prompt rendering

* `client.prompt_step("Echo {input.message}", "hello", writes=...)` sends prompt containing `hello`.
* `client.prompt_step("Echo {ctx.message}", "hello", writes=...)` sends prompt containing `hello`.
* `Workflow.Input(customer="Acme")` renders `{input.customer}`.
* Unknown `{input.customer}` without such typed input fails clearly.

## 30. Acceptance tests: step helpers

* `client.prompt_step(...)` constructs and runs a `PromptStep`.
* `client.produce_verify_step(...)` constructs and runs a `ProduceVerifyStep`.
* `client.python_step(...)` constructs and runs a `PythonStep`.
* `client.workflow_step(...)` constructs and runs a `ChildWorkflowStep`.
* Helper-created writes appear in `StepResult.artifacts`.
* Helper retention override works.
* `client.step(BranchGroupStep(...))` is rejected in MVP.
* Scoped/worklist step is rejected in MVP.

## 31. Acceptance tests: routes

* `PromptStep` default route is `done -> FINISH`.
* `PythonStep` default route is `done -> FINISH`.
* `ChildWorkflowStep` default route is `done -> FINISH`.
* `ProduceVerifyStep` default routes are:

  * `accepted -> FINISH`
  * `needs_rework -> SELF`
* Explicit `routes=` passed to helper is preserved.
* Explicit `SELF` target is not rewritten to `FINISH`.

## 32. Acceptance tests: retained artifacts

* `ResultArtifact.read_text()` works after task scratch deletion.
* `ResultArtifact.read_json()` works.
* `ResultArtifact.read_model()` works for Pydantic JSON artifacts.
* `ArtifactMap` maps names to `ResultArtifact`, not raw `ArtifactHandle`.
* Artifact schema metadata is preserved.

## 33. Acceptance tests: retention

* Successful SDK run deletes `.autoloop/tasks/<sdk-task-id>`.
* Successful SDK step deletes `.autoloop/tasks/<sdk-task-id>`.
* Failed SDK run keeps task scratch by default.
* Unhandled pause keeps task scratch by default.
* Too many pauses keeps task scratch by default.
* Declared write outside task dir remains in place.
* Declared write inside task dir is promoted before deletion.
* Result artifact path points to promoted file.
* Undeclared file inside task dir is deleted.
* Undeclared workspace file outside task dir is kept.
* `RetentionPolicy.keep_all()` keeps task dir on success.
* `RetentionPolicy.ephemeral()` deletes scratch and omits task-local declared writes when `keep_declared_writes=False`.

## 34. Acceptance tests: safe cleanup

* Deletion refuses non-`sdk-` task id.
* Deletion refuses missing sentinel.
* Deletion refuses sentinel with wrong schema.
* Deletion refuses sentinel with mismatched task id.
* Deletion refuses path outside `.autoloop/tasks`.
* `client.cleanup(dry_run=True)` deletes nothing.
* `client.cleanup(...)` deletes only valid SDK sentinel-marked task directories.

## 35. Implementation order

1. Add missing imports in `sdk.py`.
2. Add public exports in `autoloop/__init__.py`.
3. Add `ResultArtifact`, `RetentionPolicy`, `RetentionInfo`, `CleanupResult`.
4. Change `ArtifactMap` to map `str -> ResultArtifact`.
5. Fix prompt rendering roots to include `"input"`.
6. Add sentinel creation.
7. Add safe delete guard.
8. Add declared write collection.
9. Add promotion logic.
10. Add `_apply_retention(...)`.
11. Thread `retention=` through `run` and `step`.
12. Fix exception paths so partial results apply retention before raising.
13. Fix synthetic route defaults, especially `ProduceVerifyStep`.
14. Add helper methods:

    * `prompt_step`
    * `produce_verify_step`
    * `python_step`
    * `workflow_step`
15. Add `cleanup(...)`.
16. Add acceptance tests.
