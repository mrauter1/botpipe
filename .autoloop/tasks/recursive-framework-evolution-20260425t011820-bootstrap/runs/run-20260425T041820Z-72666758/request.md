# Standalone Implementation Plan: Pythonic Autoloop v3 Capability Upgrade + Artifact Contracts

This plan targets the current Pythonic `autoloop_v3` implementation: class-based `Workflow`, `LLMStep`, `PairStep`, `SystemStep`, `Artifact`, `Session`, `RouteContract`, package discovery, `ctx.invoke_workflow(...)`, and the strict root `workflow` authoring shim. The current code already binds produced artifact names through `produces`, exposes produced artifacts as `step.artifact_name`, validates routes and expected output payloads, and keeps workflow authoring separate from engine internals.   

The goal is to implement the missing capability layer while preserving the current Pythonic feel:

```python
class ReviewWorkflow(Workflow):
    class State(BaseModel):
        pass

    ask = LLMStep(name="ask", producer="prompts/ask.md")
    entry = ask
    transitions = {ask: {"done": SUCCESS}}
```

The framework should stay **plain Python with strong abstractions**, not a string DSL or manifest-driven workflow language. The runtime should continue to inject only narrow mechanical contracts such as route information, expected output schema, and route contracts; prompt templates remain provider-facing operational guidance. 

---

# 1. Objectives

Implement these improvements:

1. **Artifact contracts**

   * Inline step-local artifacts in `produces`.
   * Artifact factories: `Artifact.md`, `Artifact.json`, `Artifact.text`, `Artifact.raw`.
   * Artifact requiredness.
   * Artifact schema validation.
   * Runtime enforcement of `RouteContract.required_artifacts`.

2. **Default global session**

   * Every run has an implicit default run-global provider session.
   * LLM/Pair steps use it unless another session is declared.
   * Declared sessions auto-open; `ctx.open_session(...)` remains an override.

3. **Continuity model**

   * Replace session “scope” semantics with explicit `Continuity`.
   * A session is a provider conversation handle selected by a continuity policy.

4. **Typed parameters**

   * Add `ctx.params` as the typed validated `Parameters` model.
   * Preserve `ctx.workflow_params` as a JSON-safe dict.

5. **Typed routes and effects**

   * Preserve dict transitions for simple workflows.
   * Add `Route`, `SetStatus`, `Advance`, `ResetCompletion`, `Refresh`, `BoardMutation` for advanced workflows.

6. **Worklists**

   * Add Pythonic `Worklist`, `WorkItem`, `Selector`, and `Selection`.
   * Avoid Book-style `.flow("""...""")`.
   * Support scoped steps and work-item continuity.

7. **Typed child workflow contracts**

   * Preserve `ctx.invoke_workflow(...)`.
   * Add optional typed `Input` / `Output` models.

8. **Documentation and test coverage**

   * Update docs, strictness tests, runtime tests, compiler tests, and workflow examples.

---

# 2. Non-negotiable constraints

## Preserve

Preserve these existing capabilities:

```text
Workflow
Context
Session
Artifact
Prompt
RouteContract
LLMStep
PairStep
SystemStep
SUCCESS
PAUSE
FAIL
GLOBAL
ctx.invoke_workflow(...)
workflow.toml metadata-only behavior
package discovery
package CLI
expected_output_schema
available_routes
route_contracts
provider session_id / provider_metadata boundary
checkpoint/resume behavior
extension isolation
tracing
git tracking
```

## Do not introduce

Do **not** introduce:

```text
WorkflowBook as the main v3 authoring surface
string flow parser
workflow.toml execution semantics
manifest-declared topology
hidden sequencing rules
automatic fallback routing on artifact failure
generic plugin bus
public raw engine API
legacy compatibility layers
```

---

# 3. Target public API

Update the root `workflow` shim to export these authoring primitives:

```python
from workflow import (
    Artifact,
    Context,
    Continuity,
    FAIL,
    GLOBAL,
    LLMStep,
    PAUSE,
    PairStep,
    Prompt,
    Route,
    RouteContract,
    SUCCESS,
    Session,
    SystemStep,
    Workflow,
    WorkItem,
    Worklist,
    Selector,
    SetStatus,
    Advance,
    Refresh,
    ResetCompletion,
    BoardMutation,
)
```

Keep these in `workflow.primitives`:

```python
from workflow.primitives import (
    Event,
    Outcome,
    Checkpoint,
    ResolvedArtifacts,
    ChildWorkflowResult,
)
```

Do **not** export:

```python
Engine
compile_workflow
WorkflowMeta
FilesystemSessionStore
InMemorySessionStore
provider internals
runtime internals
```

---

# 4. Artifact Contract Implementation

This is the highest-priority change because the current framework already has `produces`, route contracts, and provider-facing artifact metadata, but produced artifact existence/schema validity is not enforced after a step completes.

## 4.1 Modify `core/artifacts.py`

Current `Artifact` should remain usable:

```python
report = Artifact("{workflow_folder}/report.md")
```

Extend `Artifact` with new fields:

```python
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, Mapping
from pydantic import BaseModel, ValidationError

ArtifactKind = Literal["text", "markdown", "json", "raw"]


@dataclass
class Artifact:
    template: str
    name: str | None = None
    kind: ArtifactKind = "text"
    schema: type[BaseModel] | dict[str, object] | None = None
    required: bool = False
    owner_step: str | None = None
    qualified_name: str | None = None

    @classmethod
    def text(cls, path: str, *, required: bool = False, name: str | None = None) -> "Artifact":
        return cls(path, name=name, kind="text", required=required)

    @classmethod
    def md(cls, path: str, *, required: bool = False, name: str | None = None) -> "Artifact":
        return cls(path, name=name, kind="markdown", required=required)

    @classmethod
    def json(
        cls,
        path: str,
        *,
        schema: type[BaseModel] | dict[str, object] | None = None,
        required: bool = False,
        name: str | None = None,
    ) -> "Artifact":
        return cls(path, name=name, kind="json", schema=schema, required=required)

    @classmethod
    def raw(cls, path: str, *, required: bool = False, name: str | None = None) -> "Artifact":
        return cls(path, name=name, kind="raw", required=required)

    def bind_name(self, name: str) -> None:
        if self.name is None:
            self.name = name
        elif self.name != name:
            raise ValueError(f"artifact already named {self.name!r}; cannot rename to {name!r}")

    def bind_owner(self, owner_step: str) -> None:
        self.owner_step = owner_step
        if self.name is not None:
            self.qualified_name = f"{owner_step}.{self.name}"
```

Implementation note: the current `Step.__init__` already calls `artifact.bind_name(artifact_name)` for each `produces` entry and exposes `step.artifact_name` through `__getattr__`. Preserve that behavior. 

## 4.2 Artifact identity rules

There are two artifact classes conceptually, but use one `Artifact` type:

### Class-level artifact

```python
report = Artifact("{workflow_folder}/report.md")

step = PairStep(
    name="write_report",
    produces={"report": report},
)
```

Compiler inventory:

```text
name = "report"
qualified_name = "report"
owner_step = None
producer_steps = ("write_report",)
```

### Step-local artifact

```python
step = PairStep(
    name="write_report",
    produces={
        "report": Artifact.md("report.md", required=True),
        "summary": Artifact.json("summary.json", schema=SummaryPayload, required=True),
    },
)
```

Compiler inventory:

```text
name = "report"
qualified_name = "write_report.report"
owner_step = "write_report"
producer_steps = ("write_report",)
```

The step must expose:

```python
step.report
step.summary
```

so downstream code can write:

```python
publish = SystemStep(
    name="publish",
    requires=[step.report, step.summary],
)
```

## 4.3 Compiler artifact binding

Modify `core/compiler.py`.

The compiler must:

1. Collect class-level `Artifact` declarations first.
2. Collect step `produces` artifacts.
3. Determine whether each produced artifact is class-level or step-local:

   * if artifact object identity appears as a class-level artifact, keep `owner_step=None`;
   * otherwise bind `owner_step=step.name` and `qualified_name=f"{step.name}.{local_name}"`.
4. Build a single artifact inventory.

Suggested internal record:

```python
@dataclass(frozen=True)
class ArtifactInventoryRecord:
    name: str
    qualified_name: str
    owner_step: str | None
    artifact: Artifact
    producer_steps: tuple[str, ...]
```

Suggested compiled artifact:

```python
@dataclass(frozen=True)
class CompiledArtifact:
    name: str
    qualified_name: str
    owner_step: str | None
    template: str
    kind: ArtifactKind
    schema: type[BaseModel] | dict[str, object] | None
    required: bool
    producer_steps: tuple[str, ...]
```

## 4.4 Artifact validation rules

Add compiler validation:

```text
1. duplicate class-level artifact names are rejected;
2. duplicate artifact names inside the same step are rejected;
3. duplicate qualified artifact names are rejected;
4. ambiguous unqualified artifact references are rejected;
5. requires=[plan.decision] is accepted;
6. requires=["decision"] is accepted only if unambiguous;
7. RouteContract.required_artifacts resolves against the selected step first;
8. "decision" inside plan.route_contracts resolves to "plan.decision" if produced by plan;
9. cross-step references may use "plan.decision";
10. unknown required artifact references are rejected;
11. schema must be supported;
12. schema on non-json artifacts is rejected;
13. JSON artifacts with schema must have kind="json".
```

Important resolution rule for `RouteContract.required_artifacts`:

```text
Given step "plan" and required_artifacts=("decision",):

1. if "plan.decision" exists, use that;
2. else if unqualified "decision" is globally unambiguous, use that;
3. else raise WorkflowValidationError.
```

## 4.5 Path resolution rules

Preserve existing template behavior:

```python
Artifact("{workflow_folder}/decision.json")
Artifact("{run_folder}/scratch.txt")
Artifact("{task_folder}/input.md")
```

Add new behavior only for **step-local relative artifacts**:

```python
Artifact.json("decision.json")
```

inside:

```python
plan = PairStep(
    name="plan",
    produces={"decision": Artifact.json("decision.json")},
)
```

resolves to:

```text
{workflow_folder}/plan/decision.json
```

Rules:

```text
if template is absolute:
    resolve as absolute path

elif template contains "{":
    render existing template behavior exactly

elif artifact.owner_step is not None:
    resolve as "{workflow_folder}/{owner_step}/{template}"

else:
    preserve current relative-path behavior
```

Do not change class-level relative path semantics unless tests reveal they are currently undefined. If undefined, document class-level relative artifacts as resolving under `{workflow_folder}`.

## 4.6 Artifact handles

Extend `ArtifactHandle`.

Current handlers can do:

```python
artifacts.report.read_text()
artifacts.report.write_text(...)
```

Add:

```python
handle.exists() -> bool
handle.read_json() -> object
handle.write_json(value: object) -> None
handle.read_model() -> BaseModel
handle.write_model(model_or_mapping) -> None
handle.validate() -> ArtifactValidationResult
```

Define:

```python
@dataclass(frozen=True)
class ArtifactValidationResult:
    ok: bool
    path: Path
    artifact_name: str
    errors: tuple[str, ...] = ()
```

Validation behavior:

```text
if kind is text/markdown/json and file exists but is empty:
    invalid

if kind is json:
    must parse as JSON when validating

if schema is Pydantic model:
    model.model_validate(payload)

if schema is JSON schema dict:
    support only if jsonschema is already a dependency;
    otherwise raise WorkflowValidationError at compile time
```

Minimum acceptable implementation: Pydantic-only schemas.

## 4.7 Runtime enforcement

Modify `core/engine.py`.

After a provider step returns an `Outcome`, and after existing route/payload validation, enforce artifact contracts before accepting the route as complete.

Recommended order for provider-owned steps:

```text
1. run provider step
2. validate Outcome.tag is legal
3. validate Outcome.payload against expected_output_schema
4. resolve selected route
5. run outcome handler if current engine architecture requires it before artifact validation
6. determine required artifacts
7. validate required artifact existence
8. validate schemas for required artifacts
9. validate schemas for optional produced artifacts that exist
10. checkpoint/event/advance
```

Recommended order for `SystemStep`:

```text
1. run system handler
2. get Event tag
3. resolve selected route
4. determine required artifacts
5. validate required artifact existence/schema
6. validate optional present produced artifacts
7. checkpoint/event/advance
```

If the engine currently commits state before route advancement, preserve that architecture, but artifact validation must occur before the route is considered successfully completed.

## 4.8 Determining required artifacts

For a selected route:

```text
if selected RouteContract.required_artifacts is non-empty:
    required artifacts = those route-specific artifacts
else:
    required artifacts = all produced artifacts where artifact.required is True
```

Always additionally validate optional produced artifacts that exist and have a schema.

## 4.9 Failure behavior

If a required artifact is missing, empty, or schema-invalid:

For `LLMStep` or `PairStep`:

```python
raise ProviderExecutionError(...)
```

For `SystemStep`:

```python
raise WorkflowExecutionError(...)
```

In both cases:

```text
- save checkpoint;
- include step name;
- include route tag;
- include artifact name;
- include qualified artifact name when available;
- include resolved path;
- include schema/validation error;
- do not silently route to needs_rework;
- do not invent automatic fallback routing.
```

## 4.10 Provider request enrichment

Keep current provider artifact handles.

Optionally enrich route contract payloads sent to providers with artifact contract metadata:

```json
{
  "route_contracts": {
    "ready": {
      "summary": "The summary is ready.",
      "required_artifacts": ["summary"],
      "work_item_effect": "Advances the workflow.",
      "artifact_contracts": {
        "summary": {
          "kind": "json",
          "required": true,
          "schema": {
            "title": "SummaryPayload",
            "type": "object"
          }
        }
      }
    }
  }
}
```

This is optional. Runtime validation is mandatory.

## 4.11 Artifact contract tests

Add compiler tests:

```python
def test_step_local_artifacts_bind_names_and_qualified_names(): ...
def test_step_local_artifact_access_via_step_attribute(): ...
def test_relative_step_local_artifact_resolves_under_step_folder(): ...
def test_template_step_local_artifact_resolves_as_written(): ...
def test_duplicate_step_local_artifact_names_rejected(): ...
def test_ambiguous_unqualified_artifact_reference_rejected(): ...
def test_requires_accepts_step_local_artifact_reference(): ...
def test_route_contract_required_artifact_resolves_to_step_local_output(): ...
def test_route_contract_unknown_required_artifact_rejected(): ...
def test_schema_on_non_json_artifact_rejected(): ...
```

Add runtime tests:

```python
def test_required_produced_artifact_must_exist_after_selected_route(): ...
def test_missing_required_produced_artifact_checkpoints_failure(): ...
def test_required_json_artifact_schema_validates_after_step(): ...
def test_invalid_required_json_artifact_schema_fails_and_checkpoints(): ...
def test_optional_json_artifact_absent_is_allowed(): ...
def test_optional_json_artifact_present_must_validate(): ...
def test_route_specific_required_artifacts_override_artifact_default_requiredness(): ...
def test_required_artifact_default_used_when_route_contract_has_no_required_artifacts(): ...
def test_system_step_required_output_missing_raises_workflow_execution_error(): ...
```

Add backward compatibility tests:

```python
def test_existing_class_level_artifact_produces_still_works(): ...
def test_existing_unrequired_produces_does_not_force_file_existence(): ...
def test_expected_output_schema_still_validates_only_outcome_payload(): ...
def test_produces_still_exposes_artifact_handles_to_provider(): ...
```

---

# 5. Session Upgrade

The current implementation still exposes `SessionPaths` as a workflow extension and tests manual `ctx.open_session(...)` behavior. This should be changed because the session path strategy is storage infrastructure, not workflow behavior. 

## 5.1 New session model

Create `core/sessions.py`.

Implement:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from .context import Context
    from .worklists import Worklist


@dataclass(frozen=True, slots=True)
class Continuity:
    kind: Literal["run", "task", "work_item", "fresh", "key"]
    worklist_name: str | None = None
    key_fn: Callable[["Context"], str] | None = None

    @staticmethod
    def run() -> "Continuity":
        return Continuity("run")

    @staticmethod
    def task() -> "Continuity":
        return Continuity("task")

    @staticmethod
    def work_item(worklist: "Worklist | str") -> "Continuity":
        name = worklist if isinstance(worklist, str) else worklist.name
        return Continuity("work_item", worklist_name=name)

    @staticmethod
    def fresh() -> "Continuity":
        return Continuity("fresh")

    @staticmethod
    def key(fn: Callable[["Context"], str]) -> "Continuity":
        return Continuity("key", key_fn=fn)
```

Modify `Session`:

```python
class Session:
    __slots__ = ("name", "continuity", "_order")

    def __init__(self, *, continuity: Continuity | None = None) -> None:
        self.name: str | None = None
        self.continuity = continuity or Continuity.run()
        self._order = next(_SESSION_COUNTER)
```

## 5.2 Default session

Add:

```python
DEFAULT_SESSION_NAME = "default"
```

Compiler rule:

```text
Every compiled workflow has an implicit Session(name="default", continuity=Continuity.run()).
```

Step rule:

```text
LLMStep(session=None) uses default session.
PairStep(session=None) uses default session.
SystemStep uses no provider session.
```

Runtime rule:

```text
Every run creates or lazily opens the default session before the first provider step.
```

## 5.3 Auto-open sessions

Change old behavior:

```text
declared session missing binding -> error
```

to new behavior:

```text
declared session missing binding -> auto-open using its Continuity
```

Keep:

```python
ctx.open_session(...)
```

as an explicit override.

## 5.4 SessionKey

Add:

```python
@dataclass(frozen=True, slots=True)
class SessionKey:
    slot: str
    continuity_kind: str
    continuity_id: str
```

Examples:

```text
default/run/<run_id>
planner/run/<run_id>
reviewer/task/<task_id>
worker/work_item/<worklist>:<item_id>
scratch/fresh/<uuid>
custom/key/<safe-key>
```

## 5.5 Store protocol

Update `core/stores/protocols.py`:

```python
class SessionStore(Protocol):
    def get(self, key: SessionKey) -> SessionBinding | None: ...
    def open(self, key: SessionKey) -> SessionBinding: ...
    def upsert(self, binding: SessionBinding) -> None: ...
    def snapshot(self) -> SessionSnapshot: ...
    def restore(self, snapshot: SessionSnapshot) -> None: ...
```

`SessionBinding`:

```python
@dataclass(frozen=True, slots=True)
class SessionBinding:
    key: SessionKey
    session_id: str | None
    provider: str
    provider_metadata: Mapping[str, object]
```

## 5.6 Remove workflow-facing `SessionPaths`

Remove `SessionPaths` from:

```text
extensions/session_paths.py
extensions/__init__.py
docs/authoring.md
docs/architecture.md
workflow-facing examples
```

If internal path customization is needed, move it to runtime:

```python
class SessionPathResolver(Protocol):
    def path_for(self, key: SessionKey, folders: SessionFolders) -> Path: ...
```

## 5.7 Session tests

Add:

```python
def test_default_global_session_is_created_for_every_run(): ...
def test_llm_step_without_session_uses_default_session(): ...
def test_pair_step_without_session_uses_default_session(): ...
def test_declared_session_auto_opens_without_on_start(): ...
def test_open_session_still_overrides_active_binding(): ...
def test_work_item_continuity_uses_current_work_item_key(): ...
def test_fresh_continuity_rotates_session_key(): ...
def test_session_paths_extension_is_not_exported(): ...
```

Delete or rewrite:

```python
test_missing_session_binding_fails_instead_of_auto_opening
```

Expected new behavior: declared sessions auto-open.

---

# 6. Typed Parameters

## 6.1 Goal

Expose validated workflow parameters as a typed object:

```python
ctx.params.mode
```

while preserving:

```python
ctx.workflow_params["mode"]
```

## 6.2 Implementation

Modify `core/context.py`.

Add:

```python
@property
def params(self) -> BaseModel:
    return self._params
```

Context constructor should receive:

```python
params: BaseModel
workflow_params: Mapping[str, object]
```

If no `Parameters` model exists:

```python
class EmptyParameters(BaseModel):
    model_config = ConfigDict(frozen=True)
```

## 6.3 Runner behavior

At run start:

```text
1. parse -wf values;
2. validate with package Parameters model if present;
3. persist normalized JSON-safe params in run metadata;
4. pass both typed params and dict params into Context.
```

At resume:

```text
1. load persisted params from run metadata;
2. rebuild typed params;
3. ignore new parameter overrides for existing run.
```

## 6.4 Tests

```python
def test_context_exposes_typed_params(): ...
def test_context_workflow_params_dict_remains_available(): ...
def test_resume_restores_typed_params(): ...
def test_missing_parameters_model_returns_empty_params(): ...
```

---

# 7. Typed Routes and Effects

## 7.1 Goal

Keep simple workflows simple:

```python
transitions = {ask: {"done": SUCCESS}}
```

Add advanced Pythonic transition objects:

```python
transitions = {
    assess: {
        "passed": Route.to(next_step, SetStatus(gates, "completed"), Advance(gates)),
        "needs_rework": Route.to(assess, ResetCompletion(gates)),
    }
}
```

## 7.2 Add `core/routes.py`

```python
@dataclass(frozen=True, slots=True)
class Route:
    target: Step | str | None = None
    effects: tuple[Effect, ...] = ()

    @staticmethod
    def to(target: Step | str, *effects: Effect) -> "Route": ...

    @staticmethod
    def complete(*effects: Effect) -> "Route": ...

    @staticmethod
    def pause(*effects: Effect) -> "Route": ...

    @staticmethod
    def fail(*effects: Effect) -> "Route": ...
```

## 7.3 Add `core/effects.py`

```python
class Effect(Protocol):
    pass


@dataclass(frozen=True, slots=True)
class Refresh:
    worklist: Worklist | str


@dataclass(frozen=True, slots=True)
class ResetCompletion:
    worklist: Worklist | str


@dataclass(frozen=True, slots=True)
class SetStatus:
    worklist: Worklist | str
    status: str


@dataclass(frozen=True, slots=True)
class Advance:
    worklist: Worklist | str
    if_exhausted: Literal["complete", "pause", "fail", "route"] = "complete"
    route_to: Step | str | None = None


@dataclass(frozen=True, slots=True)
class BoardMutation:
    worklist: Worklist | str
    kind: Literal[
        "split_active_work_item",
        "reprioritize_remaining_work_items",
        "retire_active_work_item",
    ]
```

## 7.4 Compiler normalization

Normalize all transition values into:

```python
@dataclass(frozen=True, slots=True)
class CompiledRoute:
    source_step: str
    tag: str
    target: str | Terminal | None
    effects: tuple[Effect, ...]
```

Rules:

```text
Step destination -> Route.to(step)
SUCCESS -> Route.complete()
PAUSE -> Route.pause()
FAIL -> Route.fail()
Route -> compile directly
```

## 7.5 Tests

```python
def test_dict_transition_shorthand_still_works(): ...
def test_route_object_to_step_compiles(): ...
def test_route_complete_with_effects_compiles(): ...
def test_invalid_effect_worklist_reference_rejected(): ...
def test_advance_route_to_requires_target_when_if_exhausted_route(): ...
```

---

# 8. Worklists and Work Items

## 8.1 Goal

Recover the useful named-scope/work-item capability from the broader Book Architecture, but expose it as plain Python objects.

## 8.2 Add `core/worklists.py`

```python
@dataclass(frozen=True, slots=True)
class WorkItem(Generic[T]):
    id: str
    title: str
    payload: T
    status: str | None = None
    dir_key: str | None = None


@dataclass(frozen=True, slots=True)
class Selector:
    item_param: str | None = None
    mode_param: str | None = None
    default_mode: Literal["all", "single", "up_to"] = "all"
    allowed_modes: tuple[str, ...] = ("all",)


@dataclass(frozen=True, slots=True)
class Selection(Generic[T]):
    worklist_name: str
    mode: str
    items: tuple[WorkItem[T], ...]
    explicit: bool
    current_index: int = 0

    @property
    def current(self) -> WorkItem[T] | None:
        ...
```

```python
class WorklistSource(Protocol[T]):
    def load(self, ctx: Context) -> Sequence[T]: ...
    def save(self, ctx: Context, items: Sequence[T]) -> None: ...
    def validate(self, ctx: Context, items: Sequence[T]) -> str | None: ...
```

```python
@dataclass(frozen=True, slots=True)
class Worklist(Generic[T]):
    name: str
    source: WorklistSource[T]
    selector: Selector = Selector()

    @classmethod
    def from_items(cls, name: str, items: Sequence[T], ...): ...

    @classmethod
    def from_artifact(
        cls,
        name: str,
        artifact: Artifact,
        *,
        collection: str,
        item_id: str,
        title: str,
        status: str | None = None,
        selector: Selector = Selector(),
    ) -> "Worklist":
        ...
```

## 8.3 Step scoping

Extend `LLMStep` and `PairStep`:

```python
PairStep(..., scope=gates)
LLMStep(..., scope=gates)
```

Rules:

```text
scope=None means run-global;
scope=Worklist means current work item;
engine does not loop automatically;
progression occurs through Advance(worklist).
```

## 8.4 Context APIs

Add:

```python
ctx.selection(worklist_or_name) -> Selection
ctx.current(worklist_or_name) -> WorkItem | None
ctx.item -> WorkItem | None
```

## 8.5 Artifact placeholders

Support:

```text
{item.id}
{item.dir_key}
{worklist.<name>.current.id}
{worklist.<name>.current.dir_key}
```

## 8.6 Tests

```python
def test_worklist_from_artifact_selects_all_items(): ...
def test_selector_single_item_from_params(): ...
def test_scoped_step_receives_current_item(): ...
def test_artifact_template_can_use_item_dir_key(): ...
def test_advance_moves_to_next_item(): ...
def test_advance_completes_when_exhausted(): ...
```

---

# 9. Typed Child Workflow Contracts

## 9.1 Workflow conventions

A workflow may declare:

```python
class Input(BaseModel):
    ...


class Output(BaseModel):
    ...


@staticmethod
def build_output(state: State, ctx: Context) -> Output:
    ...
```

## 9.2 `ctx.invoke_workflow(...)`

Preserve:

```python
ctx.invoke_workflow("child_workflow", message="...", parameters={...})
ctx.invoke_workflow(ChildWorkflow, message="...", parameters={...})
```

Add:

```python
ctx.invoke_workflow(ChildWorkflow, input=ChildWorkflow.Input(...))
```

## 9.3 Child result

Extend `ChildWorkflowResult`:

```python
@dataclass(frozen=True, slots=True)
class ChildWorkflowResult(Generic[T]):
    workflow_name: str
    run_id: str
    terminal: str
    status: str
    output: T | None
    task_folder: Path
    workflow_folder: Path
    run_folder: Path
    package_folder: Path
    artifacts: Mapping[str, Path]
    metadata: Mapping[str, object]
```

Do not remove existing fields.

## 9.4 Tests

```python
def test_invoke_workflow_with_typed_input(): ...
def test_child_result_exposes_typed_output(): ...
def test_child_result_preserves_low_level_metadata(): ...
def test_child_typed_output_validation_failure_is_recorded(): ...
```

---

# 10. Compiler Implementation Order

Update compiler in this order:

1. Extend `Artifact` fields and factories.
2. Preserve `Step.__getattr__` artifact access.
3. Collect class-level artifacts.
4. Collect step-local artifacts.
5. Build artifact inventory with qualified names.
6. Normalize `requires`.
7. Resolve `RouteContract.required_artifacts`.
8. Add default session.
9. Compile session continuity.
10. Compile worklists.
11. Normalize routes into `CompiledRoute`.
12. Validate route/effect/worklist/artifact references.
13. Preserve deterministic compile cache.

Add compiler tests before engine tests.

---

# 11. Engine Implementation Order

Update engine in this order:

1. Add default session creation.
2. Auto-open step session.
3. Add typed `ctx.params`.
4. Add artifact validation utilities.
5. Validate `requires` before step execution as today.
6. Validate provider `Outcome.tag`.
7. Validate `Outcome.payload`.
8. Resolve selected route.
9. Run handler according to existing engine order.
10. Validate selected route artifacts.
11. Validate optional present produced artifacts.
12. Execute route effects.
13. Save checkpoint/event.
14. Advance target.

Failure checkpoint must include:

```text
step name
route tag
state snapshot
session snapshot
artifact validation error
worklist selection state if present
```

---

# 12. Runtime / Store Implementation

## 12.1 Filesystem session store

Update constructor:

```python
FilesystemSessionStore(
    *,
    task_folder: Path,
    workflow_folder: Path,
    run_folder: Path,
    provider: str,
)
```

Path policy:

```text
run continuity:
  <run_folder>/sessions/<slot>.json

task continuity:
  <workflow_folder>/sessions/task/<slot>.json

work-item continuity:
  <workflow_folder>/sessions/work_items/<worklist>/<item_dir_key>/<slot>.json

key continuity:
  <workflow_folder>/sessions/keys/<slot>/<safe_key>.json

fresh continuity:
  <run_folder>/sessions/fresh/<slot>/<uuid>.json
```

Default:

```text
<run_folder>/sessions/default.json
```

## 12.2 Run metadata

Add:

```json
{
  "default_session": "default",
  "session_policy_version": 1,
  "worklists": {}
}
```

Preserve existing metadata.

---

# 13. Documentation Updates

Update `docs/authoring.md`.

Required sections:

```text
Default session
Continuity
Typed params
Artifact declarations
Class-level artifacts
Step-local artifacts
Relative step-local paths
Artifact schemas
Artifact requiredness
Route-specific required artifacts
Difference between produces and requires
Difference between expected_output_schema and artifact schema
Typed routes/effects
Worklists
Child workflow typed outputs
```

Include this artifact example:

```python
class Summary(BaseModel):
    summary: str
    ready: bool


class Review(Workflow):
    class State(BaseModel):
        summary: str = ""

    draft = PairStep(
        name="draft",
        producer="prompts/draft_producer.md",
        verifier="prompts/draft_verifier.md",
        produces={
            "summary": Artifact.json("summary.json", schema=Summary, required=True),
            "report": Artifact.md("report.md", required=True),
        },
        route_contracts={
            "ready": RouteContract(
                summary="The report and summary are ready.",
                required_artifacts=("summary", "report"),
            )
        },
    )

    publish = SystemStep(
        name="publish",
        requires=[draft.summary, draft.report],
    )
```

Update `docs/architecture.md`.

State explicitly:

```text
workflow.toml remains metadata-only.
Session pathing is runtime store infrastructure, not a workflow extension.
The runtime does not implement a flow-string DSL.
Route/effect objects are Python objects.
```

---

# 14. Test Suite Plan

## Unit tests

```text
tests/unit/test_artifacts.py
tests/unit/test_sessions.py
tests/unit/test_routes.py
tests/unit/test_worklists.py
tests/unit/test_validation.py
```

## Contract tests

```text
tests/contract/test_engine_contracts.py
tests/contract/test_artifact_contracts.py
tests/contract/test_session_contracts.py
tests/contract/test_route_effect_contracts.py
```

## Runtime tests

```text
tests/runtime/test_package_cli.py
tests/runtime/test_workspace_and_context.py
tests/runtime/test_workflow_reference_resolution.py
tests/runtime/test_provider_backends.py
```

## Strictness tests

Update strictness tests to ensure:

```text
workflow exports new authoring primitives
workflow does not export engine/compiler internals
SessionPaths is not exported from extensions
workflow.toml remains metadata-only
no flow-string DSL appears in v3 authoring docs
```

---

# 15. Concrete Implementation Sequence for Codex CLI

Run each phase with tests before proceeding.

## Phase 1: Artifact model

```text
- update core/artifacts.py
- add factories
- add validation result type
- add artifact handle helpers
- update Step produces binding only as needed
- add unit tests
```

Run:

```bash
pytest -q tests/unit/test_validation.py tests/contract/test_engine_contracts.py -k artifact
```

## Phase 2: Compiler artifact inventory

```text
- collect class-level artifacts
- collect step-local artifacts
- qualified names
- route required artifact resolution
- schema validation
- ambiguous reference validation
```

Run:

```bash
pytest -q tests/unit/test_validation.py
```

## Phase 3: Runtime artifact enforcement

```text
- enforce RouteContract.required_artifacts
- enforce Artifact.required
- validate optional present schema artifacts
- checkpoint on failure
- preserve expected_output_schema behavior
```

Run:

```bash
pytest -q tests/contract/test_engine_contracts.py
```

## Phase 4: Sessions

```text
- add Continuity
- add default session
- auto-open provider sessions
- update memory/filesystem stores
- remove SessionPaths extension export
```

Run:

```bash
pytest -q tests/unit/test_primitives_and_stores.py tests/contract/test_engine_contracts.py tests/runtime/test_workspace_and_context.py
```

## Phase 5: `ctx.params`

```text
- typed params model
- resume persistence
- docs/tests
```

Run:

```bash
pytest -q tests/runtime/test_package_cli.py tests/runtime/test_workspace_and_context.py
```

## Phase 6: Routes/effects

```text
- add Route and effects
- normalize dict routes and object routes
- execute effects
- add tests
```

Run:

```bash
pytest -q tests/unit/test_validation.py tests/contract/test_engine_contracts.py
```

## Phase 7: Worklists

```text
- add Worklist/WorkItem/Selector/Selection
- add scoped steps
- add context APIs
- add artifact placeholders
- add Advance effect behavior
```

Run:

```bash
pytest -q tests/contract/test_engine_contracts.py tests/runtime
```

## Phase 8: Child workflow typed IO

```text
- Input/Output conventions
- build_output
- typed ChildWorkflowResult.output
- preserve low-level metadata
```

Run:

```bash
pytest -q tests/runtime/test_workspace_and_context.py tests/runtime/test_package_cli.py
```

## Phase 9: Docs and full regression

```bash
pytest -q
```

---

# 16. Acceptance Criteria

The implementation is complete when all are true:

1. Existing workflows compile and run.
2. Existing `Artifact("{workflow_folder}/x.md")` still works.
3. Existing `produces={"x": artifact}` still provides writable handles.
4. Step-local artifacts can be declared inline.
5. Step-local artifacts are accessible as `step.artifact_name`.
6. Step-local relative paths resolve under `{workflow_folder}/{step_name}/`.
7. Explicit artifact templates resolve exactly as before.
8. `Artifact.json(..., schema=Model)` validates content.
9. `required=True` enforces existence and schema validity.
10. `RouteContract.required_artifacts` is enforced at runtime.
11. Optional absent artifacts do not fail.
12. Optional present schema artifacts validate.
13. Missing/invalid required artifacts fail with checkpoint.
14. `expected_output_schema` validates only `Outcome.payload`.
15. Every run has a default provider session.
16. LLM/Pair steps without sessions use default session.
17. Declared sessions auto-open.
18. `ctx.open_session(...)` still works.
19. `Continuity` replaces session-scope semantics.
20. `SessionPaths` is no longer workflow-facing.
21. `ctx.params` exposes typed parameters.
22. `ctx.workflow_params` remains available.
23. Dict transitions still work.
24. `Route` objects work.
25. Route effects work.
26. Worklists can drive scoped steps.
27. Child workflows can return typed outputs.
28. `workflow.toml` remains metadata-only.
29. Root `workflow` shim exports only authoring primitives.
30. Full `pytest` passes.

---

# 17. Final Design Rule

Keep the mental model simple:

```text
requires
  required inputs before the step runs

produces
  named writable outputs owned by the step

Artifact.schema
  validates artifact file content

Artifact.required
  default output requirement

RouteContract.required_artifacts
  route-specific output requirement

expected_output_schema
  validates provider Outcome.payload, not files

Session
  named provider conversation slot

Continuity
  policy for reusing/rotating the provider conversation

Route
  Python object describing target + effects

Worklist
  Python object describing repeated scoped work
```

The final result should feel like **plain Python**, but with abstractions strong enough to express real workflow contracts directly in code.
