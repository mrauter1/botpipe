# Botlane v3 second-pass greenfield architecture spec

This is a standalone implementation spec for the second pass over the current Botlane v3 codebase. The current implementation snapshot still contains old internal compiled structures such as `CompiledWorkflow`, `CompiledStep`, `CompiledRoute`, `CompiledArtifact`, `CompiledBranchGroupSpec`, `CompiledBranchStepSpec`, `_COMPILED_WORKFLOW_CACHE`, branch-runtime paths that depend on compiled steps and dict-shaped branch results, and duplicated placeholder parsing/rendering in `artifacts.py`. Those are the internal structures this pass must remove.  

---

## 0. Prime directive

* Botlane is a greenfield project.
* Preserve the public Botlane API and user-facing behavior.
* Do **not** preserve old internal compiled objects, adapter layers, transitional wrappers, or parallel runtime representations.
* The canonical internal architecture is:

```text
WorkflowDefinition
    -> WorkflowPlan
    -> Engine(WorkflowPlan, ExecutionFrame, ExecutionServices)
```

* The canonical runtime objects are:

```text
WorkflowPlan
StepPlan
StepHeader
StepSource
RouteContract
RouteDecision
RouteAction
ExecutionFrame
ExecutionServices
ProviderTurnPlan
BranchGroupPlan
BranchResult
BranchManifest
ReferenceGraph
ArtifactId
ArtifactSpec
```

* There must not be both an old compiled representation and a new plan representation.
* `WorkflowPlan` is the compiled workflow representation. There is no separate `CompiledWorkflow`.

---

## 1. Public API invariants

* Public users must still write:

```python
from botlane import Workflow, step, produce_verify_step, python_step, workflow_step
from botlane import parallel, fan_out, llm, classify
from botlane import Md, Json, Text, Raw
from botlane import Route, FINISH, AWAIT_INPUT, FAIL, SELF
from botlane import Policy, Botlane
```

* Public users must **not** be required to construct or understand:

```text
WorkflowPlan
StepPlan
StepHeader
StepSource
ProviderTurnPlan
RouteContract
RouteDecision
RouteAction
ExecutionFrame
ExecutionServices
RunPaths
RunIdentity
ArtifactId
ArtifactSpec
PlaceholderRef
ReferenceGraph
BranchGroupPlan
BranchResult
BranchManifest
WorkflowLocator
SingleStepPlan
```

### 1.1 Frozen root exports

* Do not change `botlane.__all__`.
* The public root must continue exporting exactly the current public surface, including:

```text
Workflow
step
produce_verify_step
python_step
validation_step
workflow_step
Step
PromptStep
ProduceVerifyStep
PythonStep
ChildWorkflowStep
parallel
fan_out
llm
classify
ControlRoutes
Effects
Prompt
Md
Json
Text
Raw
Route
Session
Continuity
FanIn
Worklist
WorklistEffect
StateVar
ValidationResult
Event
Outcome
RequestInput
Goto
Fail
FINISH
AWAIT_INPUT
FAIL
SELF
Policy
ProviderName
ModelEffort
ModelVerbosity
ReasoningSummary
SandboxMode
NetworkMode
PermissionMode
Botlane
WorkflowResult
StepResult
ArtifactMap
ResultArtifact
RetentionPolicy
RetentionInfo
CleanupResult
InputRequest
HandledInput
SDKDebugInfo
BotlaneSDKError
WorkflowInputError
WorkflowParameterError
InputRequired
TooManyPauses
InputResponseValidationError
SDKExecutionError
ConsoleInput
StaticInput
MappingInput
BestSuppositionInput
```

### 1.2 Frozen core exports

* Do not expose new internal plan/runtime objects through:

```text
botlane.__all__
botlane.core.__all__
botlane.core.branch_groups.__all__
```

* Do not export:

```text
WorkflowPlan
StepPlan
StepHeader
StepSource
ProviderTurnPlan
RouteContract
RouteDecision
RouteAction
ExecutionFrame
ExecutionServices
RunPaths
RunIdentity
ArtifactId
ArtifactSpec
PlaceholderRef
ReferenceGraph
BranchGroupPlan
BranchPlan
BranchResult
BranchManifest
WorkflowLocator
SingleStepPlan
```

### 1.3 Branch-group public/internal exports

* `botlane.core.branch_groups.__all__` may change **only** to remove old compiled branch exports.
* Remove these from `botlane.core.branch_groups.__all__` during the atomic compiler/runtime cutover:

```text
CompiledBranchGroupSpec
CompiledBranchStepSpec
```

* Do not add these to `botlane.core.branch_groups.__all__`:

```text
BranchGroupPlan
BranchPlan
BranchResult
BranchManifest
```

* Expected remaining branch-group exports should be limited to authoring/runtime helper names such as:

```text
BranchGroupDeclarationSpec
BranchMetadata
BranchSessionStoreView
BranchStepDeclarationSpec
FanIn
FanInHelperReference
FanInMetadata
StateCell
branch_group_paths
select_branch_group_outcome
```

* If `branch_group_paths` or `select_branch_group_outcome` are intentionally no longer exported, remove them only with explicit public-surface test updates.

---

## 2. Public SDK behavior

* Preserve:

```text
Botlane.run(...)
Botlane.step(...)
Botlane.prompt_step(...)
Botlane.produce_verify_step(...)
Botlane.python_step(...)
Botlane.workflow_step(...)
```

* Preserve current SDK behavior:

```text
Botlane.run(...) accepts workflow, message, policy, input, params, on_input, max_pauses, max_steps, provider_questions, options, and retention.
Botlane.step(...) accepts step_def, message, policy, input, params, routes, on_input, max_pauses, max_steps, provider_questions, and retention.
Botlane.step(...) applies invocation-local policy without mutating the supplied step object.
Botlane.step(...) returns StepResult(value=None, workflow_result=<full WorkflowResult>).
provider_questions defaults to on_input is not None when provider_questions is None.
on_input pause/resume behavior is unchanged.
retention and cleanup behavior are unchanged.
SDK exception classes and error wrapping are unchanged.
```

---

## 3. Public route authoring

* Users must still write:

```python
routes={"done": FINISH}
routes={"accepted": FINISH, "needs_rework": SELF}
routes={"question": AWAIT_INPUT}
routes={"failed": FAIL}
routes={"repair": Route(target=SELF, summary="retry once")}
```

* Public route sentinels remain:

```text
FINISH
AWAIT_INPUT
FAIL
SELF
Route(...)
```

* Do not make `RouteAction` public.
* Public route declarations lower into `RouteContract` at compile time.

---

## 4. Botlane identity and persistence

* Preserve:

```text
botlane
botlane_optimizer
.botlane
.botlane/tasks
.botlane-sdk-task.json
schema "botlane.sdk_task/v1"
generated_by "botlane.sdk"
schema "botlane.branch_results/v1"
```

* Do not introduce stale package names, stale state directories, stale schema IDs, or stale `generated_by` values.

---

## 5. Internal greenfield rule

* Remove old internal compatibility objects.
* Do not wrap them.
* Do not convert from them.
* Do not keep them for tests.
* Do not retain them as “compatibility” or “legacy” code.

### 5.1 Delete these internal classes

Remove these classes entirely:

```text
CompiledWorkflow
CompiledStep
CompiledRoute
CompiledArtifact
CompiledBranchGroupSpec
CompiledBranchStepSpec
```

Use these replacements:

```text
CompiledWorkflow        -> WorkflowPlan
CompiledStep            -> StepPlan variants
CompiledRoute           -> RouteContract
CompiledArtifact        -> ArtifactSpec
CompiledBranchGroupSpec -> BranchGroupPlan
CompiledBranchStepSpec  -> BranchPlan
```

* No class with a `Compiled*` name should remain in `botlane/core`.

### 5.2 Delete adapter layer

Remove:

```text
botlane/core/plan_adapters.py
```

Remove all references to:

```text
workflow_plan_from_compiled
compiled_workflow_from_plan
step_plan_from_compiled_step
compiled_step_from_step_plan
route_contract_from_compiled_route
compiled_route_from_route_contract
artifact_id_from_compiled_artifact
```

### 5.3 Delete split compile entrypoint

There should be exactly one compiler entrypoint:

```python
compile_workflow(workflow_cls) -> WorkflowPlan
```

Remove:

```text
compile_workflow_plan(...)
```

Do not keep one compiler returning old compiled objects and another returning plans.

---

## 6. Allowed declaration-layer objects

* Do not confuse authoring declarations with runtime compiled compatibility objects.
* These declaration-layer objects may remain:

```text
WorkflowDefinition
BranchGroupDeclarationSpec
BranchStepDeclarationSpec
FanInHelperReference
Artifact
Route
Step
PromptStep
ProduceVerifyStep
PythonStep
ChildWorkflowStep
BranchGroupStep
```

* Rules:

```text
Declaration-layer objects may be used during discovery, lowering, validation, and compilation.
Declaration-layer objects must not appear in Engine, StepDispatcher, BranchGroupRuntime, RouteFinalizer, provider execution, or runtime result objects.
Runtime execution must use WorkflowPlan, StepPlan, BranchGroupPlan, RouteContract, ArtifactId, and ArtifactSpec.
```

* `WorkflowPlan.workflow_cls` may be retained only for identity, diagnostics, source hashing, output building, or child workflow resolution.
* Runtime step execution must not inspect `workflow_cls` to recover authored `Step` declarations.
* `StepPlan` and `StepHeader` must not store authored `Step` objects.

---

## 7. Canonical internal modules

These modules should exist and own canonical internal types:

```text
botlane/core/identifiers.py
botlane/core/artifact_plan.py
botlane/core/run_paths.py
botlane/core/route_contracts.py
botlane/core/step_plans.py
botlane/core/workflow_plan.py
botlane/core/placeholders.py
botlane/core/reference_graph.py
botlane/core/execution_frame.py
botlane/core/execution_services.py
botlane/core/provider_policy_resolution.py
botlane/core/branch_groups/results.py
botlane/core/branch_groups/manifest.py
botlane/runtime/workflow_locator.py
```

Remove:

```text
botlane/core/plan_adapters.py
```

* Do not export these internal modules through package-level `__all__`.

---

## 8. Artifact model requirements

### 8.1 Replace `CompiledArtifact`

Create a canonical artifact metadata type:

```python
@dataclass(frozen=True, slots=True)
class ArtifactSpec:
    id: ArtifactId
    name: str
    template: str
    kind: ArtifactKind
    schema: type[BaseModel] | dict[str, object] | None
    required: bool
    owner_step: str | None
    workflow_level: bool
    producer_steps: tuple[str, ...]
```

* Preferred name: `ArtifactSpec`.
* Allowed alternative: `ArtifactPlan`.
* Use one name consistently.
* `ArtifactSpec` replaces `CompiledArtifact` everywhere except public runtime handles.

### 8.2 Public artifact handle behavior

* Preserve public `ArtifactHandle` behavior.
* If current public behavior has:

```python
ArtifactHandle.artifact: Artifact | None
```

then keep that public behavior.

* Internally, runtime artifact resolution should be:

```text
ArtifactId -> ArtifactSpec -> ArtifactHandle
```

* Do not expose `ArtifactSpec` publicly.

### 8.3 Artifact identity

Use:

```python
@dataclass(frozen=True, slots=True, order=True)
class ArtifactId:
    namespace: Literal["workflow", "step"]
    name: str
    step: str | None = None
```

Rules:

```text
Workflow-level artifact: ArtifactId(namespace="workflow", name=...)
Step-owned artifact: ArtifactId(namespace="step", step=<step name>, name=...)
Do not derive ArtifactId by splitting strings on ".".
Artifact names containing dots must be valid.
Artifact identity must come from artifact declarations and inventory records.
```

### 8.4 Artifact inventory

Compiler should produce:

```python
artifacts: dict[ArtifactId, ArtifactSpec]
public_artifacts: dict[str, ArtifactId]
artifacts_by_qualified_name: dict[str, ArtifactId]
```

Rules:

```text
Internal plans must not use raw artifact-name strings for reads/writes.
reads/requires/writes in StepIO must use ArtifactId, ExternalRead, or FanInRead.
```

Use:

```python
ReadRef = ArtifactId | ExternalRead | FanInRead
RequireRef = ArtifactId | FanInRead
WriteRef = ArtifactId
```

---

## 9. WorkflowPlan requirements

`compile_workflow(...)` must return:

```python
@dataclass(frozen=True, slots=True)
class WorkflowPlan:
    workflow_cls: type[Any]
    workflow_name: str
    state_cls: type[BaseModel]
    input_model: type[BaseModel] | None
    output_model: type[BaseModel] | None
    output_builder: Callable[[BaseModel, Context], Any] | None
    parameters_cls: type[BaseModel] | None

    entry_step_name: str

    sessions: dict[str, Session]
    default_session_name: str
    default_session_open: bool

    worklists: dict[str, Worklist[Any]]

    steps: dict[str, StepPlan]
    routes: dict[str, dict[str, RouteContract]]
    global_routes: dict[str, RouteContract]

    artifacts: dict[ArtifactId, ArtifactSpec]
    public_artifacts: dict[str, ArtifactId]
    artifacts_by_qualified_name: dict[str, ArtifactId]

    extensions: tuple[WorkflowExtension, ...]
    provider_policy: PolicyInput
    source_hash: str | None
    topology_hash: str
    reference_graph: ReferenceGraph
```

### 9.1 State creation

Replace `CompiledWorkflow.new_state()` with one of:

```python
@dataclass(frozen=True, slots=True)
class WorkflowPlan:
    ...
    def new_state(self) -> BaseModel:
        ...
```

or:

```python
def new_workflow_state(plan: WorkflowPlan) -> BaseModel:
    ...
```

Behavior:

```text
Instantiate plan.state_cls with no arguments.
If it cannot be instantiated, raise WorkflowCompilationError with equivalent clear wording:
"state model <qualname> requires an explicit initial state"
```

### 9.2 WorkflowPlan cache

Replace:

```text
_COMPILED_WORKFLOW_CACHE
```

with:

```text
_WORKFLOW_PLAN_CACHE
```

Rules:

```text
Cache stores WorkflowPlan only.
Cache key may remain the same if still valid.
No cache may store CompiledWorkflow or any removed compiled structure.
No _COMPILED_WORKFLOW_CACHE symbol remains.
```

### 9.3 Immutability

* `WorkflowPlan` is logically immutable.
* Compiler must copy incoming dictionaries.
* Runtime must not mutate these maps in place:

```text
WorkflowPlan.steps
WorkflowPlan.routes
WorkflowPlan.global_routes
WorkflowPlan.artifacts
WorkflowPlan.sessions
WorkflowPlan.worklists
```

* Runtime mutable state belongs in `ExecutionFrame`.

---

## 10. StepPlan requirements

Use typed step variants:

```python
StepPlan: TypeAlias = (
    PromptStepPlan
    | ProduceVerifyStepPlan
    | PythonStepPlan
    | ChildWorkflowStepPlan
    | BranchGroupStepPlan
)
```

### 10.1 StepSource

If source/debug metadata is needed, use `StepSource`, not an authored `Step` object:

```python
@dataclass(frozen=True, slots=True)
class StepSource:
    authoring_kind: str
    declaration_name: str | None = None
    source_module: str | None = None
    source_qualname: str | None = None
```

Rules:

```text
StepSource is metadata only.
StepSource must not contain Step, PromptStep, ProduceVerifyStep, PythonStep, ChildWorkflowStep, or BranchGroupStep objects.
StepSource must not be used to recover authored declarations at runtime.
```

### 10.2 StepHeader

`StepHeader` contains only common step metadata:

```python
@dataclass(frozen=True, slots=True)
class StepHeader:
    name: str
    kind: str
    source: StepSource | None
    session_name: str | None
    scope_name: str | None
    io: StepIO
    state: StepStateSpec
    hooks: StepHookSpec
    provider_policy: PolicyInput
```

Rules:

```text
StepHeader must not store original_step.
StepHeader must not store authored Step objects.
StepHeader must not store route contracts.
StepHeader must not store available_routes.
StepHeader must not store authored_routes.
StepHeader must not store runtime_control_routes.
StepHeader must not store provider_visible_routes_interactive.
StepHeader must not store provider_visible_routes_full_auto.
StepHeader must not store route_table.
```

* Derived route views must come from helper functions over `WorkflowPlan.routes`.

### 10.3 Step variants

```python
@dataclass(frozen=True, slots=True)
class PromptStepPlan:
    header: StepHeader
    turn: ProviderTurnPlan

@dataclass(frozen=True, slots=True)
class ProduceVerifyStepPlan:
    header: StepHeader
    producer: ProviderTurnPlan
    verifier: ProviderTurnPlan
    verifier_session_name: str | None

@dataclass(frozen=True, slots=True)
class PythonStepPlan:
    header: StepHeader
    handler: Callable[..., Any]

@dataclass(frozen=True, slots=True)
class ChildWorkflowStepPlan:
    header: StepHeader
    workflow: Any
    message: Any
    message_from: Any
    params: dict[str, Any]
    input: Any

@dataclass(frozen=True, slots=True)
class BranchGroupStepPlan:
    header: StepHeader
    branch_group: BranchGroupPlan
```

Rules:

```text
No StepPlan variant may contain _compiled_step.
No StepPlan variant may contain original_step.
No StepPlan variant may contain authored Step objects.
No StepPlan variant may contain old compiled objects.
No StepPlan variant may contain fields irrelevant to that variant.
PythonStepPlan must not carry provider prompt fields.
PromptStepPlan must have exactly one ProviderTurnPlan.
ProduceVerifyStepPlan must have exactly two ProviderTurnPlan objects.
BranchGroupStepPlan must carry BranchGroupPlan, not provider prompt fields except through nested branch/fan-in step plans.
```

---

## 11. RouteContract and RouteAction requirements

### 11.1 RouteContract

Compiler emits `RouteContract` directly:

```python
@dataclass(frozen=True, slots=True)
class RouteContract:
    source_step: str
    tag: str
    target: RouteTarget
    summary: str | None
    required_writes: RequiredWriteContract
    handoff: str | None
    on_taken: Callable[..., Any] | None
    provider: ProviderRoutePolicy
    payload: PayloadContract
    route_fields: RouteFieldsContract
    preset_kind: str
    inheritance_source: str
    disabled: bool
    is_runtime_control: bool
```

Rules:

```text
No CompiledRoute exists.
RouteContract is compiler output.
WorkflowPlan.routes owns step-local routes.
WorkflowPlan.global_routes owns global routes.
StepPlan does not own route tables.
Required writes are ArtifactId values.
```

### 11.2 RouteAction and RouteDecision

Runtime finalization returns:

```python
@dataclass(frozen=True, slots=True)
class RouteDecision:
    final_route: str | None
    contract: RouteContract | None
    action: RouteAction
    runtime_control: str | None = None
    pending_handoffs: tuple[PendingHandoff, ...] = ()
    provider_attributable: bool = False
    source_hook: str | None = None
    source_phase: str | None = None
```

`RouteAction` is:

```text
Continue | Finish | AwaitInput | FailAction
```

Rules:

```text
RouteFinalizer.finalize(...) returns RouteDecision.
Engine consumes RouteAction.
Engine does not compare terminal strings as runtime control flow.
Public route sentinels lower into RouteContract at compile time.
```

### 11.3 Remove old route-finalization wrappers

Remove or replace:

```text
RouteFinalizationResult
_DirectRuntimeControl
```

* `StepExecutionResult` may remain only as the canonical output of `StepDispatcher`.

Allowed `StepExecutionResult` fields:

```text
state
event
outcome
route_decision
action
destination
pending_input
producer_raw_output
verifier_raw_output
provider_usage
```

Forbidden `StepExecutionResult` fields:

```text
finalization
route_finalization
direct_control
CompiledStep
CompiledRoute
CompiledWorkflow
```

* `StepFinalizationRequest` may remain only if it references:

```text
StepPlan
RouteContract
ExecutionFrame
ResolvedArtifacts
```

* `StepFinalizationRequest` must not reference `CompiledStep`.

---

## 12. Branch-group requirements

### 12.1 BranchGroupPlan

Runtime branch execution uses:

```python
@dataclass(frozen=True, slots=True)
class BranchPlan:
    name: str
    index: int
    input: Any
    step: StepPlan

@dataclass(frozen=True, slots=True)
class BranchGroupPlan:
    name: str
    kind: Literal["parallel", "fan_out"]
    branches: tuple[BranchPlan, ...]
    concurrency: int | None
    settle: str
    success_routes: tuple[str, ...]
    outcome: str | Callable[..., Any] | None
    fan_in_step: StepPlan | None
    composite_route_tags: tuple[str, ...]
    default_chain_route: str
    rework_chain_route: str | None = None
```

Rules:

```text
No CompiledBranchGroupSpec exists.
No CompiledBranchStepSpec exists.
BranchGroupDeclarationSpec remains declaration-layer only.
BranchGroupPlan is runtime-layer.
```

### 12.2 BranchResult

Branch runtime methods must return `BranchResult`, not dictionaries.

Required signatures:

```python
BranchGroupRuntime._run_branches(...) -> dict[int, BranchResult]
BranchGroupRuntime._execute_branch(...) -> BranchResult
BranchGroupRuntime._branch_result_from_step_result(...) -> BranchResult
BranchGroupRuntime._failed_branch_result(...) -> BranchResult
_cancelled_branch_result(...) -> BranchResult
_unexpected_branch_failure_result(...) -> BranchResult
_skipped_branch_result(...) -> BranchResult
```

`_emit_branch_result_event(...)` accepts:

```python
result: BranchResult
```

not:

```python
result: Mapping[str, Any]
```

### 12.3 BranchManifest

Add canonical manifest value:

```python
@dataclass(frozen=True, slots=True)
class BranchManifest:
    schema: Literal["botlane.branch_results/v1"]
    kind: str
    name: str
    started_at: str
    finished_at: str
    duration_ms: int
    concurrency: int | None
    settle: str
    success_routes: tuple[str, ...]
    branches: tuple[BranchResult, ...]

    def to_dict(self) -> dict[str, Any]:
        ...
```

Rules:

```text
build_branch_manifest(...) returns BranchManifest.
write_branch_group_evidence(...) serializes BranchManifest.to_dict().
Only BranchManifest.to_dict() and BranchResult.to_manifest_dict() serialize branch evidence.
render_branch_group_context(...) may accept BranchManifest or serialized manifest dict only at final rendering boundary.
select_branch_group_outcome(...) should accept BranchManifest after branch cutover.
```

### 12.4 Branch manifest schema

Schema must remain:

```text
botlane.branch_results/v1
```

---

## 13. ExecutionFrame and Context requirements

### 13.1 ExecutionFrame is authoritative

`ExecutionFrame` is the only mutable runtime backing store.

Remove:

```text
WeakKeyDictionary context sidecar
legacy private-field mirroring
context_runtime mutating old private fields
```

`Context` is a public facade over `ExecutionFrame`.

### 13.2 Context public API stays stable

Public properties and methods remain unchanged:

```text
ctx.state
ctx.params
ctx.workflow_params
ctx.request
ctx.request_file
ctx.message
ctx.input
ctx.input_fields
ctx.artifacts
ctx.values
ctx.branch
ctx.fan_in
ctx.route
ctx.outcome
ctx.event
ctx.run
ctx.workflow
ctx.meta
ctx.history
ctx.step_state
ctx.item_state
ctx.step_item_state
ctx.worklists
ctx.worklist(...)
ctx.current_worklist
ctx.ensure_selection(...)
ctx.selection(...)
ctx.current(...)
ctx.item
ctx.open_session(...)
ctx.get_session(...)
ctx.reset_global_session()
ctx.set_global_session(...)
ctx.read(...)
ctx.write(...)
ctx.read_json(...)
ctx.write_json(...)
ctx.invoke_workflow(...)
```

* Each property should read from `ExecutionFrame` or a narrow service.

### 13.3 Child contexts

Branch and fan-in context creation must use:

```python
frame.child_for_branch(...)
frame.child_for_fan_in(...)
```

Do not manually clone private `Context` fields.

---

## 14. ExecutionServices requirements

Collaborators must not hold `Engine`.

Collaborators must depend on narrow services:

```text
ArtifactService
RouteService
HookService
SessionService
CheckpointService
EventService
ProviderService
OperationService
ChildWorkflowService
StateService
```

Minimum boundaries:

```text
ArtifactService:
  - resolve artifacts
  - collect artifact observations
  - validate required writes

RouteService:
  - retrieve RouteContract
  - finalize RouteDecision
  - derive provider-visible route tags

EventService:
  - emit runtime events

StateService:
  - create/update step state
  - create/update item state
  - track visits

ProviderService:
  - execute ProviderTurnPlan through provider rendering/transport

SessionService:
  - open/get/upsert sessions

ChildWorkflowService:
  - invoke child workflows

OperationService:
  - run llm/classify operations if operations are migrated
```

Rules:

```text
No service method may accept Engine.
No service may call Engine private methods.
No collaborator may call Engine private methods.
ExecutionServices must not become a method dump.
```

---

## 15. Engine requirements

### 15.1 Engine consumes WorkflowPlan

`Engine` constructor and runtime path must consume:

```python
WorkflowPlan
```

not:

```text
CompiledWorkflow
```

### 15.2 Step dispatch

`StepDispatcher` dispatches by `StepPlan` variant:

```python
if isinstance(plan, PromptStepPlan):
    ...
elif isinstance(plan, ProduceVerifyStepPlan):
    ...
elif isinstance(plan, PythonStepPlan):
    ...
elif isinstance(plan, ChildWorkflowStepPlan):
    ...
elif isinstance(plan, BranchGroupStepPlan):
    ...
```

* Do not dispatch runtime semantics by `step.kind`.

### 15.3 Route loop

The workflow loop consumes:

```text
RouteAction
```

Runtime control branches on:

```text
Continue
Finish
AwaitInput
FailAction
```

not raw strings.

---

## 16. Placeholder and ReferenceGraph requirements

### 16.1 Single parser

`botlane/core/placeholders.py` owns all placeholder parsing and rendering.

Remove duplicate parser/rendering logic from `artifacts.py`.

The following old symbols must not remain in `artifacts.py`:

```text
_PLACEHOLDER_RE
PromptContextView
_resolve_placeholder
_resolve_ctx_placeholder
_resolve_input_placeholder
_resolve_item_placeholder
_resolve_worklist_placeholder
_resolve_runtime_path
_lookup_runtime_value
```

Allowed in `artifacts.py`:

```text
resolve_artifact_template(...)
render_runtime_template(...)
```

only as thin delegates to `placeholders.py`.

### 16.2 Placeholder surfaces

`validate_placeholder_ref(...)` must support all current placeholder surfaces:

```text
prompt
workflow_step_message
artifact_template
branch_step_prompt
fan_in_step_prompt
worklist_context
runtime_template
```

No partial “simple_prompt only” mode.

### 16.3 ReferenceGraph

Compiler builds and attaches:

```python
ReferenceGraph
```

to `WorkflowPlan`.

ReferenceGraph must contain at least:

```text
prompt_refs
artifact_template_refs
inferred_artifact_reads
step_output_refs
branch_refs
fan_in_refs
worklist_refs
```

Do not infer artifact reads by reparsing prompt strings at runtime.

---

## 17. ProviderTurnPlan requirements

### 17.1 Prompt and produce/verify

Provider-backed steps are driven by `ProviderTurnPlan`.

```text
PromptStepPlan.turn
ProduceVerifyStepPlan.producer
ProduceVerifyStepPlan.verifier
```

### 17.2 Provider transport boundary

Use existing provider boundary types:

```text
ProviderTurnContext
RenderedProviderTurn
ProviderTurnResult
```

Rules:

```text
ProviderTurnPlan feeds rendering/execution.
Transport receives RenderedProviderTurn.
Transport returns ProviderTurnResult.
Do not create a second provider result universe.
```

### 17.3 Operations

Keeping the existing operation runtime is allowed **only** if it is treated as its own canonical operation path, not as compatibility.

Rules:

```text
Existing operation runtime may remain if llm(...) and classify(...) still work.
Existing operation runtime must not depend on CompiledStep, CompiledWorkflow, or CompiledRoute after plan cutover.
Do not include "operation" in ProviderTurnKind unless operation execution is fully migrated.
```

Allowed before operation migration:

```python
ProviderTurnKind = Literal["llm", "producer", "verifier"]
```

If operation migration is included, add a complete typed operation plan and tests for:

```text
llm(...)
classify(...)
operation policy resolution
operation result recording
operation replay/checkpoint behavior
operation context values
```

---

## 18. SDK one-step execution

There must be exactly one one-step execution architecture.

Preferred:

```text
Botlane.step(...) builds SingleStepPlan and executes it through the same StepPlan dispatcher.
```

Allowed alternative:

```text
Botlane.step(...) builds a normal WorkflowPlan with one step using the same compiler path.
```

Forbidden:

```text
dynamic synthetic workflow class as a fallback plus SingleStepPlan
two parallel one-step execution paths
old internal compatibility fallback
```

If `SingleStepPlan` is used, it is canonical.

If `SingleStepPlan` is not used, remove it entirely.

---

## 19. Botlane identity requirements

Preserve:

```text
botlane
botlane_optimizer
.botlane
.botlane/tasks
.botlane-sdk-task.json
botlane.sdk_task/v1
botlane.sdk
botlane.branch_results/v1
```

Search:

```text
botlane/**/*.py
botlane_optimizer/**/*.py
tests/**/*.py
```

Fail on direct source occurrences of:

```text
from autoloop
import autoloop
autoloop.
autoloop_optimizer
.autoloop
.autoloop-sdk-task.json
autoloop.sdk_task/v1
autoloop.branch_results/v1
generated_by "autoloop.sdk"
```

Allow only split-string strictness tests that assert absence.

---

## 20. Tests required

Second pass is not complete without tests.

### 20.1 Public API tests

Add or update:

```text
tests/unit/test_public_surface.py
```

Assert:

```text
botlane.__all__ exact expected list
botlane.core.__all__ exact expected list
botlane.core.branch_groups.__all__ current export behavior in Phase 0
botlane.core.branch_groups.__all__ target behavior after Phase 2 removes compiled branch exports
no internal plan objects exported publicly
Botlane and BotlaneSDKError exported
deprecated public names not exported
```

### 20.2 Compiler/engine plan cutover tests

Add:

```text
tests/unit/test_workflow_plan_compiler.py
tests/contract/test_engine_workflow_plan_runtime.py
```

Assert:

```text
compile_workflow returns WorkflowPlan
WorkflowPlan has typed StepPlan variants
PromptStep compiles to PromptStepPlan
ProduceVerifyStep compiles to ProduceVerifyStepPlan
PythonStep compiles to PythonStepPlan
ChildWorkflowStep compiles to ChildWorkflowStepPlan
BranchGroupStep compiles to BranchGroupStepPlan
WorkflowPlan.routes contains RouteContract tables
WorkflowPlan.global_routes contains RouteContract tables
StepHeader does not duplicate route contracts
StepHeader has no original_step field
StepPlan/StepHeader do not store authored Step objects
WorkflowPlan artifacts are keyed by ArtifactId
WorkflowPlan artifacts are ArtifactSpec values
ReferenceGraph is present
WorkflowPlan.new_state or new_workflow_state works
_WORKFLOW_PLAN_CACHE stores WorkflowPlan
Engine executes WorkflowPlan
StepDispatcher dispatches by StepPlan variant
RouteFinalizer returns RouteDecision
Engine consumes RouteAction
```

Assert absence:

```text
CompiledWorkflow
CompiledStep
CompiledRoute
CompiledArtifact
CompiledBranchGroupSpec
CompiledBranchStepSpec
_COMPILED_WORKFLOW_CACHE
compile_workflow_plan
original_step on StepHeader
```

### 20.3 Route tests

Add:

```text
tests/unit/test_route_contracts.py
```

Cover:

```text
FINISH lowers to RouteTarget(kind="finish")
AWAIT_INPUT lowers to RouteTarget(kind="await_input")
FAIL lowers to RouteTarget(kind="fail")
SELF lowers to current step target
normal step target lowers to RouteTarget(kind="step")
disabled route lowers to RouteTarget(kind="disabled")
provider visibility preserved
payload schema preserved
route fields schema preserved
handoff preserved
on_taken preserved
required writes are ArtifactId values
RouteFinalizer returns RouteDecision
Engine consumes RouteAction
StepExecutionResult has route_decision, not finalization
```

### 20.4 Artifact tests

Add:

```text
tests/unit/test_artifact_ids.py
```

Cover:

```text
workflow ArtifactId valid
step ArtifactId valid
step ArtifactId requires step
workflow ArtifactId rejects step
artifact names containing dots work
no dot-splitting parser exists
artifact identity comes from declarations/inventory
ArtifactSpec replaces CompiledArtifact
ArtifactHandle public behavior unchanged
reads/requires/writes in StepIO use ArtifactId/FanInRead/ExternalRead
```

### 20.5 ExecutionFrame tests

Add:

```text
tests/unit/test_execution_frame_context.py
```

Cover:

```text
Context public properties read from ExecutionFrame
no WeakKeyDictionary context sidecar remains
explicit message=None differs from default message-from-request-file sentinel
branch child context uses child frame
fan-in child context uses child frame
worklist selection snapshots survive child frame creation
state cell sharing works
```

### 20.6 Branch runtime tests

Add:

```text
tests/contract/test_branch_result_runtime.py
```

Cover:

```text
BranchGroupRuntime returns BranchResult internally
BranchManifest serializes to schema "botlane.branch_results/v1"
build_branch_manifest returns BranchManifest
manifest JSON shape matches expected public evidence format
branch context markdown renders correctly
completed branch result
failed branch result
needs_input branch result
cancelled branch result
skipped branch result
fail_fast cancellation behavior
fan-in manifest metadata counts
select_branch_group_outcome accepts BranchManifest or typed branch access
```

### 20.7 Placeholder tests

Add:

```text
tests/unit/test_placeholder_refs.py
```

Cover:

```text
single parser extracts placeholders
prompt rendering
workflow-step message rendering
artifact template rendering
artifact template rejects ctx.*
safe ctx.* allowlist
input placeholders
params placeholders
state placeholders
worklist placeholders
item placeholders
branch placeholders only in branch context
fan_in placeholders only in fan-in context
unknown fields produce equivalent errors
ReferenceGraph inferred reads are correct
no duplicate runtime parser remains in artifacts.py
```

### 20.8 Provider turn tests

Add:

```text
tests/contract/test_provider_turn_plan.py
```

Cover:

```text
PromptStepPlan executes through ProviderTurnPlan
ProduceVerifyStepPlan producer executes through ProviderTurnPlan
ProduceVerifyStepPlan verifier executes through ProviderTurnPlan
RenderedProviderTurn still reaches transport
ProviderTurnResult still returned by transport
fake provider call records unchanged
retry behavior preserved
session persistence preserved
raw output persistence preserved
usage aggregation preserved
```

If operation turns are not migrated:

```text
ProviderTurnKind does not include "operation".
Operation runtime does not depend on CompiledStep, CompiledWorkflow, or CompiledRoute.
```

If operation turns are migrated, add:

```text
tests/contract/test_operation_turn_plan.py
```

### 20.9 SDK tests

Add or update:

```text
tests/unit/test_sdk_facade.py
tests/contract/test_sdk_single_step_execution.py
```

Greenfield meaning:

```text
There is one canonical one-step execution architecture.
No fallback path.
```

Cover:

```text
Botlane.step PromptStep
Botlane.step ProduceVerifyStep
Botlane.step PythonStep
Botlane.step ChildWorkflowStep
simple operation declarations if supported
message
input model
params model
route overrides
provider_questions true/false/None
on_input pause/resume
retention
StepResult.value is None
WorkflowResult passthrough
error wrapping
```

### 20.10 Strictness tests

Add:

```text
tests/strictness/test_no_internal_compat_layers.py
tests/strictness/test_core_runtime_boundary.py
tests/strictness/test_botlane_identity.py
```

`test_no_internal_compat_layers.py` must scan:

```text
botlane/**/*.py
botlane_optimizer/**/*.py
```

Fail on:

```text
CompiledWorkflow
CompiledStep
CompiledRoute
CompiledArtifact
CompiledBranchGroupSpec
CompiledBranchStepSpec
plan_adapters
workflow_plan_from_compiled
compiled_workflow_from_plan
step_plan_from_compiled_step
compiled_step_from_step_plan
route_contract_from_compiled
route_contract_from_compiled_route
compiled_route_from_route_contract
_COMPILED_WORKFLOW_CACHE
compile_workflow_plan
_compiled_step
_DirectRuntimeControl
RouteFinalizationResult
original_step
```

Allowlist only strictness-test strings that assert absence, preferably built with split strings.

`test_core_runtime_boundary.py` must be AST-aware and fail on core imports of runtime outside `TYPE_CHECKING`.

`test_botlane_identity.py` must assert:

```text
no stale package imports
no stale state directory strings
no stale schema IDs
botlane_optimizer imports from botlane
```

Strictness must allow:

```text
botlane.core.route_contracts.RouteContract
internal imports of botlane.core.route_contracts.RouteContract
```

Strictness must forbid:

```text
botlane.RouteContract
RouteContract in botlane.__all__
RouteContract in botlane.core.__all__
deprecated public route-contract aliases
```

---

## 21. Implementation order

### Phase 0: Public freeze

Before changing internals, add tests for:

```text
botlane.__all__
botlane.core.__all__
Botlane.run signature
Botlane.step signature
simple authoring examples
route sentinel authoring
.botlane persistence identity
botlane_optimizer import identity
```

For `botlane.core.branch_groups.__all__`:

```text
Add a Phase 0 test that documents current export behavior.
Prepare, but do not enable until Phase 2, the target assertion that CompiledBranchGroupSpec and CompiledBranchStepSpec are no longer exported.
```

### Phase 1: Canonical type definitions

Add or finish internal canonical types:

```text
ArtifactId
ArtifactSpec
RouteContract
RouteAction
RouteDecision
StepPlan
StepHeader
StepSource
ProviderTurnPlan
WorkflowPlan
ExecutionFrame
ExecutionServices
BranchResult
BranchManifest
ReferenceGraph
```

Do not enable hard no-`Compiled*` strictness yet.

### Phase 2: Atomic compiler + runtime cutover

This phase is one atomic cutover. Do not expect the suite to pass halfway through this phase. After this phase is complete, the compiler and runtime must both use the new architecture.

Rewrite `botlane/core/compiler.py` so:

```python
compile_workflow(...) -> WorkflowPlan
```

Directly build:

```text
WorkflowPlan
RouteContract
StepPlan
BranchGroupPlan
ArtifactId inventory
ArtifactSpec
ReferenceGraph
ProviderTurnPlan
```

Update all immediate consumers to consume `WorkflowPlan`, `StepPlan`, `RouteContract`, and typed runtime results:

```text
Engine
StepDispatcher
RouteFinalizer
HookRunner
BranchGroupRuntime
OperationRecorder
WorkflowInvoker
runtime runner
runtime loader
runtime static graph
SDK
```

Delete in this same phase:

```text
CompiledWorkflow
CompiledStep
CompiledRoute
CompiledArtifact
CompiledBranchGroupSpec
CompiledBranchStepSpec
_COMPILED_WORKFLOW_CACHE
compile_workflow_plan
plan_adapters.py
_compiled_step fields
original_step fields on StepHeader / StepPlan
```

Add:

```text
_WORKFLOW_PLAN_CACHE
```

This phase must also ensure:

```text
Engine executes WorkflowPlan.
StepDispatcher dispatches by StepPlan variant.
RouteFinalizer returns RouteDecision.
Engine consumes RouteAction.
BranchGroupRuntime consumes BranchGroupPlan.
Operation runtime, if kept, no longer depends on CompiledStep, CompiledWorkflow, or CompiledRoute.
StepPlan and StepHeader do not store authored Step objects.
botlane.core.branch_groups.__all__ removes CompiledBranchGroupSpec and CompiledBranchStepSpec.
The prepared branch_groups.__all__ target test is enabled.
```

### Phase 3: Context/frame cutover

Make `ExecutionFrame` authoritative.

Remove:

```text
WeakKeyDictionary context sidecar
mirrored private runtime state
context_runtime mutation of old private fields
```

Keep `Context` as public facade.

### Phase 4: Branch typed evidence cutover

Rewrite branch runtime to use:

```text
BranchGroupPlan
BranchResult
BranchManifest
```

Dict conversion only at:

```text
BranchResult.to_manifest_dict()
BranchManifest.to_dict()
JSON/write boundary
```

### Phase 5: Placeholder cutover

Move parser/rendering/validation into:

```text
botlane/core/placeholders.py
botlane/core/reference_graph.py
```

Remove duplicate parser/rendering code from:

```text
artifacts.py
discovery.py
branch_groups/validation.py where appropriate
runtime paths
```

### Phase 6: Provider turn cutover

Wire prompt and produce/verify execution through:

```text
ProviderTurnPlan
RenderedProviderTurn
ProviderTurnResult
```

Do not include operation turns unless fully implemented.

### Phase 7: One-step SDK cutover

Choose exactly one:

```text
SingleStepPlan canonical path
normal one-step WorkflowPlan canonical path
```

Remove any other one-step execution path.

### Phase 8: Strictness and cleanup

Enable strictness tests that fail on:

```text
Compiled*
plan_adapters
compile_workflow_plan
_COMPILED_WORKFLOW_CACHE
_compiled_step
_DirectRuntimeControl
RouteFinalizationResult
original_step
stale Botlane identity strings
```

Remove:

```text
old compatibility comments
adapter-only tests
compatibility aliases
old compiled references
stale package/schema/state identifiers
```

---

## 22. Explicit non-goals

Do not do these:

```text
Do not keep CompiledWorkflow.
Do not keep CompiledStep.
Do not keep CompiledRoute.
Do not keep CompiledArtifact.
Do not keep CompiledBranchGroupSpec.
Do not keep CompiledBranchStepSpec.
Do not keep plan_adapters.py.
Do not keep compile_workflow_plan.
Do not keep _COMPILED_WORKFLOW_CACHE.
Do not keep _compiled_step backrefs.
Do not keep original_step on StepHeader or StepPlan.
Do not keep authored Step objects inside StepPlan.
Do not keep _DirectRuntimeControl.
Do not keep RouteFinalizationResult as a compatibility wrapper.
Do not keep branch results as dicts inside runtime.
Do not keep duplicated placeholder parsers.
Do not keep route contracts on StepHeader.
Do not dispatch runtime behavior by step.kind.
Do not make RouteAction public.
Do not export internal plan types through botlane.__all__.
Do not create synthetic workflow fallback if SingleStepPlan is canonical.
Do not include "operation" in ProviderTurnKind unless operation execution is fully migrated and tested.
Do not preserve old internal APIs just because tests used them.
Do not let ExecutionServices become a renamed Engine.
Do not let services call Engine private methods.
Do not remove public Botlane authoring or SDK behavior.
```

---

## 23. Definition of done

The second pass is complete only when all are true:

```text
1. Full pytest suite passes.
2. botlane.__all__ is unchanged.
3. botlane.core.__all__ is unchanged.
4. botlane.core.branch_groups.__all__ removes old compiled branch exports and does not export internal plan/result objects.
5. compile_workflow(...) returns WorkflowPlan.
6. No CompiledWorkflow class exists.
7. No CompiledStep class exists.
8. No CompiledRoute class exists.
9. No CompiledArtifact class exists.
10. No CompiledBranchGroupSpec class exists.
11. No CompiledBranchStepSpec class exists.
12. No plan_adapters.py exists.
13. No compile_workflow_plan(...) exists.
14. No _COMPILED_WORKFLOW_CACHE symbol exists.
15. _WORKFLOW_PLAN_CACHE stores WorkflowPlan.
16. No StepPlan variant contains _compiled_step.
17. No StepPlan or StepHeader contains original_step.
18. No StepPlan or StepHeader stores authored Step objects.
19. StepHeader does not store route contracts or route view tuples.
20. WorkflowPlan owns route contracts.
21. WorkflowPlan owns ArtifactId-keyed ArtifactSpec inventory.
22. WorkflowPlan or a helper owns new_state behavior.
23. Engine executes WorkflowPlan.
24. StepDispatcher dispatches by StepPlan variant.
25. RouteFinalizer returns RouteDecision.
26. Engine consumes RouteAction.
27. No _DirectRuntimeControl exists.
28. No RouteFinalizationResult compatibility wrapper exists.
29. StepExecutionResult, if kept, contains route_decision/action fields and no finalization wrapper.
30. ExecutionFrame is authoritative runtime state.
31. Context has no WeakKeyDictionary sidecar.
32. BranchGroupRuntime uses BranchResult internally.
33. build_branch_manifest returns BranchManifest.
34. Only BranchManifest.to_dict() and BranchResult.to_manifest_dict() serialize branch evidence.
35. Branch manifest schema remains "botlane.branch_results/v1".
36. Placeholder parsing/rendering/validation is centralized in placeholders/reference graph modules.
37. artifacts.py does not contain _PLACEHOLDER_RE, PromptContextView, or _resolve_* placeholder functions.
38. ReferenceGraph is attached to WorkflowPlan.
39. Provider-backed prompt and produce/verify steps are driven by ProviderTurnPlan.
40. ProviderTurnPlan does not include operation unless operations are fully migrated and tested.
41. Operation runtime, if kept separately, does not depend on CompiledStep, CompiledWorkflow, or CompiledRoute.
42. No core module imports botlane.runtime outside TYPE_CHECKING.
43. No stale package/state/schema identifiers are introduced.
44. botlane_optimizer imports from botlane.
45. Botlane.run and Botlane.step public behavior is unchanged.
46. .botlane persistence identity is unchanged.
47. Internal RouteContract is allowed, but public RouteContract exports/aliases are forbidden.
```

---

## 24. Final handoff instruction

Give this instruction with the spec:

```text
This is a greenfield internal rewrite. Preserve only the public Botlane API and user-facing behavior.
Do not preserve internal compatibility objects. Remove adapter layers, old compiled dataclasses,
dict-shaped branch runtime internals, duplicated placeholder parsers, and partial typed wrappers.

Implement phase by phase. Phase 2 is an atomic compiler + runtime cutover and does not need to pass
mid-phase. After each complete phase, run its tests before continuing.
```
