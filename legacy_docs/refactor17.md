# Botlane internal architecture refactor spec

This is a standalone implementation spec for an agentic coding agent working on the current **Botlane** codebase. The target package shape is `botlane/core`, `botlane/runtime`, `botlane/sdk.py`, `botlane/simple.py`, `botlane/stdlib`, `botlane/extensions`, `botlane_optimizer`, and the `tests/` tree. The public root package exports `Botlane`, `BotlaneSDKError`, the simple authoring surface, route sentinels, policy objects, SDK results, and input handlers. 

---

# 0. Prime directive

Refactor Botlane’s internal architecture toward stronger runtime data structures while preserving all public SDK and simple authoring behavior.

This refactor is **internal-only**.

Public users must still write:

```python
from botlane import Workflow, step, produce_verify_step, python_step, workflow_step
from botlane import parallel, fan_out, llm, classify
from botlane import Md, Json, Text, Raw
from botlane import Route, FINISH, AWAIT_INPUT, FAIL, SELF
from botlane import Policy, Botlane
```

Public users must **not** be required to construct or understand:

```python
WorkflowPlan
StepPlan
StepHeader
ProviderTurnPlan
RouteContract
RouteDecision
RouteAction
ExecutionFrame
ExecutionServices
RunPaths
RunIdentity
ArtifactId
PlaceholderRef
ReferenceGraph
BranchResult
WorkflowLocator
SingleStepPlan
```

Those names are internal implementation details.

When in doubt, preserve current behavior and keep a compatibility adapter.

---

# 1. Hard target constraints

## 1.1 Work only on the current Botlane package

Use this package shape:

```text
botlane/core
botlane/runtime
botlane/sdk.py
botlane/simple.py
botlane/stdlib
botlane/extensions
botlane_optimizer
tests/unit
tests/runtime
tests/contract
tests/strictness
```

Do not introduce architecture, names, imports, schemas, state directories, or runtime behavior that are not grounded in the current Botlane package.

## 1.2 Public root API is frozen

Do not change `botlane.__all__`.

Do not add new internal architecture names to `botlane.__all__`.

Do not remove, rename, reorder, or replace existing root exports.

Keep the current public root surface stable, including:

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

## 1.3 Do not promote new internals through package `__init__` files

Do not add these new internal objects to `botlane.__init__`.

Also do not add them to `botlane.core.__all__` or `botlane.core.branch_groups.__all__` during this refactor unless a specific internal test requires it:

```text
WorkflowPlan
StepPlan
StepHeader
ProviderTurnPlan
RouteContract
RouteDecision
RouteAction
ExecutionFrame
ExecutionServices
RunPaths
RunIdentity
ArtifactId
PlaceholderRef
ReferenceGraph
BranchResult
BranchGroupPlan
WorkflowLocator
SingleStepPlan
```

These objects should be importable from their internal modules only.

Every new module containing these objects should include a docstring like:

```python
"""Internal workflow-plan value objects.

Not part of the public botlane authoring API.
"""
```

## 1.4 Simple authoring API is frozen

These patterns must continue to work:

```python
class W(Workflow):
    draft = step("Draft the report.", writes=[Md("report")])
```

```python
class W(Workflow):
    class State(BaseModel):
        status: str = "new"

    class Params(BaseModel):
        mode: str = "brief"

    draft = step("Draft in {params.mode} mode. Current status: {state.status}")
```

```python
class W(Workflow):
    review = produce_verify_step(
        producer_prompt="Draft.",
        verifier_prompt="Review.",
        writes=[Md("draft")],
        verifier_writes=[Md("review")],
    )
```

```python
class W(Workflow):
    branch = parallel(
        branches={
            "a": step("Do A with {branch.name}", session=Session.fresh()),
            "b": step("Do B with {branch.name}", session=Session.fresh()),
        }
    )
```

Preserve these conventions:

```text
simple.Workflow uses class State(BaseModel), not StateField.
simple.Workflow uses class Params(BaseModel), not Parameters.
State must be instantiable with no arguments.
Params must inherit from pydantic.BaseModel when present.
Descriptor-backed StateField and ParameterField remain invalid in simple workflows.
Step descriptor names remain deterministic through __set_name__ / class attribute binding.
Simple artifact helpers Md/Json/Text/Raw keep the same behavior.
```

Do not require simple users to pass explicit IDs, plans, route actions, runtime frames, or compiler objects.

## 1.5 SDK API is frozen

`Botlane.run(...)` must remain source-compatible.

`Botlane.step(...)` must remain source-compatible.

These helper methods must remain source-compatible:

```python
client.prompt_step(...)
client.produce_verify_step(...)
client.python_step(...)
client.workflow_step(...)
```

Preserve current SDK behavior:

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

`SingleStepPlan` is allowed only as an internal parity target. It must not replace the current synthetic one-step workflow path until exact equivalence is proven by tests.

## 1.6 Public route declarations are frozen

Users must still write:

```python
routes={"done": FINISH}
routes={"accepted": FINISH, "needs_rework": SELF}
routes={"question": AWAIT_INPUT}
routes={"failed": FAIL}
routes={"repair": Route(target=SELF, summary="retry once")}
```

Do not expose `RouteAction` as public authoring syntax.

Internally, route sentinels may compile to `RouteContract`, `RouteDecision`, and `RouteAction`.

Publicly, `FINISH`, `AWAIT_INPUT`, `FAIL`, `SELF`, and `Route(...)` remain the route vocabulary.

## 1.7 Context API is frozen

Public workflow code must continue to use `ctx`.

Do not rename public `Context`.

Do not introduce public `ContextView`.

The following public properties and methods must continue to behave as before:

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

`ExecutionFrame` may become the internal mutable backing store, but public `Context` remains the facade.

## 1.8 Public and semi-public dataclass compatibility

If adding fields to any public or semi-public dataclass, append fields at the end and provide defaults.

Do not reorder existing dataclass fields.

Do not make existing positional construction invalid.

This applies especially to:

```text
WorkflowResult
StepResult
ChildWorkflowResult
SDKDebugInfo
RetentionInfo
CleanupResult
InputRequest
HandledInput
```

## 1.9 Botlane persistence and schema identity are frozen

Preserve current Botlane state and schema identity.

Do not introduce non-Botlane package, state-dir, sentinel, schema, or `generated_by` values.

Preserve:

```text
.botlane
.botlane/tasks
.botlane-sdk-task.json
schema "botlane.sdk_task/v1"
generated_by "botlane.sdk"
schema "botlane.branch_results/v1"
```

Preserve safe deletion and retention ownership checks under `.botlane/tasks`.

---

# 2. Canonical internal vocabulary

Use this vocabulary consistently:

```text
WorkflowDefinition     Existing discovered workflow declaration model.
WorkflowPlan           Internal executable workflow plan.
StepPlan               Union of typed executable step variants.
StepHeader             Common step metadata.
ProviderTurnPlan       One provider call/turn plan.
RouteContract          Static route declaration/contract.
RouteDecision          Runtime finalized route result.
RouteAction            Runtime next action: continue, finish, await input, fail.
ExecutionFrame         Mutable runtime state.
ExecutionServices      Narrow injected service bundle.
RunIdentity            task_id, run_id, workflow_name, paths.
RunPaths               Canonical filesystem layout.
ArtifactId             Canonical internal artifact identity.
PlaceholderRef         Parsed placeholder expression.
ReferenceGraph         Compile-time placeholder/dependency graph.
BranchGroupPlan        Compiled branch-group plan.
BranchResult           Typed branch execution result.
WorkflowLocator        Workflow source/loading locator.
SingleStepPlan         Optional SDK one-step execution plan, parity-gated.
```

Avoid these names as headline objects:

```text
RuntimePlan            Use WorkflowPlan.
StepEnvelope           Use StepHeader.
BindingRef             Use PlaceholderRef.
ContextView            Keep Context public and internal.
ForkJoinPlan           Use BranchGroupPlan for the domain object.
SingleStepProgram      Use SingleStepPlan.
CaptureOnly            Use execution mode, not RouteAction.
ValidatedWorkflowIR    Validation is a phase, not a headline type.
```

---

# 3. Import-cycle safety

New value-object modules must be dependency-light.

Add:

```text
botlane/core/plan_adapters.py
```

All conversion between current compiled objects and new plan objects belongs in `plan_adapters.py`, not in value-object modules.

## 3.1 Runtime import rules

These modules must not import `botlane.core.compiler` at runtime:

```text
botlane/core/identifiers.py
botlane/core/route_contracts.py
botlane/core/step_plans.py
botlane/core/workflow_plan.py
botlane/core/execution_frame.py
```

These modules must not import `botlane.runtime`:

```text
all botlane/core/**/*.py modules
```

`botlane/runtime` may import `botlane/core`.

## 3.2 Adapter module ownership

Put these conversion helpers in:

```text
botlane/core/plan_adapters.py
```

Required adapter functions:

```python
artifact_id_from_compiled_artifact(...)
artifact_id_from_inventory_record(...)
artifact_id_for_reference(...)

route_contract_from_compiled_route(...)
compiled_route_from_route_contract(...)

step_plan_from_compiled_step(...)
compiled_step_from_step_plan(...)

workflow_plan_from_compiled(...)
compiled_workflow_from_plan(...)
```

Value modules should define dataclasses and small pure helpers only.

## 3.3 Lazy adapter imports from `compiler.py`

If `compile_workflow_plan(...)` is added to `compiler.py`, import `plan_adapters` lazily inside the function:

```python
def compile_workflow_plan(workflow_cls):
    compiled = compile_workflow(workflow_cls)
    from .plan_adapters import workflow_plan_from_compiled

    return workflow_plan_from_compiled(compiled)
```

Rules:

```text
compiler.py may import plan_adapters only inside functions, not at module import time.
plan_adapters.py may import CompiledWorkflow, CompiledStep, and CompiledRoute from compiler.py.
No value-object module may import compiler.py at runtime.
```

---

# 4. Type alias syntax

All union aliases must use `typing.TypeAlias`.

Valid:

```python
from typing import TypeAlias

RouteAction: TypeAlias = Continue | Finish | AwaitInput | FailAction

ReadRef: TypeAlias = ArtifactId | ExternalRead | FanInRead
RequireRef: TypeAlias = ArtifactId | FanInRead
WriteRef: TypeAlias = ArtifactId

StepPlan: TypeAlias = (
    PromptStepPlan
    | ProduceVerifyStepPlan
    | PythonStepPlan
    | ChildWorkflowStepPlan
    | BranchGroupStepPlan
)

WorkflowLocator: TypeAlias = (
    CatalogWorkflowLocator
    | PythonFileWorkflowLocator
    | PythonModuleWorkflowLocator
    | WorkflowDirectoryLocator
)
```

Do not omit the `TypeAlias` annotation for internal union aliases.

---

# 5. Module placement

Create these modules if they do not already exist and if no existing module is a better owner:

```text
botlane/core/identifiers.py
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
botlane/core/plan_adapters.py
botlane/runtime/workflow_locator.py
```

Rules:

```text
Do not create one giant plans.py module.
Do not put runtime implementation classes in botlane/core.
Do not import botlane.runtime from botlane.core.
Runtime may import core.
Core may define protocols implemented by runtime.
```

---

# 6. New internal data structures

## 6.1 `ArtifactId`

File:

```text
botlane/core/identifiers.py
```

Purpose:

```text
Replace ambiguous internal artifact strings with canonical artifact IDs.
Distinguish workflow-level artifacts from step-owned artifacts.
Avoid repeated short-name / qualified-name / owner-step interpretation in runtime code.
```

Definition:

```python
"""Internal artifact identity values.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True, order=True)
class ArtifactId:
    namespace: Literal["workflow", "step"]
    name: str
    step: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("ArtifactId.name must be non-empty")
        if self.namespace == "step":
            if not isinstance(self.step, str) or not self.step.strip():
                raise ValueError("step ArtifactId requires step")
        elif self.namespace == "workflow":
            if self.step is not None:
                raise ValueError("workflow ArtifactId must not include step")
        else:
            raise ValueError(f"unsupported ArtifactId namespace {self.namespace!r}")

    @property
    def qualified_name(self) -> str:
        return self.name if self.step is None else f"{self.step}.{self.name}"

    @property
    def display(self) -> str:
        return self.qualified_name
```

Do **not** implement artifact identity by naively splitting strings on `"."`.

Bad:

```python
def artifact_id_from_qualified_name(value: str) -> ArtifactId:
    step, name = value.split(".", 1)
    return ArtifactId("step", name=name, step=step)
```

Reason:

```text
Artifact names and filenames may contain dots.
The existing inventory resolver already owns ambiguity resolution.
```

Adapter functions belong in `botlane/core/plan_adapters.py`:

```python
def artifact_id_from_compiled_artifact(
    *,
    key: str,
    artifact: CompiledArtifact,
) -> ArtifactId:
    ...
```

```python
def artifact_id_from_inventory_record(
    *,
    key: str,
    record: ArtifactInventoryRecord,
) -> ArtifactId:
    ...
```

```python
def artifact_id_for_reference(
    reference: object,
    inventory: Mapping[str, ArtifactInventoryRecord],
    *,
    step_name: str | None = None,
    prefer_step_local: bool = False,
) -> ArtifactId:
    ...
```

Implementation rules:

```text
Use existing inventory resolution functions where possible.
Keep public artifact access unchanged.
Keep CompiledArtifact.qualified_name compatibility.
Keep ctx.artifacts.report and ctx.artifacts["report"] behavior unchanged.
Keep provider request artifact names unchanged until provider request compatibility tests are migrated.
```

---

## 6.2 `StepIO` read/write references

File:

```text
botlane/core/step_plans.py
```

Purpose:

```text
Use ArtifactId structurally, not decoratively.
Represent external reads and fan-in helper reads without pretending they are artifacts.
```

Definition:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from .identifiers import ArtifactId


@dataclass(frozen=True, slots=True)
class ExternalRead:
    value: str | Path


@dataclass(frozen=True, slots=True)
class FanInRead:
    helper: Literal["results", "context"]
    path: str


ReadRef: TypeAlias = ArtifactId | ExternalRead | FanInRead
RequireRef: TypeAlias = ArtifactId | FanInRead
WriteRef: TypeAlias = ArtifactId


@dataclass(frozen=True, slots=True)
class StepIO:
    reads: tuple[ReadRef, ...]
    requires: tuple[RequireRef, ...]
    writes: tuple[WriteRef, ...]
    log_artifacts: tuple[WriteRef, ...]
```

Implementation rules:

```text
Current CompiledStep.reads/requires/writes may remain tuple[str, ...] during migration.
StepPlan must use typed StepIO.
Add conversion helpers to and from current string-compatible fields in plan_adapters.py.
Do not change provider request payloads until tests prove compatibility.
```

---

## 6.3 `RunPaths` and `RunIdentity`

File:

```text
botlane/core/run_paths.py
```

Purpose:

```text
Encode run filesystem layout once instead of passing many path fields through SDK, runtime, engine, child workflow result, and context.
```

Use existing field vocabulary:

```text
task_folder
workflow_folder
run_folder
package_folder
```

Do **not** use:

```text
task_dir
workflow_dir
run_dir
package_dir
```

Definition:

```python
"""Internal run identity and filesystem layout values.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RunPaths:
    root: Path
    task_folder: Path
    workflow_folder: Path
    run_folder: Path
    package_folder: Path
    request_file: Path
    task_request_file: Path | None
    run_meta_file: Path | None
    events_file: Path
    checkpoint_file: Path
    sessions_dir: Path
    trace_file: Path
    raw_dir: Path
    parent_file: Path | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "root",
            "task_folder",
            "workflow_folder",
            "run_folder",
            "package_folder",
            "request_file",
            "events_file",
            "checkpoint_file",
            "sessions_dir",
            "trace_file",
            "raw_dir",
        ):
            object.__setattr__(self, field_name, Path(getattr(self, field_name)))
        if self.task_request_file is not None:
            object.__setattr__(self, "task_request_file", Path(self.task_request_file))
        if self.run_meta_file is not None:
            object.__setattr__(self, "run_meta_file", Path(self.run_meta_file))
        if self.parent_file is not None:
            object.__setattr__(self, "parent_file", Path(self.parent_file))


@dataclass(frozen=True, slots=True)
class RunIdentity:
    task_id: str
    run_id: str
    workflow_name: str
    paths: RunPaths | None = None
```

Rules:

```text
RunIdentity.paths may be None during migration.
Context constructor must not require callers/tests to pass RunIdentity.
Context may synthesize RunIdentity and RunPaths internally from existing arguments.
Keep task_folder, workflow_folder, run_folder, package_folder, request_file, events_file, checkpoint_file, sessions_dir, trace_file, raw_dir fields/properties where currently exposed.
ChildWorkflowResult may gain paths/identity internally only as appended defaulted fields.
ChildWorkflowResult old path fields must remain.
```

---

## 6.4 `RouteContract`

File:

```text
botlane/core/route_contracts.py
```

Purpose:

```text
Make route semantics a single static object.
Unify target, provider visibility, payload schema, route-fields schema, required writes, handoff, on_taken, preset kind, disabled status, and runtime-control status.
```

Definition:

```python
"""Internal route contract values.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, TypeAlias

from .identifiers import ArtifactId


RouteTargetKind: TypeAlias = Literal["step", "finish", "await_input", "fail", "disabled"]


@dataclass(frozen=True, slots=True)
class RouteTarget:
    kind: RouteTargetKind
    step_name: str | None = None


@dataclass(frozen=True, slots=True)
class PayloadContract:
    schema_mode: str = "inherit"
    schema: dict[str, Any] | None = None
    validator: Any | None = None


@dataclass(frozen=True, slots=True)
class RouteFieldsContract:
    schema: dict[str, Any] | None = None
    validator: Any | None = None


@dataclass(frozen=True, slots=True)
class ProviderRoutePolicy:
    visibility: str
    visible: bool
    visible_interactive: bool
    visible_full_auto: bool


@dataclass(frozen=True, slots=True)
class RequiredWriteContract:
    declared: tuple[ArtifactId, ...]
    explicit: tuple[ArtifactId, ...] | None
    effective: tuple[ArtifactId, ...] | None = None


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
RouteContract is internal.
CompiledRoute remains for compatibility.
RouteContract must be buildable from CompiledRoute through plan_adapters.py.
CompiledRoute must be buildable from RouteContract through plan_adapters.py.
Provider contract generation should eventually read RouteContract.
Route finalization should eventually read RouteContract.
Required writes should eventually use ArtifactId internally.
RequiredWriteContract conversion from current string names must use compiled workflow artifact inventory.
```

Critical route ownership rule:

```text
Route contracts live canonically in WorkflowPlan.routes and WorkflowPlan.global_routes.
StepHeader must not duplicate route contracts.
Derived route views must be functions, not stored duplicate state on StepHeader.
```

Allowed helper functions, placed where they avoid cycles:

```python
def available_route_tags(plan: WorkflowPlan, step_name: str) -> tuple[str, ...]:
    ...

def runtime_control_route_tags(plan: WorkflowPlan, step_name: str) -> tuple[str, ...]:
    ...

def provider_visible_route_tags(
    plan: WorkflowPlan,
    step_name: str,
    *,
    mode: Literal["interactive", "full_auto"],
) -> tuple[str, ...]:
    ...
```

Adapter functions belong in `plan_adapters.py`:

```python
def route_contract_from_compiled_route(...) -> RouteContract:
    ...

def compiled_route_from_route_contract(...) -> CompiledRoute:
    ...
```

Inventory rule:

```text
inventory may be None only when route.required_writes is empty.
If route.required_writes is non-empty and inventory is None, route_contract_from_compiled_route must raise a clear ValueError.
Do not guess ArtifactId from string splitting.
```

---

## 6.5 `RouteAction` and `RouteDecision`

File:

```text
botlane/core/route_contracts.py
```

Purpose:

```text
Replace engine-loop terminal sentinel comparisons with typed internal route actions.
```

Definition:

```python
@dataclass(frozen=True, slots=True)
class Continue:
    target_step: str
    reason: str = "route"


@dataclass(frozen=True, slots=True)
class Finish:
    reason: str = "finish"


@dataclass(frozen=True, slots=True)
class AwaitInput:
    pending_input: Any


@dataclass(frozen=True, slots=True)
class FailAction:
    reason: str | None = None
    failure_context: Any | None = None


RouteAction: TypeAlias = Continue | Finish | AwaitInput | FailAction


@dataclass(frozen=True, slots=True)
class RouteDecision:
    final_route: str | None
    contract: RouteContract | None
    action: RouteAction
    runtime_control: str | None = None
    pending_handoffs: tuple[Any, ...] = ()
    provider_attributable: bool = False
    source_hook: str | None = None
    source_phase: str | None = None
```

Compile-time versus runtime rule:

```text
RouteContract may know that a route target is await-input.
PendingInput is only constructed during route finalization.
Do not require PendingInput at compile time.
```

Rules:

```text
RouteAction is internal only.
Do not expose RouteAction in botlane.__all__.
Do not expose RouteAction in botlane.core.__all__.
Do not require user-authored RouteAction objects.
Do not create CaptureOnly as a RouteAction.
Capture/capture-only is an executor mode, not a graph transition.
```

Migration rule:

```text
RouteFinalizer may keep returning RouteFinalizationResult initially.
Add conversion to RouteDecision.
Only switch Engine loop to RouteAction after route contract tests and runtime-control tests pass.
```

---

## 6.6 `StepHeader`, `ProviderTurnPlan`, and `StepPlan`

File:

```text
botlane/core/step_plans.py
```

Purpose:

```text
Replace the broad optional-field CompiledStep bag with typed step variants.
```

Use this clean module skeleton. Do not import `StepIO` from the same module.

```python
"""Internal step-plan values.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, TYPE_CHECKING, TypeAlias

from .identifiers import ArtifactId

if TYPE_CHECKING:
    from .branch_groups.models import BranchGroupPlan
```

Define read/write references first:

```python
@dataclass(frozen=True, slots=True)
class ExternalRead:
    value: str | Path


@dataclass(frozen=True, slots=True)
class FanInRead:
    helper: Literal["results", "context"]
    path: str


ReadRef: TypeAlias = ArtifactId | ExternalRead | FanInRead
RequireRef: TypeAlias = ArtifactId | FanInRead
WriteRef: TypeAlias = ArtifactId


@dataclass(frozen=True, slots=True)
class StepIO:
    reads: tuple[ReadRef, ...]
    requires: tuple[RequireRef, ...]
    writes: tuple[WriteRef, ...]
    log_artifacts: tuple[WriteRef, ...]
```

Common metadata:

```python
@dataclass(frozen=True, slots=True)
class StepStateSpec:
    step_state_model: type[Any]
    step_state_fields: tuple[str, ...]
    step_item_state_model: type[Any] | None
    step_item_state_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StepHookSpec:
    before: Callable[..., Any] | None = None
    after: Callable[..., Any] | None = None
    before_producer: Callable[..., Any] | None = None
    after_producer: Callable[..., Any] | None = None
    before_verifier: Callable[..., Any] | None = None
    after_verifier: Callable[..., Any] | None = None


@dataclass(frozen=True, slots=True)
class StepHeader:
    name: str
    kind: str
    original_step: Any
    session_name: str | None
    scope_name: str | None
    io: StepIO
    state: StepStateSpec
    hooks: StepHookSpec
    provider_policy: Any
```

Important:

```text
StepHeader must not own route contracts.
StepHeader must not duplicate available_routes, authored_routes, runtime_control_routes, or provider-visible route tags unless temporarily needed for compatibility.
Those route views should be derived from WorkflowPlan.routes.
CompiledStep may keep these tuple fields during migration.
```

Provider turn:

```python
ProviderTurnKind: TypeAlias = Literal["llm", "producer", "verifier", "operation"]


@dataclass(frozen=True, slots=True)
class ProviderTurnPlan:
    kind: ProviderTurnKind
    prompt: Any
    session_name: str | None
    io: StepIO
    retry_policy: Any
    expected_output_schema: dict[str, Any] | None
    expected_output_validator: Any | None
```

Provider-turn rule:

```text
ProviderTurnPlan is a plan object.
ProviderTurnPlan must not replace RenderedProviderTurn or ProviderTurnResult.
ProviderTurnPlan is the step-plan input to the existing provider rendering/execution path.
Transport implementations must continue accepting RenderedProviderTurn and returning ProviderTurnResult.
Do not create a parallel provider result system if existing ProviderTurnContext, RenderedProviderTurn, or ProviderTurnResult can represent the required data.
```

Operations rule:

```text
Do not migrate operation execution in the first ProviderTurnPlan phase.
First migrate prompt and produce/verify provider turns.
Only migrate operation turns after OperationRuntime parity tests pass.
```

Step variants:

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
    branch_group: "BranchGroupPlan"


StepPlan: TypeAlias = (
    PromptStepPlan
    | ProduceVerifyStepPlan
    | PythonStepPlan
    | ChildWorkflowStepPlan
    | BranchGroupStepPlan
)
```

Rules:

```text
No StepPlan variant may carry irrelevant fields.
PythonStepPlan must not carry provider prompts.
PromptStepPlan has one ProviderTurnPlan.
ProduceVerifyStepPlan has exactly two ProviderTurnPlan objects.
BranchGroupStepPlan carries BranchGroupPlan, not provider prompt fields.
CompiledStep remains as a compatibility facade until all callers are migrated.
```

---

## 6.7 `BranchGroupPlan` import-cycle-safe design

Branch plans recursively reference `StepPlan`. Avoid runtime import cycles.

Preferred implementation:

```text
Put BranchPlan and BranchGroupPlan in botlane/core/step_plans.py below the StepPlan-adjacent classes, using from __future__ import annotations.
```

Acceptable implementation:

```text
Keep BranchPlan and BranchGroupPlan in botlane/core/branch_groups/models.py, but import StepPlan only under TYPE_CHECKING and use string annotations.
```

If kept in `branch_groups/models.py`, use:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from botlane.core.step_plans import StepPlan


@dataclass(frozen=True, slots=True)
class BranchPlan:
    name: str
    index: int
    input: Any
    step: "StepPlan"


@dataclass(frozen=True, slots=True)
class BranchGroupPlan:
    name: str
    kind: str
    branches: tuple[BranchPlan, ...]
    concurrency: int | None
    settle: str
    success_routes: tuple[str, ...]
    outcome: str | Callable[..., Any] | None
    fan_in_step: "StepPlan | None"
    composite_route_tags: tuple[str, ...]
    default_chain_route: str
    rework_chain_route: str | None = None
```

Rules:

```text
Do not import StepPlan at runtime from branch_groups/models.py.
Keep CompiledBranchGroupSpec compatibility.
Do not rename public parallel, fan_out, or FanIn helpers.
Do not broaden unsupported branch capabilities accidentally.
```

Preserve current unsupported constraints unless fully implemented and tested:

```text
Scoped branch/fan-in steps unsupported.
Child workflow branch/fan-in steps unsupported.
Operation branch/fan-in steps unsupported.
Nested branch groups unsupported.
Provider-backed branch steps require explicit Session.fresh().
Non-fresh provider-backed branch sessions unsupported.
```

---

## 6.8 `WorkflowPlan`

File:

```text
botlane/core/workflow_plan.py
```

Purpose:

```text
Executable internal representation derived from WorkflowDefinition / CompiledWorkflow.
```

Definition:

```python
"""Internal executable workflow plan.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .identifiers import ArtifactId
from .reference_graph import ReferenceGraph
from .route_contracts import RouteContract
from .step_plans import StepPlan


@dataclass(frozen=True, slots=True)
class WorkflowPlan:
    workflow_cls: type[Any]
    workflow_name: str
    state_cls: type[Any]
    input_model: type[Any] | None
    output_model: type[Any] | None
    output_builder: Callable[..., Any] | None
    parameters_cls: type[Any] | None

    entry_step_name: str

    sessions: dict[str, Any]
    default_session_name: str
    default_session_open: bool

    worklists: dict[str, Any]

    steps: dict[str, StepPlan]
    routes: dict[str, dict[str, RouteContract]]
    global_routes: dict[str, RouteContract]

    artifacts: dict[str, Any]
    artifacts_by_id: dict[ArtifactId, Any]
    artifacts_by_qualified_name: dict[str, Any]

    extensions: tuple[Any, ...]
    provider_policy: Any
    source_hash: str | None
    topology_hash: str
    reference_graph: ReferenceGraph | None = None
```

Rules:

```text
WorkflowPlan is logically immutable.
Adapters must copy incoming dictionaries.
Runtime code must not mutate WorkflowPlan maps in place.
compile_workflow(...) must keep returning CompiledWorkflow unless tests are intentionally migrated.
Add compile_workflow_plan(workflow_cls) -> WorkflowPlan.
Initially implement compile_workflow_plan by adapting from compile_workflow.
CompiledWorkflow may hold or convert to WorkflowPlan.
Do not force Engine migration to WorkflowPlan if it risks SDK/simple regressions.
```

Correct end-state framing:

```text
It is acceptable for WorkflowPlan to exist as a tested adapter layer while Engine still consumes CompiledWorkflow.
Engine migration to WorkflowPlan is desirable, but not allowed to break public behavior.
```

---

## 6.9 `PlaceholderRef` and `ReferenceGraph`

Files:

```text
botlane/core/placeholders.py
botlane/core/reference_graph.py
```

Purpose:

```text
Unify placeholder parsing, validation, rendering, and artifact dependency inference.
```

`placeholders.py` must not import `Context` at runtime. Use `TYPE_CHECKING` or `Any` annotations.

Definition:

```python
"""Internal placeholder parsing values.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlaceholderRef:
    raw: str
    root: str
    path: tuple[str, ...]
    source: str
```

Reference graph:

```python
"""Internal workflow reference graph.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass

from .identifiers import ArtifactId
from .placeholders import PlaceholderRef


@dataclass(frozen=True, slots=True)
class ReferenceGraph:
    prompt_refs: dict[str, tuple[PlaceholderRef, ...]]
    artifact_template_refs: dict[str, tuple[PlaceholderRef, ...]]
    inferred_artifact_reads: dict[str, tuple[ArtifactId, ...]]
```

Required functions:

```python
def parse_placeholders(text: str, *, source: str) -> tuple[PlaceholderRef, ...]:
    ...
```

```python
def validate_placeholder_ref(
    ref: PlaceholderRef,
    *,
    surface: str,
    symbols: Any,
) -> str | None:
    ...
```

```python
def render_placeholder_ref(ref: PlaceholderRef, context: Any) -> Any:
    ...
```

```python
def render_template_with_refs(
    template: str,
    refs: tuple[PlaceholderRef, ...],
    context: Any,
    *,
    replace_roots: frozenset[str] | None = None,
    placeholder_label: str,
) -> str:
    ...
```

Rules:

```text
Preserve current placeholder grammar.
Preserve current safe ctx.* allowlist.
Preserve current artifact path restriction: ctx.* is not allowed in artifact paths.
Preserve branch/fan_in placement validation.
Preserve missing input/params/state/worklist error quality.
Do not silently make invalid placeholders valid.
Do not silently make valid placeholders invalid.
```

Important behavior-preservation rule:

```text
The PlaceholderRef migration must be behavior-preserving against existing validation/rendering tests.
The golden placeholder list is a regression target only where current already supports that placeholder family.
Do not add new placeholder semantics unless tests explicitly define them.
```

Golden placeholder families to preserve where currently supported:

```text
{ctx.message}
{ctx.request.text}
{ctx.request.file}
{ctx.request.task_file}
{ctx.input.message}
{ctx.input.<field>}
{ctx.state.<field>}
{ctx.params.<field>}
{input.message}
{input.<field>}
{params.<field>}
{state.<field>}
{run.id}
{workflow.folder}
{task_id}
{run_id}
{workflow_name}
{task_folder}
{workflow_folder}
{run_folder}
{package_folder}
{root}
{request_file}
{item.id}
{item.title}
{item.status}
{item.dir_key}
{item.payload}
{item.payload.<path>}
{item.state.<field>}
{worklist.<name>.current.id}
{worklist.<name>.current.title}
{worklist.<name>.current.status}
{worklist.<name>.current.dir_key}
{worklist.<name>.current.payload}
{worklist.<name>.current.payload.<path>}
{worklist.<name>.item_ids}
{worklist.<name>.current_index}
{worklist.<name>.is_exhausted}
{branch.name}
{branch.index}
{branch.group}
{branch.count}
{branch.input.<field>}
{fan_in.results_path}
{fan_in.context_path}
{fan_in.context_text}
{fan_in.branch_count}
{fan_in.completed_count}
{fan_in.failed_count}
{fan_in.needs_input_count}
{fan_in.cancelled_count}
{previous_step.value}
{previous_step.state.<field>}
{previous_step.item_state.<field>}
{previous_step.meta}
{previous_step.<artifact_name>}
{artifacts.<artifact_name>}
{step.<artifact_name>}
```

---

## 6.10 `ExecutionFrame`

File:

```text
botlane/core/execution_frame.py
```

Purpose:

```text
Move mutable runtime state out of Context private fields and _ContextRuntime sidecar.
Make branch/fan-in child contexts explicit.
Make checkpoint/resume and context cloning easier to reason about.
```

Definition:

```python
"""Internal mutable execution-frame state.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .run_paths import RunIdentity
from .workflow_plan import WorkflowPlan


_DEFAULT_FRAME_MESSAGE = object()


@dataclass(slots=True)
class ExecutionFrame:
    identity: RunIdentity | None = None
    workflow: WorkflowPlan | None = None

    state_cell: Any | None = None
    params: Any | None = None
    workflow_params: dict[str, Any] | None = None
    message: object = _DEFAULT_FRAME_MESSAGE
    input_fields: Any | None = None
    answer: str | None = None
    input_response: Any | None = None

    session_store: Any | None = None
    session_definitions: dict[str, Any] | None = None
    worklists: dict[str, Any] | None = None
    selections: dict[str, Any] | None = None
    selection_snapshots: dict[str, Any] | None = None
    active_worklist: str | None = None

    artifacts: Any | None = None
    values: dict[str, Any] | None = None
    route: Any | None = None
    event: Any | None = None
    outcome: Any | None = None
    meta: Any | None = None

    step_name: str | None = None
    step_execution_id: str | None = None
    step_state: Any | None = None
    item_state: Any | None = None
    step_item_state: Any | None = None

    branch: Any | None = None
    fan_in: Any | None = None

    runtime_event_sink: Callable[[str, Mapping[str, Any]], None] | None = None
    workflow_invoker: Callable[..., Any] | None = None
```

Required behavior:

```text
ExecutionFrame must preserve the difference between explicit message=None and default message-from-request-file behavior.
```

Required methods:

```python
def child_for_step(...): ...
def child_for_branch(...): ...
def child_for_fan_in(...): ...

def set_state(...): ...
def set_artifacts(...): ...
def set_values(...): ...
def set_route(...): ...
def set_event(...): ...
def set_outcome(...): ...
def set_meta(...): ...
def set_step_state(...): ...
def set_item_state(...): ...
def set_step_item_state(...): ...
```

Migration rules:

```text
ExecutionFrame.workflow may be None during migration.
ExecutionFrame.identity may be None during migration.
execution_frame.py must not import Context at runtime.
Context constructor must keep its current signature.
Context should synthesize ExecutionFrame internally.
Context public properties should gradually read from frame.
Old private fields should be mirrored until all tests pass.
context_runtime(context) may remain initially, but should delegate to ExecutionFrame mutation.
Do not remove WeakKeyDictionary until branch groups, worklists, hooks, SDK, and context tests pass.
```

---

## 6.11 `ExecutionServices`

File:

```text
botlane/core/execution_services.py
```

Purpose:

```text
Migrate collaborators away from direct Engine private-method calls.
Avoid replacing Engine with a renamed god object.
```

Initial definition:

```python
"""Internal execution service protocols.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ArtifactService(Protocol): ...
class RouteService(Protocol): ...
class HookService(Protocol): ...
class SessionService(Protocol): ...
class CheckpointService(Protocol): ...
class EventService(Protocol): ...
class ProviderService(Protocol): ...
class OperationService(Protocol): ...
class ChildWorkflowService(Protocol): ...
class StateService(Protocol): ...


@dataclass(frozen=True, slots=True)
class ExecutionServices:
    artifacts: ArtifactService | None = None
    routes: RouteService | None = None
    hooks: HookService | None = None
    sessions: SessionService | None = None
    checkpoints: CheckpointService | None = None
    events: EventService | None = None
    providers: ProviderService | None = None
    operations: OperationService | None = None
    child_workflows: ChildWorkflowService | None = None
    state: StateService | None = None
```

Migration rules:

```text
Create ExecutionServices as a small shell first.
Only add concrete protocol methods when a collaborator is migrated.
Do not add broad engine-like methods.
Do not create methods like run_step, execute_everything, or finalize_everything.
Each service must own one narrow operation family.
```

Collaborator migration target:

```text
Before: Collaborator(engine)
After:  Collaborator(services, plan) or Collaborator(specific_service)
```

---

## 6.12 Core provider policy resolver protocol

File:

```text
botlane/core/provider_policy_resolution.py
```

Purpose:

```text
Remove core -> runtime dependency leaks.
Core defines protocol.
Runtime implements protocol.
```

Definition:

```python
"""Core provider policy resolver protocol.

Runtime implementations live outside botlane.core.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ProviderPolicyResolverProtocol(Protocol):
    def resolve_for_step(self, step: Any) -> Any:
        ...

    def resolve_for_operation(
        self,
        ctx: Any | None,
        explicit_policy: Any = None,
    ) -> Any:
        ...
```

Rules:

```text
botlane.core must not import botlane.runtime.
botlane.runtime.provider_policy_resolver.ProviderPolicyResolver must implement this protocol.
Engine and operations must type against the core protocol, not runtime implementation.
Add strictness test only after current core -> runtime imports are fixed.
```

---

## 6.13 `BranchResult`

File:

```text
botlane/core/branch_groups/results.py
```

Purpose:

```text
Replace internal branch result dictionaries with typed values while preserving manifest JSON shape exactly.
```

Definition:

```python
"""Internal branch-group result values.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


BranchStatus = Literal["completed", "needs_input", "failed", "cancelled", "skipped"]


@dataclass(frozen=True, slots=True)
class BranchArtifactObservation:
    name: str
    path: str
    kind: str | None
    exists: bool
    validation: str
    validation_errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BranchResult:
    name: str
    index: int
    input: Any
    step_name: str
    status: BranchStatus
    route: str | None
    destination: str | None
    runtime_control: str | None
    reason: str | None
    question: str | None
    artifacts: tuple[BranchArtifactObservation, ...]
    raw_output_path: str | None
    raw_output_paths: dict[str, str]
    provider_session: str | None
    provider_sessions: dict[str, str]
    error: dict[str, Any] | None
    started_at: str
    finished_at: str
    duration_ms: int
    usage: dict[str, Any]
    cancellation_requested: bool = False
    cancellation_completed: bool = False
    cancellation_supported: bool = True

    def to_manifest_dict(self) -> dict[str, Any]:
        ...
```

Rules:

```text
BranchResult.to_manifest_dict() must exactly reproduce current manifest branch entry shape.
Do not change branch manifest schema.
Do not change branch event payloads.
Do not change branch scheduling, fan-in routing, or composite finalization until BranchResult serialization parity is proven.
render_branch_group_context may accept dicts and BranchResult during migration.
select_branch_group_outcome may continue consuming manifest dicts initially.
```

Manifest schema rule:

```text
Branch manifest schema must remain "botlane.branch_results/v1".
```

---

## 6.14 `WorkflowLocator`

File:

```text
botlane/runtime/workflow_locator.py
```

Purpose:

```text
Replace workflow source/loading optional-field soup with shape-specific locator variants.
```

Definition:

```python
"""Runtime workflow locator variants.

Internal runtime helper; not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class CatalogWorkflowLocator:
    workflow_id: str


@dataclass(frozen=True, slots=True)
class PythonFileWorkflowLocator:
    path: Path
    class_name: str | None = None


@dataclass(frozen=True, slots=True)
class PythonModuleWorkflowLocator:
    module: str
    class_name: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowDirectoryLocator:
    path: Path


WorkflowLocator: TypeAlias = (
    CatalogWorkflowLocator
    | PythonFileWorkflowLocator
    | PythonModuleWorkflowLocator
    | WorkflowDirectoryLocator
)
```

Rules:

```text
Keep existing workflow reference resolution behavior.
Do not break runtime CLI workflow lookup.
Do not break SDK workflow string resolution.
Do not remove existing workflow catalog/reference fields until adapter tests pass.
```

---

## 6.15 `SingleStepPlan`

File:

```text
botlane/core/step_plans.py
```

or an internal SDK module:

```text
botlane/sdk.py
```

Purpose:

```text
Optional internal replacement for SDK synthetic one-step workflow execution.
```

Definition:

```python
@dataclass(frozen=True, slots=True)
class SingleStepPlan:
    step: StepPlan
    input_model: type[Any] | None
    params_model: type[Any] | None
    routes: dict[str, RouteContract]
    workflow_policy: Any
```

Hard rule:

```text
SingleStepPlan is optional until exact parity with the synthetic workflow path is proven.
If parity is not fully proven, keep the current synthetic workflow path.
```

Do not switch `Botlane.step(...)` to `SingleStepPlan` until tests prove identical behavior for:

```text
message handling
typed input handling
params handling
route defaults
explicit route overrides
policy layering
provider_questions true/false/None
on_input pause/resume
retention behavior
artifact reads/writes
state behavior
StepResult.route
StepResult.value is None
workflow_result passthrough
error wrapping
debug paths
```

---

# 7. Compiler and adapter requirements

## 7.1 Keep `compile_workflow(...)`

Current behavior must remain:

```python
compile_workflow(workflow_cls) -> CompiledWorkflow
```

Add:

```python
compile_workflow_plan(workflow_cls) -> WorkflowPlan
```

Initial implementation:

```python
def compile_workflow_plan(workflow_cls):
    compiled = compile_workflow(workflow_cls)
    from .plan_adapters import workflow_plan_from_compiled

    return workflow_plan_from_compiled(compiled)
```

Later implementation may invert control:

```python
def compile_workflow(workflow_cls):
    plan = compile_workflow_plan(workflow_cls)
    return compiled_workflow_from_plan(plan)
```

Only invert after compatibility tests pass.

## 7.2 Conversion helpers live in `plan_adapters.py`

Add:

```python
def step_plan_from_compiled_step(
    step: CompiledStep,
    *,
    routes: Mapping[str, RouteContract],
    inventory: Mapping[str, CompiledArtifact],
) -> StepPlan:
    ...
```

```python
def compiled_step_from_step_plan(
    plan: StepPlan,
    *,
    routes: Mapping[str, RouteContract],
) -> CompiledStep:
    ...
```

```python
def workflow_plan_from_compiled(compiled: CompiledWorkflow) -> WorkflowPlan:
    ...
```

```python
def compiled_workflow_from_plan(plan: WorkflowPlan) -> CompiledWorkflow:
    ...
```

```python
def route_contract_from_compiled_route(
    route: CompiledRoute,
    *,
    inventory: Mapping[str, CompiledArtifact] | None = None,
) -> RouteContract:
    ...
```

```python
def compiled_route_from_route_contract(contract: RouteContract) -> CompiledRoute:
    ...
```

Rules:

```text
CompiledWorkflow remains test-compatible.
CompiledStep remains test-compatible.
CompiledRoute remains test-compatible.
Topology hash must remain stable unless a test is intentionally updated.
Provider contracts must receive equivalent route, visibility, schema, and required-write payloads.
Branch-group internal compiled steps must still compile.
```

## 7.3 Topology hash parity

Add a concrete parity test:

```text
For a representative workflow without branch groups, compile_workflow(...).topology_hash must remain unchanged before and after adding WorkflowPlan adapters.
```

Use a non-branch workflow for this parity check.

## 7.4 Route table parity

Add a concrete parity test:

```text
For each compiled workflow in route tests, CompiledWorkflow.routes and WorkflowPlan.routes must agree on:
- route tags
- target
- visibility
- payload schema
- route-fields schema
- handoff
- disabled status
- runtime-control status
- required writes
```

---

# 8. Engine and collaborator migration

## 8.1 Engine target

Long-term target:

```text
Engine
  - owns or receives WorkflowPlan / CompiledWorkflow compatibility wrapper
  - creates ExecutionFrame
  - uses ExecutionServices
  - delegates step execution
  - consumes RouteAction internally
```

Important:

```text
Do not rewrite the whole engine in one pass.
Do not force full Engine migration to WorkflowPlan if it threatens SDK/simple behavior.
```

This project can be considered successful if:

```text
WorkflowPlan exists, is tested, and is compatible,
even if Engine still consumes CompiledWorkflow behind adapters.
```

## 8.2 Collaborator migration order

Migrate collaborators away from direct `Engine` private-method calls in this order:

```text
1. ArtifactGuard
2. RouteFinalizer
3. HookRunner
4. StepDispatcher
5. OperationRecorder
6. WorkflowInvoker
7. BranchGroupRuntime
8. CheckpointManager
9. SessionRuntime
10. StateRuntime
```

Rules:

```text
Each migration must reduce direct engine._private_method calls.
Temporary private calls must be marked TODO with a specific migration note.
Do not create one service that simply exposes all Engine private methods.
```

## 8.3 Route finalizer target

Current route finalization result may remain.

Add:

```python
def route_decision_from_finalization(result: RouteFinalizationResult) -> RouteDecision:
    ...
```

or add:

```python
RouteFinalizationResult.decision
```

Rules:

```text
RouteFinalizer should eventually build RouteDecision internally.
Engine may keep consuming RouteFinalizationResult until RouteAction migration is safe.
```

## 8.4 Step dispatch target

During migration, dispatch may still use `CompiledStep.kind`.

Final target:

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

Do not introduce one broad `StepKindStrategy` that owns compile, execute, and default-route behavior.

If strategy objects are introduced, split them:

```text
StepLoweringRule
StepPlanner
StepExecutor
RouteDefaultRule
```

---

# 9. Provider turn migration

## 9.1 Add `ProviderTurnPlan` adapter

ProviderTurnPlan should drive construction of existing provider request/rendering/result objects.

Use existing provider boundary types where possible, especially current provider turn/rendering/result models under `botlane.core.providers`.

Mandatory rule:

```text
ProviderTurnPlan must not replace RenderedProviderTurn or ProviderTurnResult.
ProviderTurnPlan is the step-plan input to the existing provider rendering/execution path.
Transport implementations must continue accepting RenderedProviderTurn and returning ProviderTurnResult.
```

Do not create a second provider result universe unless the current provider result types cannot represent required data.

## 9.2 Single-turn and produce/verify unification

Target model:

```text
Prompt step = one ProviderTurnPlan
Produce/verify step = producer ProviderTurnPlan + verifier ProviderTurnPlan
Operation step = later migration only
```

Provider execution should share:

```text
retry handling
session persistence
provider attempt events
raw output persistence
usage aggregation
route visibility
structured output validation
required-write reporting
```

Do not regress:

```text
producer_writes
verifier_writes
verifier_reads
verifier_requires
producer session
verifier session
producer/verifier hooks
route visibility
expected output schema
fake provider call records
runtime tracing
```

## 9.3 Operations are a later phase

Do not migrate operation execution in the first ProviderTurnPlan phase.

First migrate:

```text
PromptStep provider turn
ProduceVerifyStep producer turn
ProduceVerifyStep verifier turn
```

Only migrate operation turns after parity tests pass for:

```text
llm(...)
classify(...)
operation policy resolution
operation result recording
operation replay/checkpoint behavior
operation context values
```

---

# 10. Context and ExecutionFrame migration

## Phase A: Add frame behind Context

```text
Add ExecutionFrame.
Context constructor builds an ExecutionFrame internally.
Keep old private fields mirrored.
context_runtime(context) mutates both frame and old fields.
```

## Phase B: Move Context reads to frame

```text
Context properties gradually read from frame.
Old private fields remain compatibility aliases.
Tests must not observe behavior change.
```

## Phase C: Child contexts use child frames

```text
Branch/fan-in helpers use parent_frame.child_for_branch(...)
Fan-in helpers use parent_frame.child_for_fan_in(...)
Stop manually copying large sets of private Context fields once parity is proven.
```

## Phase D: Remove weak sidecar only after parity

```text
Remove WeakKeyDictionary only after all context, branch group, worklist, SDK, runtime, and contract tests pass.
```

---

# 11. Placeholder migration

## 11.1 Parser first

Add parser and tests before replacing existing validation or rendering.

Required behavior:

```python
parse_placeholders("Echo {ctx.message} / {input.topic}", source="prompt")
```

returns stable `PlaceholderRef` values preserving:

```text
raw expression
root
path
source
```

## 11.2 Validation next

Replace existing prompt-reference validation gradually.

Rules:

```text
Old validation function may delegate to PlaceholderRef validation.
Do not change error messages where tests assert them.
Do not infer reads differently.
Do not alter branch/fan_in placement rules.
Do not expand grammar just because a placeholder appears in the aspirational list.
```

## 11.3 Rendering last

Replace runtime template rendering gradually.

Rules:

```text
Old render_runtime_template may parse refs and delegate to the new renderer.
Artifact-template rendering should be migrated only after ctx.* artifact-path rejection tests pass.
```

---

# 12. Branch group migration

## 12.1 Type branch results first

Convert these branch result dict constructors first:

```text
_cancelled_branch_result
_skipped_branch_result
_unexpected_branch_failure_result
_branch_result_from_step_result
_failed_branch_result
```

New flow:

```text
Build BranchResult.
Immediately serialize with to_manifest_dict().
Keep manifest JSON identical.
```

## 12.2 Preserve branch manifest and events

Do not change:

```text
schema
kind
name
started_at
finished_at
duration_ms
concurrency
settle
success_routes
branches
```

Do not change event names or payload shape.

Preserve:

```text
branch_group_started
branch_scheduled
branch_started
branch_completed
branch_failed
branch_needs_input
branch_cancelled
branch_skipped
branch_manifest_written
fan_in_started
fan_in_completed
branch_group_completed
```

Schema rule:

```text
Branch manifest schema must remain "botlane.branch_results/v1".
```

## 12.3 Runtime ownership migration

After `ExecutionFrame` and `ExecutionServices` exist:

```text
BranchGroupRuntime(engine) -> BranchGroupRuntime(services)
create_branch_context(parent, ...) -> parent_frame.child_for_branch(...)
create_fan_in_context(parent, ...) -> parent_frame.child_for_fan_in(...)
```

Do not change scheduling/fan-in/finalization before serialization parity is locked.

---

# 13. Provider policy migration

## 13.1 Core protocol

Create:

```text
botlane/core/provider_policy_resolution.py
```

Runtime implementation remains in:

```text
botlane/runtime/provider_policy_resolver.py
```

Rules:

```text
Core imports protocol only.
Runtime implements protocol.
No core module imports botlane.runtime.
```

## 13.2 AST-aware core/runtime strictness test

Add the no-core-runtime-import test only after current violations are fixed.

The strictness test must parse Python files using `ast`.

It must detect both absolute runtime imports and relative runtime imports from files under `botlane/core`.

Fail on:

```text
import botlane.runtime
from botlane.runtime import ...
from botlane.runtime.foo import ...
from ..runtime import ...
from ..runtime.foo import ...
from ...runtime import ...
from ...runtime.foo import ...
```

Allow only imports inside `if TYPE_CHECKING:` blocks.

Test requirements:

```text
Scan botlane/core/**/*.py.
Fail on runtime imports outside TYPE_CHECKING.
Do not fail on runtime importing core.
Do not fail on tests importing runtime.
```

## 13.3 Capability/rule table

Provider-specific policy emitters may gradually move from large imperative conditionals to rule tables.

Define:

```python
from dataclasses import dataclass
from typing import Callable, Literal


PolicySupport = Literal["native", "lossy", "unsupported", "unsafe", "requires_flag"]


@dataclass(frozen=True, slots=True)
class PolicyFeatureRule:
    feature: str
    provider: str
    support: PolicySupport
    emit: Callable[..., object]
```

Migration order:

```text
Codex emitter first.
Claude emitter second.
```

Rules:

```text
Preserve emitted payloads.
Preserve unsupported/lossy/unsafe reports.
Preserve provider policy config tests.
```

---

# 14. Workflow locator migration

Add `WorkflowLocator` variants and adapters.

Rules:

```text
Existing workflow catalog entry/reference objects may remain.
Adapters should convert existing optional-field objects to WorkflowLocator variants.
Do not break runtime CLI workflow list/describe/run.
Do not break SDK workflow string resolution.
Do not break workflow catalog root behavior.
```

---

# 15. SDK `SingleStepPlan` migration

## 15.1 Parity tests first

Create tests comparing:

```text
current synthetic workflow path
new SingleStepPlan path
```

Test matrix:

```text
PromptStep default route
PromptStep explicit routes
ProduceVerifyStep default accepted/needs_rework routes
ProduceVerifyStep explicit routes
PythonStep handler route
ChildWorkflowStep resolvable workflow
simple llm operation
simple classify operation
typed input model
params model
message
policy layering
provider_questions true
provider_questions false
provider_questions None
on_input pause/resume
retention delete/promote/retain
artifact reads/writes
StepResult.route
StepResult.value is None
StepResult.workflow_result is full result
SDK debug paths
error wrapping
```

## 15.2 Preserve support matrix

Current `client.step(...)` support must remain.

Supported:

```text
simple named prompt declarations
simple named produce/verify declarations
simple named python declarations
simple named workflow declarations
simple operation declarations
core PromptStep
core ProduceVerifyStep
core PythonStep
resolvable core ChildWorkflowStep
```

Rejected or unsupported:

```text
branch-group declarations
worklist-scoped declarations
unresolved child workflow references
```

Do not accidentally accept unsupported cases unless fully implemented and tested.

## 15.3 Switch only after parity

Only after parity passes:

```text
Botlane.step(...) -> build SingleStepPlan -> execute through same engine/services
```

Keep synthetic workflow fallback temporarily until one full test suite pass.

---

# 16. Test requirements

## 16.1 Existing tests to run repeatedly

After each major phase, run:

```bash
python -m pytest tests/unit/test_simple_surface.py
python -m pytest tests/unit/test_sdk_facade.py
python -m pytest tests/unit/test_simple_policy.py
python -m pytest tests/runtime/test_sdk_policy.py
python -m pytest tests/runtime/test_provider_policy_emitters.py
python -m pytest tests/runtime/test_provider_policy_steps.py
python -m pytest tests/runtime/test_workspace_and_context.py
python -m pytest tests/contract/test_canonical_runtime_contracts.py
python -m pytest tests/contract/engine
python -m pytest tests/contract/test_branch_group_runtime.py
python -m pytest tests/strictness/test_no_compat.py
```

Before final completion:

```bash
python -m pytest
```

## 16.2 New tests to add

### `tests/strictness/test_core_runtime_boundary.py`

Add only after current violations are fixed.

Test:

```text
No botlane/core/**/*.py module imports botlane.runtime outside TYPE_CHECKING.
Use ast parsing, not naive grep.
Catch both absolute and relative runtime imports.
```

### `tests/unit/test_artifact_ids.py`

Cover:

```text
workflow ArtifactId valid
step ArtifactId valid
step ArtifactId requires step
workflow ArtifactId rejects step
qualified_name/display stable
artifact ID conversion uses inventory/compiled artifact records
no naive qualified-name dot splitting
```

### `tests/unit/test_run_paths.py`

Cover:

```text
RunPaths normalizes Path values
RunPaths uses task_folder/workflow_folder/run_folder/package_folder names
RunIdentity stores IDs and optional paths
Context can synthesize identity/paths from current constructor args
ChildWorkflowResult old path fields remain
```

### `tests/unit/test_route_contracts.py`

Cover:

```text
CompiledRoute -> RouteContract -> CompiledRoute round trip
FINISH target maps to Finish internally
AWAIT_INPUT target maps to AwaitInput internally
FAIL target maps to FailAction internally
normal step target maps to Continue internally
provider visibility fields preserved
required writes preserved
required writes conversion uses inventory
payload schema preserved
route fields schema preserved
handoff/on_taken preserved
disabled route preserved
runtime-control status preserved
route required_writes with no inventory raises ValueError
```

### `tests/unit/test_step_plans.py`

Cover:

```text
PromptStep compiles to PromptStepPlan with one ProviderTurnPlan
ProduceVerifyStep compiles to ProduceVerifyStepPlan with producer and verifier turns
PythonStep compiles to PythonStepPlan with handler and no provider turn
ChildWorkflowStep compiles to ChildWorkflowStepPlan
BranchGroupStep compiles to BranchGroupStepPlan
StepHeader does not duplicate route contract tables
StepIO uses ArtifactId/ExternalRead/FanInRead
CompiledStep compatibility fields still match old expectations
```

### `tests/unit/test_workflow_plan_adapters.py`

Cover:

```text
CompiledWorkflow -> WorkflowPlan conversion succeeds
WorkflowPlan -> CompiledWorkflow round trip preserves expected compatibility fields
topology_hash parity for representative non-branch workflow
route table parity between CompiledWorkflow.routes and WorkflowPlan.routes
artifact inventory parity
session/worklist parity
WorkflowPlan maps are not mutated by runtime code in tested execution paths
```

### `tests/unit/test_placeholder_refs.py`

Cover:

```text
parser extracts placeholders exactly
ctx safe refs validate
input refs validate
params refs validate
state refs validate
worklist refs validate
branch refs validate only in branch context
fan_in refs validate only in fan-in context
artifact path rejects ctx.*
unknown fields raise equivalent errors
inferred artifact reads unchanged
no new placeholder semantics added without explicit test
```

### `tests/unit/test_execution_frame_context_parity.py`

Cover:

```text
Context properties match old constructor behavior
context_runtime mutators update Context-visible values
frame mutation mirrors old private fields during migration
branch child frame/context preserves shared state cell
fan-in frame/context exposes fan_in metadata
worklist selection snapshots preserved
explicit message=None remains distinct from default message-from-request-file behavior
```

### `tests/contract/test_branch_result_serialization.py`

Cover:

```text
BranchResult.to_manifest_dict matches current branch result dict shape
branch manifest JSON remains stable
branch manifest schema remains "botlane.branch_results/v1"
branch context markdown remains stable
branch outcome selection remains stable
```

### `tests/runtime/test_workflow_locator_variants.py`

Cover:

```text
CatalogWorkflowLocator resolves same workflow as existing catalog path
PythonFileWorkflowLocator resolves same class as existing loader path
PythonModuleWorkflowLocator resolves same class as existing loader path
WorkflowDirectoryLocator resolves same workflow as existing directory path
invalid locators fail clearly
```

### `tests/runtime/test_provider_policy_core_protocol.py`

Cover:

```text
runtime ProviderPolicyResolver satisfies core protocol
isinstance resolver check works because protocol is runtime_checkable
step policy resolution unchanged
operation policy resolution unchanged
core does not import runtime
```

### `tests/contract/test_provider_turn_plan_adapter.py`

Cover:

```text
ProviderTurnPlan feeds existing RenderedProviderTurn path
transport still receives RenderedProviderTurn
transport still returns ProviderTurnResult
fake provider call records unchanged
prompt step provider behavior unchanged
produce/verify provider behavior unchanged
operation execution not migrated yet unless operation parity tests exist
```

### `tests/contract/test_single_step_plan_equivalence.py`

Add only when implementing `SingleStepPlan`.

Cover:

```text
synthetic workflow path and SingleStepPlan path produce equivalent StepResult/WorkflowResult
```

### `tests/runtime/test_botlane_persistence_identity.py`

Cover:

```text
SDK task sentinel remains .botlane-sdk-task.json
SDK task sentinel schema remains "botlane.sdk_task/v1"
SDK task sentinel generated_by remains "botlane.sdk"
SDK task storage remains under .botlane/tasks
cleanup ownership checks still reject malformed or foreign sentinels
branch manifest schema remains "botlane.branch_results/v1"
```

---

# 17. Phased implementation order

## Phase 0: Freeze public compatibility

Confirm or add tests for:

```text
botlane.__all__
botlane.core.__all__ unchanged unless explicitly required
botlane.core.branch_groups.__all__ unchanged unless explicitly required
removed compat names remain absent
simple State/Params conventions
simple descriptor rejection
simple artifact helpers
simple route sentinels
Botlane.run signature behavior
Botlane.step signature behavior
StepResult.value is None
SDK helper delegation
provider_questions defaulting
retention/cleanup safety
.botlane persistence identity
botlane schema IDs
prompt placeholders
branch group unsupported constraints
public/semi-public dataclass field compatibility
```

No architectural rewrite until these tests pass.

## Phase 1: Boundary and value primitives

Implement:

```text
ArtifactId
RunPaths
RunIdentity
ProviderPolicyResolverProtocol
plan_adapters.py shell
```

Fix any current core -> runtime imports.

Then add the AST-aware no-core-runtime-import strictness test.

Run:

```bash
python -m pytest tests/unit/test_artifact_ids.py
python -m pytest tests/unit/test_run_paths.py
python -m pytest tests/runtime/test_provider_policy_core_protocol.py
python -m pytest tests/strictness/test_core_runtime_boundary.py
python -m pytest tests/unit/test_simple_surface.py
python -m pytest tests/unit/test_sdk_facade.py
python -m pytest tests/strictness/test_no_compat.py
```

## Phase 2: Route contracts

Implement:

```text
RouteTarget
PayloadContract
RouteFieldsContract
ProviderRoutePolicy
RequiredWriteContract
RouteContract
RouteDecision
RouteAction
CompiledRoute conversion helpers in plan_adapters.py
route view helper functions
```

Rules:

```text
Keep CompiledRoute compatibility.
Do not move routes into StepHeader.
Do not expose RouteAction publicly.
Use inventory-aware required-write conversion.
Route conversion must raise ValueError for non-empty required_writes without inventory.
```

## Phase 3: Step plans and WorkflowPlan adapters

Implement:

```text
ExternalRead
FanInRead
StepIO
StepStateSpec
StepHookSpec
StepHeader
ProviderTurnPlan
StepPlan variants
BranchPlan / BranchGroupPlan import-cycle-safe design
WorkflowPlan
CompiledStep <-> StepPlan conversion in plan_adapters.py
CompiledWorkflow <-> WorkflowPlan conversion in plan_adapters.py
compile_workflow_plan(...)
```

Rules:

```text
Engine may still consume CompiledWorkflow.
Provider requests may still receive string-compatible fields.
CompiledStep compatibility remains.
StepHeader must not duplicate route contracts.
Type aliases must use TypeAlias.
compiler.py must import plan_adapters lazily inside functions only.
```

## Phase 4: ExecutionFrame behind Context

Implement:

```text
ExecutionFrame
Context internal frame support
context_runtime delegation to frame
RunIdentity/RunPaths synthesis in Context where possible
Context parity tests
```

Rules:

```text
Keep old Context constructor.
Keep old private fields mirrored.
Preserve _DEFAULT_MESSAGE semantics through _DEFAULT_FRAME_MESSAGE.
Do not remove WeakKeyDictionary yet.
```

## Phase 5: Route finalization adapter

Update RouteFinalizer to build or expose `RouteDecision`.

Rules:

```text
Keep RouteFinalizationResult compatibility.
Engine may still consume old result.
Run all route/runtime-control contract tests.
```

## Phase 6: ProviderTurnPlan adapter

Wire ProviderTurnPlan into current provider turn/rendering/request path.

Rules:

```text
Use existing RenderedProviderTurn / ProviderTurnResult.
Preserve fake provider behavior.
Preserve provider attempt events.
Preserve session persistence.
Do not migrate operations yet.
```

## Phase 7: ExecutionServices incremental migration

Introduce services only as collaborators are migrated.

Migration order:

```text
ArtifactGuard
RouteFinalizer
HookRunner
StepDispatcher
OperationRecorder
WorkflowInvoker
BranchGroupRuntime
CheckpointManager
SessionRuntime
StateRuntime
```

Rules:

```text
No broad Engine clone service.
No new core -> runtime imports.
Temporary engine private calls must be marked and reduced.
```

## Phase 8: PlaceholderRef and ReferenceGraph

Implement:

```text
PlaceholderRef parser
ReferenceGraph
validation delegation
runtime rendering delegation
artifact template validation delegation
```

Rules:

```text
Preserve grammar and error behavior.
Do not change inferred reads.
Do not add new semantics unless tests explicitly require them.
placeholders.py must not import Context at runtime.
```

## Phase 9: BranchResult and BranchGroupPlan

Implement:

```text
BranchArtifactObservation
BranchResult
BranchResult.to_manifest_dict()
BranchPlan
BranchGroupPlan
CompiledBranchGroupSpec adapter
```

Rules:

```text
Manifest JSON identical.
Manifest schema remains "botlane.branch_results/v1".
Events identical.
Scheduling unchanged until serialization parity is proven.
```

## Phase 10: Provider policy capability tables

Implement:

```text
PolicyFeatureRule
Codex policy rule table
Claude policy rule table
```

Rules:

```text
Provider policy outputs and reports identical.
```

## Phase 11: WorkflowLocator

Implement locator variants and adapters.

Rules:

```text
Existing loader/catalog behavior unchanged.
```

## Phase 12: Optional SingleStepPlan

Implement `SingleStepPlan` only after prior phases are stable.

Rules:

```text
Build parity tests first.
Keep synthetic workflow fallback.
Switch Botlane.step only after parity.
```

## Phase 13: Cleanup

After full suite passes:

```text
Remove temporary adapter-only private calls where safe.
Remove duplicate route/provider-visible calculations where safe.
Remove dead placeholder parsing branches where safe.
Keep compatibility classes/fields still required by tests or advanced internal imports.
Do not slim public root namespace.
Do not expose internal plan objects.
```

---

# 18. Explicit non-goals

Do not do these:

```text
Do not change botlane.__all__.
Do not casually change botlane.core.__all__.
Do not casually change botlane.core.branch_groups.__all__.
Do not expose WorkflowPlan, StepPlan, RouteContract, RouteAction, ExecutionFrame, or ArtifactId publicly.
Do not replace public FINISH/AWAIT_INPUT/FAIL/SELF with classes.
Do not require users to pass explicit step IDs.
Do not remove simple Workflow/State/Params conventions.
Do not remove synthetic Botlane.step path until SingleStepPlan parity is proven.
Do not broaden client.step support accidentally.
Do not accept branch groups in client.step unless fully implemented and tested.
Do not change provider_questions semantics.
Do not change retention cleanup ownership checks.
Do not change .botlane state-directory semantics.
Do not change .botlane-sdk-task.json sentinel semantics.
Do not change botlane.sdk_task/v1 or botlane.branch_results/v1 schema IDs.
Do not introduce deprecated package aliases or direct deprecated package imports.
Do not reintroduce removed compatibility aliases.
Do not import runtime from core.
Do not create a new god object called ExecutionServices.
Do not duplicate route contracts on StepHeader.
Do not parse artifact IDs by splitting qualified-name strings on dots.
Do not create a second provider-turn result layer unnecessarily.
Do not migrate operations in the first provider-turn phase.
Do not rewrite the whole engine in one pass.
Do not reorder public/semi-public dataclass fields.
Do not add required fields to public/semi-public dataclasses.
Do not import plan_adapters from compiler.py at module import time.
Do not import compiler.py from value-object modules at runtime.
Do not import Context from placeholders.py at runtime.
```

---

# 19. Definition of done

The refactor is complete for this spec when all are true:

```text
1. Full pytest suite passes.
2. botlane.__all__ is unchanged.
3. botlane.core.__all__ is unchanged unless an explicit internal test required a change.
4. botlane.core.branch_groups.__all__ is unchanged unless an explicit internal test required a change.
5. strictness tests pass and removed compat aliases are not reintroduced.
6. botlane/core has no runtime imports outside TYPE_CHECKING.
7. The core/runtime import strictness test is AST-aware and catches absolute and relative runtime imports.
8. ArtifactId exists and uses inventory/compiled-artifact-based conversion, not naive dot splitting.
9. RunPaths and RunIdentity exist and use task_folder/workflow_folder/run_folder/package_folder names.
10. RunPaths and RunIdentity are integrated without forcing public constructor changes.
11. RouteContract and RouteDecision/RouteAction exist internally with CompiledRoute compatibility.
12. RequiredWriteContract conversion uses artifact inventory.
13. route_contract_from_compiled_route raises ValueError for non-empty required_writes without inventory.
14. StepPlan variants and ProviderTurnPlan exist with CompiledStep compatibility.
15. StepHeader does not duplicate canonical route contracts.
16. All union aliases use TypeAlias.
17. WorkflowPlan exists and can be built from CompiledWorkflow.
18. WorkflowPlan maps are treated as logically immutable and copied by adapters.
19. plan_adapters.py owns compiled-object conversion helpers and avoids import cycles.
20. compiler.py imports plan_adapters lazily inside functions only.
21. No value-object module imports compiler.py at runtime.
22. Engine either safely consumes WorkflowPlan internally, or WorkflowPlan remains a tested adapter while Engine stays on CompiledWorkflow.
23. Topology hash parity is tested for a representative non-branch workflow.
24. Route table parity is tested between CompiledWorkflow and WorkflowPlan.
25. Context uses ExecutionFrame internally or has a tested migration path with public behavior unchanged.
26. ExecutionFrame preserves default-message sentinel behavior.
27. Placeholder validation/rendering uses or delegates to PlaceholderRef/ReferenceGraph without grammar regressions.
28. placeholders.py does not import Context at runtime.
29. BranchGroupRuntime uses typed BranchResult internally or has a tested typed serialization adapter with manifest/event shape unchanged.
30. Branch manifest schema remains "botlane.branch_results/v1".
31. Provider policy resolver protocol lives in core and runtime implements it.
32. ProviderPolicyResolverProtocol is runtime_checkable if tests use isinstance.
33. Provider policy emitters preserve payloads and capability decisions.
34. ProviderTurnPlan feeds existing RenderedProviderTurn / ProviderTurnResult machinery.
35. Operation execution is unchanged unless operation parity tests prove migration safety.
36. WorkflowLocator variants preserve existing loader/catalog behavior.
37. Botlane.run and Botlane.step behavior is unchanged.
38. SingleStepPlan either remains optional behind parity tests or replaces synthetic workflow only after exact parity is proven.
39. No new internal architecture names are exported from botlane.__init__.
40. Public and semi-public dataclass positional construction remains compatible.
41. SDK persistence identity remains .botlane / .botlane-sdk-task.json / botlane.sdk_task/v1 / botlane.sdk.
```

---

# 20. Implementation style rules

Use:

```python
@dataclass(frozen=True, slots=True)
```

for immutable plan/value objects.

Use:

```python
@dataclass(slots=True)
```

for mutable runtime state such as `ExecutionFrame`.

Use:

```python
from __future__ import annotations
```

in all new modules.

Use:

```python
from typing import TypeAlias
```

for all union aliases.

Prefer:

```text
small conversion helpers
narrow protocols
compatibility adapters
phase-by-phase tests
inventory-aware identity resolution
derived route views
dependency-light value modules
plan_adapters.py for compiled-object conversion
AST-aware strictness tests
lazy imports where needed to avoid cycles
```

Avoid:

```text
new optional-field bags
broad stringly typed internals
runtime dicts except at serialization boundaries
new public API requirements
large all-at-once engine rewrite
import cycles
duplicate route metadata
parallel provider result models
unsafe artifact string parsing
```

---

# 21. Minimal first implementation milestone

The first implementation milestone should contain only:

```text
botlane/core/identifiers.py
botlane/core/run_paths.py
botlane/core/provider_policy_resolution.py
botlane/core/plan_adapters.py shell
ArtifactId tests
RunPaths/RunIdentity tests
ProviderPolicyResolverProtocol conformance update
Fixes for any existing core -> runtime imports
AST-aware strictness test for no core -> runtime imports, added only after the fix
```

It should **not** touch engine execution yet.

It should prove the refactor can begin safely without SDK/simple regressions.

Run:

```bash
python -m pytest tests/unit/test_artifact_ids.py
python -m pytest tests/unit/test_run_paths.py
python -m pytest tests/runtime/test_provider_policy_core_protocol.py
python -m pytest tests/strictness/test_core_runtime_boundary.py
python -m pytest tests/unit/test_simple_surface.py
python -m pytest tests/unit/test_sdk_facade.py
python -m pytest tests/strictness/test_no_compat.py
```

Only after that milestone passes should the agent proceed to route contracts, step plans, workflow plans, frames, branch results, provider turns, workflow locators, and optional single-step parity.

