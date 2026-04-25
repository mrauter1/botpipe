Below is the revised, complete, standalone implementation plan. It incorporates the earlier v3 improvements, the artifact-contract improvement plan, and the correction that **`ctx.open_session(..., scope=...)` remains valid and supported**.

# Autoloop v3 Pythonic Capability Upgrade Plan

## 0. Review of the updated design

The previous plan needed one important correction:

**`ctx.open_session(..., scope=...)` must stay valid.**

The correct model is not “remove scope.” The correct model is:

```text
Session
  provider conversation slot

Continuity
  default policy for how the slot chooses/reuses a provider conversation

ctx.open_session(..., scope=...)
  explicit runtime override that binds a slot to a named logical scope key
```

So the final design keeps all three:

```python
# Common case: implicit default run-global session.
ask = LLMStep(name="ask", producer="prompts/ask.md")

# Declarative default policy.
worker = Session(continuity=Continuity.work_item("gate"))

# Explicit runtime override.
ctx.open_session(self.worker, scope="cluster-1")
```

This plan also preserves the current good v3 foundation: class-based `Workflow`, root `workflow` authoring shim, `LLMStep`, `PairStep`, `SystemStep`, `Artifact`, `RouteContract`, `ctx.invoke_workflow(...)`, package discovery, and narrow runtime/provider contracts. The current implementation already has a simple `Artifact` model, `ArtifactHandle.read_text/write_text/exists`, step `produces` binding, step-local artifact attribute access through `Step.__getattr__`, `ctx.open_session(ref, scope=None)`, and route contract metadata including `required_artifacts`.    

---

# 1. Mission

Upgrade the current Pythonic `autoloop_v3` framework so it supports stronger workflow contracts while preserving the simple authoring style.

Simple workflows should still look like this:

```python
from pydantic import BaseModel

from workflow import LLMStep, SUCCESS, Workflow


class AskWorkflow(Workflow):
    class State(BaseModel):
        answer: str | None = None

    ask = LLMStep(name="ask", producer="prompts/ask.md")

    entry = ask
    transitions = {ask: {"answered": SUCCESS}}
```

Advanced workflows should be expressible with ordinary Python objects, not a string DSL:

```python
from pydantic import BaseModel

from workflow import (
    Advance,
    Artifact,
    Continuity,
    PairStep,
    Route,
    RouteContract,
    Session,
    SetStatus,
    SUCCESS,
    Workflow,
    Worklist,
)


class SummaryPayload(BaseModel):
    summary: str
    ready: bool


class ReviewWorkflow(Workflow):
    class State(BaseModel):
        pass

    gate_board = Artifact.json(
        "{workflow_folder}/gates.json",
        schema=GateBoard,
        required=True,
    )

    gates = Worklist.from_artifact(
        name="gate",
        artifact=gate_board,
        collection="gates",
        item_id="gate_id",
        title="title",
        status="status",
    )

    gate_session = Session(continuity=Continuity.work_item(gates))

    assess = PairStep(
        name="assess",
        producer="prompts/assess_producer.md",
        verifier="prompts/assess_verifier.md",
        session=gate_session,
        scope=gates,
        produces={
            "summary": Artifact.json("summary.json", schema=SummaryPayload, required=True),
            "report": Artifact.md("report.md", required=True),
        },
        route_contracts={
            "passed": RouteContract(
                summary="Gate assessment passed.",
                required_artifacts=("summary", "report"),
            )
        },
    )

    entry = assess

    transitions = {
        assess: {
            "passed": Route.to(
                SUCCESS,
                SetStatus(gates, "completed"),
                Advance(gates),
            )
        }
    }
```

---

# 2. Non-negotiable constraints

## 2.1 Preserve

Preserve these existing concepts and behaviors:

```text
Workflow
Context
Session
Artifact
Prompt
RouteContract
PairStep
LLMStep
SystemStep
SUCCESS
PAUSE
FAIL
GLOBAL
ctx.invoke_workflow(...)
ctx.open_session(..., scope=...)
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
existing produces/requires behavior
existing ArtifactHandle.read_text/write_text behavior
```

## 2.2 Do not introduce

Do not introduce:

```text
WorkflowBook as the main v3 authoring surface
string flow parser
workflow.toml execution semantics
manifest-declared topology
hidden sequencing rules
automatic fallback routing on artifact validation failure
generic plugin bus
public raw engine API
legacy compatibility imports
provider-specific workflow APIs
```

## 2.3 Breaking changes

Breaking changes are allowed if they simplify the framework or fix the model, but **functionality regressions are not allowed**.

That means:

* `ctx.open_session(self.slot, scope="x")` remains valid.
* Existing `produces={"name": artifact}` remains valid.
* Existing `requires=[artifact]` remains valid.
* Existing `RouteContract.required_artifacts` remains valid, but now gains runtime enforcement.
* Existing workflows without artifact requiredness should not suddenly fail.
* Existing provider/request/checkpoint behavior should continue to work unless explicitly upgraded.

---

# 3. Target public API

Update the root `workflow` shim to export only authoring-facing primitives.

```python
from workflow import (
    # Core authoring
    Workflow,
    Context,
    Session,
    Continuity,
    Artifact,
    Prompt,

    # Steps
    PairStep,
    LLMStep,
    SystemStep,

    # Routing
    Route,
    RouteContract,
    SUCCESS,
    PAUSE,
    FAIL,
    GLOBAL,

    # Effects
    SetStatus,
    Advance,
    Refresh,
    ResetCompletion,
    BoardMutation,

    # Work items
    WorkItem,
    Worklist,
    Selector,
)
```

Keep low-level runtime values under `workflow.primitives`:

```python
from workflow.primitives import (
    Event,
    Outcome,
    Checkpoint,
    ResolvedArtifacts,
    ChildWorkflowResult,
)
```

Do not export these from `workflow`:

```text
Engine
compile_workflow
WorkflowMeta
FilesystemSessionStore
InMemorySessionStore
provider internals
runtime internals
store internals
```

---

# 4. Artifact Contract Upgrade

## 4.1 Goal

Upgrade `Artifact` and `produces` so steps can declare output artifacts inline, with optional schema validation and required-output enforcement.

Preserve current style:

```python
report = Artifact("{workflow_folder}/report.md")

step = PairStep(
    name="write_report",
    producer="prompts/write_report_producer.md",
    verifier="prompts/write_report_verifier.md",
    produces={"report": report},
)
```

Add compact step-local artifacts:

```python
step = PairStep(
    name="write_report",
    producer="prompts/write_report_producer.md",
    verifier="prompts/write_report_verifier.md",
    produces={
        "report": Artifact.md("report.md", required=True),
        "summary": Artifact.json("summary.json", schema=SummaryPayload, required=True),
    },
)
```

## 4.2 Mental model

```text
requires
  artifacts that must already exist before the step runs

produces
  writable artifacts owned by the step

Artifact.schema
  validates artifact file content

Artifact.required
  default output requirement for successful completion

RouteContract.required_artifacts
  route-specific output requirement

expected_output_schema
  validates provider Outcome.payload, not artifact files
```

## 4.3 Modify `core/artifacts.py`

Replace or extend the current `Artifact` class.

Current implementation has only `template`, `name`, and `owner`. Extend it to:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ValidationError


ArtifactKind = Literal["text", "markdown", "json", "raw"]


class Artifact:
    """Artifact declaration."""

    __slots__ = (
        "template",
        "name",
        "kind",
        "schema",
        "required",
        "owner",
        "owner_step",
        "qualified_name",
    )

    def __init__(
        self,
        template: str,
        name: str | None = None,
        *,
        kind: ArtifactKind = "text",
        schema: type[BaseModel] | dict[str, object] | None = None,
        required: bool = False,
        owner: object | None = None,
        owner_step: str | None = None,
        qualified_name: str | None = None,
    ) -> None:
        self.template = template
        self.name = name
        self.kind = kind
        self.schema = schema
        self.required = required
        self.owner = owner
        self.owner_step = owner_step
        self.qualified_name = qualified_name

    @classmethod
    def text(
        cls,
        path: str,
        *,
        required: bool = False,
        name: str | None = None,
    ) -> "Artifact":
        return cls(path, name=name, kind="text", required=required)

    @classmethod
    def md(
        cls,
        path: str,
        *,
        required: bool = False,
        name: str | None = None,
    ) -> "Artifact":
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
    def raw(
        cls,
        path: str,
        *,
        required: bool = False,
        name: str | None = None,
    ) -> "Artifact":
        return cls(path, name=name, kind="raw", required=required)

    def bind_name(self, name: str) -> None:
        if self.name is None:
            self.name = name
        elif self.name != name:
            raise ValueError(f"artifact already named {self.name!r}; cannot rename to {name!r}")

    def bind_owner_step(self, step_name: str) -> None:
        self.owner_step = step_name
        if self.name is None:
            raise ValueError("cannot bind owner step before artifact name is bound")
        self.qualified_name = f"{step_name}.{self.name}"

    def __repr__(self) -> str:
        return (
            f"Artifact(template={self.template!r}, name={self.name!r}, "
            f"kind={self.kind!r}, required={self.required!r}, "
            f"qualified_name={self.qualified_name!r})"
        )
```

Minimum schema support:

```text
Pydantic BaseModel class
None
```

Optional later support:

```text
raw JSON schema dict, only if jsonschema is already an accepted dependency
```

If `schema` is a dict and `jsonschema` is not installed or not intended as a dependency, reject it at compile time with `WorkflowValidationError`.

## 4.4 Artifact requiredness

Add `required`.

Default:

```python
required=False
```

Reason:

* Existing workflows should not suddenly fail.
* Route-specific requiredness is more precise.
* Existing `produces` declarations are often provider-visible writable handles but not always mandatory outputs.

Semantics:

```text
required=True
  artifact must exist and validate after successful route selection unless route-specific required_artifacts overrides.

required=False
  artifact may be absent; if present and schema exists, validate it.
```

## 4.5 Step-local artifact declarations

Allow:

```python
plan = PairStep(
    name="plan",
    producer="prompts/plan_producer.md",
    verifier="prompts/plan_verifier.md",
    produces={
        "decision": Artifact.json("decision.json", schema=Decision, required=True),
        "brief": Artifact.md("brief.md", required=True),
    },
)
```

Compiler binds:

```text
artifact.name = "decision"
artifact.owner_step = "plan"
artifact.qualified_name = "plan.decision"
```

The step exposes:

```python
plan.decision
plan.brief
```

Downstream style:

```python
publish = SystemStep(
    name="publish",
    requires=[plan.decision, plan.brief],
)
```

The current `Step.__getattr__` already supports returning artifacts from `produces`; preserve that behavior and extend it only as needed. 

## 4.6 Path resolution rules

Preserve existing template behavior:

```python
Artifact("{workflow_folder}/decision.json")
Artifact("{run_folder}/scratch.txt")
Artifact("{task_folder}/input.md")
```

Add step-local relative path behavior:

```python
plan = PairStep(
    name="plan",
    produces={"decision": Artifact.json("decision.json")}
)
```

resolves to:

```text
{workflow_folder}/plan/decision.json
```

Resolution algorithm:

```python
def resolve_artifact_template(artifact: Artifact, context: Context) -> Path:
    template = artifact.template
    candidate = Path(template)

    if candidate.is_absolute():
        return candidate

    if "{" in template and "}" in template:
        return render_existing_template(template, context)

    if artifact.owner_step is not None:
        return context.workflow_folder / artifact.owner_step / template

    # Preserve current behavior for class-level relative paths.
    return render_existing_template(template, context)
```

If current class-level relative behavior is ambiguous, define it explicitly as:

```text
Class-level relative artifact path resolves under workflow_folder.
```

## 4.7 Artifact inventory

Compiler should normalize class-level and step-local artifacts into one inventory.

```python
@dataclass(frozen=True)
class ArtifactInventoryRecord:
    name: str
    qualified_name: str
    owner_step: str | None
    artifact: Artifact
    producer_steps: tuple[str, ...]
```

For class-level artifact:

```text
name = "decision"
qualified_name = "decision"
owner_step = None
```

For step-local artifact:

```text
name = "decision"
qualified_name = "plan.decision"
owner_step = "plan"
```

## 4.8 Validation rules

Add compiler validation:

```text
1. duplicate class-level artifact names rejected;
2. duplicate artifact names inside the same step rejected;
3. duplicate qualified names rejected;
4. ambiguous unqualified artifact references rejected;
5. requires=[plan.decision] accepted;
6. requires=["decision"] accepted only if unambiguous;
7. RouteContract.required_artifacts must reference known artifacts;
8. RouteContract.required_artifacts resolves step-local names first;
9. cross-step route references may use "plan.decision";
10. unknown route-required artifacts rejected;
11. artifact schemas must be supported schema objects;
12. JSON artifacts with schemas must have kind="json";
13. schema on text/markdown/raw artifacts rejected.
```

Route contract artifact resolution:

```text
Given selected step "plan" and required_artifacts=("decision",):

1. If "plan.decision" exists, resolve to it.
2. Else if unqualified "decision" is globally unambiguous, resolve to it.
3. Else raise WorkflowValidationError.
```

## 4.9 Artifact handle changes

Current `ArtifactHandle` has `read_text`, `write_text`, `append`, and `exists`. Extend it. 

```python
@dataclass(frozen=True, slots=True)
class ArtifactValidationResult:
    ok: bool
    path: Path
    artifact_name: str
    qualified_name: str | None = None
    errors: tuple[str, ...] = ()
```

Extend `ArtifactHandle`:

```python
@dataclass(frozen=True, slots=True)
class ArtifactHandle:
    name: str
    path: Path
    artifact: Artifact | None = None

    def read_text(self) -> str: ...

    def write_text(self, content: str) -> None: ...

    def append(self, content: str) -> None: ...

    def exists(self) -> bool: ...

    def read_json(self) -> object:
        return json.loads(self.read_text())

    def write_json(self, value: object) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def read_model(self) -> BaseModel:
        if self.artifact is None or self.artifact.schema is None:
            raise TypeError("artifact has no schema")
        if not isinstance(self.artifact.schema, type) or not issubclass(self.artifact.schema, BaseModel):
            raise TypeError("read_model only supports Pydantic BaseModel schemas")
        payload = self.read_json()
        return self.artifact.schema.model_validate(payload)

    def write_model(self, model_or_mapping: BaseModel | Mapping[str, object]) -> None:
        if isinstance(model_or_mapping, BaseModel):
            self.write_json(model_or_mapping.model_dump(mode="json"))
        else:
            self.write_json(dict(model_or_mapping))

    def validate(self) -> ArtifactValidationResult:
        return validate_artifact_handle(self)
```

## 4.10 Runtime artifact validation

Add a validation helper:

```python
def validate_artifact_handle(handle: ArtifactHandle) -> ArtifactValidationResult:
    artifact = handle.artifact
    errors: list[str] = []

    if artifact is None:
        return ArtifactValidationResult(ok=True, path=handle.path, artifact_name=handle.name)

    if not handle.path.exists():
        if artifact.required:
            errors.append("artifact file does not exist")
        return ArtifactValidationResult(
            ok=not errors,
            path=handle.path,
            artifact_name=handle.name,
            qualified_name=artifact.qualified_name,
            errors=tuple(errors),
        )

    if artifact.kind in {"text", "markdown", "json"}:
        text = handle.path.read_text(encoding="utf-8")
        if not text.strip():
            errors.append("artifact file is empty")
            return ArtifactValidationResult(
                ok=False,
                path=handle.path,
                artifact_name=handle.name,
                qualified_name=artifact.qualified_name,
                errors=tuple(errors),
            )

    if artifact.kind == "json" or artifact.schema is not None:
        try:
            payload = json.loads(handle.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON: {exc.msg}")
            return ArtifactValidationResult(
                ok=False,
                path=handle.path,
                artifact_name=handle.name,
                qualified_name=artifact.qualified_name,
                errors=tuple(errors),
            )

        if artifact.schema is not None:
            if isinstance(artifact.schema, type) and issubclass(artifact.schema, BaseModel):
                try:
                    artifact.schema.model_validate(payload)
                except ValidationError as exc:
                    errors.append(str(exc))
            elif isinstance(artifact.schema, dict):
                errors.append("raw JSON schema dict validation is not implemented")
            else:
                errors.append(f"unsupported schema type: {type(artifact.schema).__name__}")

    return ArtifactValidationResult(
        ok=not errors,
        path=handle.path,
        artifact_name=handle.name,
        qualified_name=artifact.qualified_name,
        errors=tuple(errors),
    )
```

## 4.11 Runtime enforcement order

After provider/system step execution and route selection, validate artifacts before the route is considered successful.

Recommended provider-owned step order:

```text
1. run provider step
2. validate Outcome.tag is legal
3. validate Outcome.payload against expected_output_schema
4. resolve selected route
5. run step handler if present
6. determine required artifacts for selected route
7. validate required artifact existence
8. validate schemas for required artifacts
9. validate schemas for optional produced artifacts that exist
10. execute route effects
11. checkpoint/event/continue
```

Reason for handler before artifact validation:

* Providers may write artifacts directly.
* Handlers may normalize, post-process, or write artifacts from `Outcome.payload`.
* The step contract should be validated after the step’s full local processing, but before successful route commitment.

Recommended `SystemStep` order:

```text
1. run system handler
2. get Event tag
3. resolve selected route
4. determine required artifacts
5. validate required artifact existence/schema
6. validate optional present produced artifacts
7. execute route effects
8. checkpoint/event/continue
```

## 4.12 Required artifact selection

For selected route:

```text
if RouteContract.required_artifacts is non-empty:
    validate exactly those route-specific artifacts

else:
    validate all produced artifacts with Artifact.required=True

always:
    validate optional produced artifacts that exist and have schema
```

## 4.13 Failure behavior

If required artifact validation fails:

For `LLMStep` / `PairStep`:

```python
raise ProviderExecutionError(...)
```

For `SystemStep`:

```python
raise WorkflowExecutionError(...)
```

Error message must include:

```text
step name
route tag
artifact name
qualified artifact name if available
resolved path
validation errors
```

The engine must:

```text
save checkpoint
emit failure event if existing fatal/error event model supports it
not silently route to needs_rework
not invent automatic fallback routing
```

---

# 5. RouteContract Integration

Current `RouteContract.required_artifacts` is provider-facing metadata and compile-time validation. It must become runtime-enforced. Current capabilities already expose route contracts and required artifacts in workflow inspection. 

Keep existing fields:

```python
@dataclass(frozen=True)
class RouteContract:
    summary: str
    required_artifacts: tuple[str, ...] = ()
    work_item_effect: str | None = None
```

Change semantics:

```text
required_artifacts now has runtime meaning.
```

Rules:

```text
- selected route has required_artifacts:
    enforce those artifacts

- selected route has no required_artifacts:
    enforce Artifact.required=True produced artifacts

- optional produced artifact absent:
    OK

- optional produced artifact present with schema:
    validate

- expected_output_schema:
    still validates Outcome.payload only
```

Do not parse:

```text
RouteContract.summary
RouteContract.work_item_effect
```

Those remain provider-facing semantic text.

---

# 6. Session and Continuity Upgrade

## 6.1 Correct model

A session is a provider conversation handle. It is not inherently run-bound, task-bound, or work-item-bound.

Final model:

```text
Session
  named provider conversation slot

Continuity
  default policy for choosing/reusing provider conversation

ctx.open_session(..., scope=...)
  explicit runtime override binding the slot to a named logical scope key
```

## 6.2 Add `core/sessions.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from .context import Context
    from .worklists import Worklist


ContinuityKind = Literal["run", "task", "work_item", "fresh", "key"]


@dataclass(frozen=True, slots=True)
class Continuity:
    kind: ContinuityKind
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

## 6.3 Modify `Session`

Move or update `Session` in `core/steps.py` or import it from `core/sessions.py`.

```python
class Session:
    __slots__ = ("name", "continuity", "_order")

    def __init__(self, *, continuity: Continuity | None = None) -> None:
        self.name: str | None = None
        self.continuity = continuity or Continuity.run()
        self._order = next(_SESSION_COUNTER)

    def bind_name(self, name: str) -> None:
        if self.name is None:
            self.name = name
        elif self.name != name:
            raise ValueError(f"session already named {self.name!r}; cannot rename to {name!r}")

    def __repr__(self) -> str:
        return f"Session(name={self.name!r}, continuity={self.continuity!r})"
```

## 6.4 Default session

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
SystemStep uses no provider session unless currently supported; prefer no provider session.
```

Runtime rule:

```text
Every run creates or lazily opens the default session before first provider-owned step.
```

## 6.5 Preserve `ctx.open_session(..., scope=...)`

This is mandatory.

Current context supports:

```python
ctx.open_session(ref, scope=None)
ctx.get_session(ref, scope=None)
```

Preserve that behavior and extend it. 

New signature:

```python
def open_session(
    self,
    ref: Session | str = DEFAULT_SESSION_NAME,
    scope: str | None = None,
    *,
    continuity: Continuity | None = None,
    key: str | None = None,
) -> SessionBinding:
    ...
```

Also:

```python
def get_session(
    self,
    ref: Session | str = DEFAULT_SESSION_NAME,
    scope: str | None = None,
    *,
    continuity: Continuity | None = None,
    key: str | None = None,
) -> SessionBinding | None:
    ...
```

Keep `scope` as the second positional parameter to preserve current usage:

```python
ctx.open_session(self.orbit, "cluster-1")
ctx.open_session(self.orbit, scope="cluster-1")
```

## 6.6 Session key model

Create:

```python
SessionKeyDomain = Literal[
    "run",
    "task",
    "work_item",
    "fresh",
    "explicit_scope",
    "explicit_key",
]


@dataclass(frozen=True, slots=True)
class SessionKey:
    slot: str
    domain: SessionKeyDomain
    value: str
```

Examples:

```text
SessionKey("default", "run", run_id)
SessionKey("planner", "run", run_id)
SessionKey("reviewer", "task", task_id)
SessionKey("worker", "work_item", "gate:ios-release")
SessionKey("scratch", "fresh", uuid)
SessionKey("reviewer", "explicit_scope", "cluster-1")
SessionKey("reviewer", "explicit_key", "customer-acme")
```

## 6.7 Resolution order

When a step needs a session:

```text
1. use explicit step.session if present, else default session
2. if an active binding override exists for that slot, use it
3. else derive SessionKey from session.continuity
4. auto-open binding if missing
```

When `ctx.open_session(...)` is called:

```text
if key is provided and scope is provided:
    raise WorkflowExecutionError

if key is provided:
    bind slot to SessionKey(slot, "explicit_key", key)

elif scope is provided:
    bind slot to SessionKey(slot, "explicit_scope", scope)

elif continuity is provided:
    bind slot to derived key from provided continuity

else:
    bind slot to derived key from session.continuity
```

So:

```python
ctx.open_session(self.main)
```

means:

```text
open/bind using self.main.continuity
```

And:

```python
ctx.open_session(self.main, scope="cluster-1")
```

means:

```text
open/bind explicit scope key "cluster-1"
```

## 6.8 Store protocol

Update `core/stores/protocols.py`.

```python
class SessionStore(Protocol):
    def get(self, key: SessionKey) -> SessionBinding | None:
        ...

    def open(self, key: SessionKey) -> SessionBinding:
        ...

    def upsert(self, binding: SessionBinding) -> None:
        ...

    def snapshot(self) -> SessionSnapshot:
        ...

    def restore(self, snapshot: SessionSnapshot) -> None:
        ...
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

`SessionSnapshot`:

```python
@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    bindings: tuple[SessionBinding, ...]
    active_keys_by_slot: Mapping[str, SessionKey]
```

## 6.9 Filesystem session paths

Update filesystem session store.

Recommended paths:

```text
run continuity:
  <run_folder>/sessions/<slot>.json

default run continuity:
  <run_folder>/sessions/default.json

task continuity:
  <workflow_folder>/sessions/task/<slot>.json

work-item continuity:
  <workflow_folder>/sessions/work_items/<worklist>/<item_dir_key>/<slot>.json

explicit scope override:
  <run_folder>/sessions/scopes/<safe_scope>/<slot>.json

explicit key override:
  <workflow_folder>/sessions/keys/<slot>/<safe_key>.json

fresh continuity:
  <run_folder>/sessions/fresh/<slot>/<uuid>.json
```

The `explicit_scope` path preserves current scoped-session behavior in spirit.

## 6.10 SessionPaths

Do not remove `ctx.open_session(..., scope=...)`.

For `SessionPaths`:

```text
- do not export it from root workflow;
- do not treat it as workflow behavior;
- keep it as an advanced storage-path customization hook only if current functionality/tests require it;
- otherwise demote it to runtime store infrastructure.
```

Because feature regressions are not allowed, the safest implementation path is:

```text
1. keep extensions.SessionPaths importable initially;
2. adapt it internally to SessionKey-based paths;
3. mark docs as advanced storage customization;
4. do not use it in normal examples;
5. do not let it affect workflow routing, sessions, steps, artifacts, or control flow.
```

---

# 7. Typed Workflow Parameters

## 7.1 Goal

Current `ctx.workflow_params` returns a dict. Add typed access.

```python
ctx.params.mode
```

Preserve:

```python
ctx.workflow_params["mode"]
```

## 7.2 Implementation

Modify `Context`.

```python
@property
def params(self) -> BaseModel:
    return self._params
```

Constructor should accept:

```python
params: BaseModel
workflow_params: Mapping[str, object]
```

If no package `Parameters` model exists:

```python
class EmptyParameters(BaseModel):
    model_config = ConfigDict(frozen=True)
```

## 7.3 Runner behavior

At run start:

```text
1. parse -wf overrides;
2. validate using package Parameters model if present;
3. persist JSON-safe params to run metadata;
4. pass both typed params and dict params into Context.
```

At resume:

```text
1. load persisted params;
2. recreate typed params;
3. ignore new param overrides unless current runtime already has defined behavior;
4. preserve ctx.workflow_params compatibility.
```

---

# 8. Typed Routes and Effects

## 8.1 Goal

Keep current simple transition dicts:

```python
transitions = {ask: {"done": SUCCESS}}
```

Add advanced Python objects:

```python
transitions = {
    assess: {
        "passed": Route.to(
            next_step,
            SetStatus(gates, "completed"),
            Advance(gates),
        ),
        "needs_rework": Route.to(assess, ResetCompletion(gates)),
    }
}
```

## 8.2 Add `core/routes.py`

```python
@dataclass(frozen=True, slots=True)
class Route:
    target: object | None = None
    effects: tuple[Effect, ...] = ()

    @staticmethod
    def to(target: object, *effects: Effect) -> "Route":
        return Route(target=target, effects=tuple(effects))

    @staticmethod
    def complete(*effects: Effect) -> "Route":
        return Route(target=SUCCESS, effects=tuple(effects))

    @staticmethod
    def pause(*effects: Effect) -> "Route":
        return Route(target=PAUSE, effects=tuple(effects))

    @staticmethod
    def fail(*effects: Effect) -> "Route":
        return Route(target=FAIL, effects=tuple(effects))
```

## 8.3 Add `core/effects.py`

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
    route_to: object | None = None


@dataclass(frozen=True, slots=True)
class BoardMutation:
    worklist: Worklist | str
    kind: Literal[
        "split_active_work_item",
        "reprioritize_remaining_work_items",
        "retire_active_work_item",
    ]
```

## 8.4 Compile route normalization

Normalize all transition destinations:

```text
Step destination -> Route.to(step)
SUCCESS -> Route.complete()
PAUSE -> Route.pause()
FAIL -> Route.fail()
string terminal -> Route(target=string)
Route -> compile directly
```

Compiled representation:

```python
@dataclass(frozen=True, slots=True)
class CompiledRoute:
    source_step: str
    tag: str
    target: str
    effects: tuple[Effect, ...]
```

## 8.5 Validation

Add:

```text
1. target step must exist unless terminal;
2. Route.complete cannot also target nonterminal step;
3. Advance(..., if_exhausted="route") requires route_to;
4. effect worklist names must exist;
5. BoardMutation requires mutable artifact-backed worklist;
6. dict shorthand still works;
7. Route object and dict shorthand can coexist.
```

---

# 9. Worklists and Work Items

## 9.1 Goal

Add first-class Python work-item abstractions without introducing a flow DSL.

## 9.2 Add `core/worklists.py`

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
        if not self.items:
            return None
        if self.current_index >= len(self.items):
            return None
        return self.items[self.current_index]
```

```python
class WorklistSource(Protocol[T]):
    def load(self, ctx: Context) -> Sequence[T]:
        ...

    def save(self, ctx: Context, items: Sequence[T]) -> None:
        ...

    def validate(self, ctx: Context, items: Sequence[T]) -> str | None:
        ...
```

```python
@dataclass(frozen=True, slots=True)
class Worklist(Generic[T]):
    name: str
    source: WorklistSource[T]
    selector: Selector = Selector()

    @classmethod
    def from_items(
        cls,
        name: str,
        items: Sequence[T],
        *,
        item_id: Callable[[T], str] | str = "id",
        title: Callable[[T], str] | str = "title",
        status: Callable[[T], str | None] | str | None = None,
        selector: Selector = Selector(),
    ) -> "Worklist[T]":
        ...

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
    ) -> "Worklist[Mapping[str, object]]":
        ...
```

## 9.3 Step scoping

Extend provider-owned steps:

```python
PairStep(..., scope=gates)
LLMStep(..., scope=gates)
```

Rules:

```text
scope=None
  run-global step

scope=Worklist
  step executes against current selected work item

engine does not automatically loop the whole worklist
progression is explicit via Advance(worklist)
```

## 9.4 Context APIs

Add:

```python
def selection(self, worklist: Worklist | str) -> Selection:
    ...

def current(self, worklist: Worklist | str) -> WorkItem | None:
    ...

@property
def item(self) -> WorkItem | None:
    ...
```

## 9.5 Template placeholders

Support:

```text
{item.id}
{item.dir_key}
{worklist.<name>.current.id}
{worklist.<name>.current.dir_key}
```

If no current item exists and a template requires one, raise `WorkflowExecutionError`.

---

# 10. Typed Child Workflow Contracts

## 10.1 Preserve current composition

Keep:

```python
ctx.invoke_workflow("child_workflow", message="...", parameters={...})
ctx.invoke_workflow(ChildWorkflow, message="...", parameters={...})
```

## 10.2 Add typed input/output

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

Allow:

```python
ctx.invoke_workflow(
    ChildWorkflow,
    input=ChildWorkflow.Input(...),
)
```

## 10.3 Extend `ChildWorkflowResult`

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

Do not remove current metadata fields.

---

# 11. Compiler Changes

Update `core/compiler.py`.

## 11.1 Collect and compile

Compiler must collect:

```text
State
Input optional
Output optional
Parameters optional
Session declarations
default session
Artifact declarations
step-local produced artifacts
Worklists
Steps
RouteContracts
Transitions
Route/effect objects
Extensions
```

## 11.2 Compiled workflow additions

Extend compiled workflow object:

```python
@dataclass(frozen=True)
class CompiledWorkflow:
    workflow_cls: type[Workflow]
    name: str
    state_model: type[BaseModel]
    input_model: type[BaseModel] | None
    output_model: type[BaseModel] | None
    parameters_model: type[BaseModel] | None

    sessions: Mapping[str, Session]
    default_session_name: str

    artifacts: Mapping[str, CompiledArtifact]
    artifacts_by_qualified_name: Mapping[str, CompiledArtifact]

    worklists: Mapping[str, Worklist]

    steps: Mapping[str, CompiledStep]
    entry: str
    routes: Mapping[str, Mapping[str, CompiledRoute]]
    extensions: tuple[WorkflowExtension, ...]
```

## 11.3 Preserve current deterministic compilation

Current tests assert deterministic compiled workflow caching. Preserve this behavior.

When adding mutable fields to `Artifact` or `Session`, ensure compilation freezes or copies normalized definitions so subsequent mutation does not make cached compiled workflows inconsistent.

---

# 12. Engine Changes

Update `core/engine.py`.

## 12.1 Run startup

At run start:

```text
1. compile workflow
2. build initial state
3. build typed params
4. initialize worklist selections
5. initialize default session binding
6. build Context
7. call on_start if present
8. execute entry step
```

Important:

```text
on_start may still call ctx.open_session(..., scope=...)
and that override should affect subsequent steps.
```

## 12.2 Step execution

For each step:

```text
1. resolve required input artifacts
2. set current work item context if scoped
3. resolve provider session if provider-owned:
   a. explicit step session or default session
   b. active override from ctx.open_session if present
   c. otherwise declared continuity
   d. auto-open if missing
4. run provider or system handler
5. validate provider route and payload
6. run step handler if provider-owned and present
7. resolve selected route
8. enforce artifact contracts
9. execute route effects
10. checkpoint/event
11. advance, pause, fail, or complete
```

## 12.3 Artifact contract failure checkpoint

Checkpoint must include enough detail to diagnose:

```text
step name
route tag
artifact name
qualified artifact name
resolved path
validation errors
state snapshot
session snapshot
worklist selection snapshot
```

---

# 13. Runtime Store Changes

## 13.1 Session store constructor

Update filesystem session store to receive all relevant folders:

```python
FilesystemSessionStore(
    *,
    task_folder: Path,
    workflow_folder: Path,
    run_folder: Path,
    provider: str,
)
```

## 13.2 Persist default session

Every run should have:

```text
<run_folder>/sessions/default.json
```

This should exist even if the workflow has no explicit `Session` declaration.

## 13.3 Run metadata

Add:

```json
{
  "default_session": "default",
  "session_policy_version": 1,
  "worklists": {}
}
```

Preserve all existing fields.

---

# 14. Docs Updates

Update `docs/authoring.md`.

Required sections:

```text
Default session
Continuity
ctx.open_session(..., scope=...) override
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
from pydantic import BaseModel

from workflow import Artifact, PairStep, RouteContract, SystemStep, Workflow


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
ctx.open_session(..., scope=...) remains supported.
Continuity defines default session reuse policy.
scope= is an explicit runtime binding override.
Route/effect objects are Python objects, not a string DSL.
Artifact schema validates files; expected_output_schema validates Outcome.payload.
```

---

# 15. Tests to Add or Update

## 15.1 Artifact compiler tests

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

## 15.2 Artifact runtime tests

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

## 15.3 Backward compatibility tests

```python
def test_existing_class_level_artifact_produces_still_works(): ...
def test_existing_unrequired_produces_does_not_force_file_existence(): ...
def test_expected_output_schema_still_validates_only_outcome_payload(): ...
def test_produces_still_exposes_artifact_handles_to_provider(): ...
def test_ctx_open_session_scope_keyword_still_valid(): ...
def test_ctx_open_session_scope_positional_still_valid(): ...
```

## 15.4 Session tests

```python
def test_default_global_session_is_created_for_every_run(): ...
def test_llm_step_without_session_uses_default_session(): ...
def test_pair_step_without_session_uses_default_session(): ...
def test_declared_session_auto_opens_without_on_start(): ...
def test_open_session_scope_override_is_valid(): ...
def test_open_session_scope_override_changes_active_binding(): ...
def test_get_session_scope_override_reads_same_binding(): ...
def test_open_session_key_and_scope_are_mutually_exclusive(): ...
def test_work_item_continuity_uses_current_work_item_key(): ...
def test_fresh_continuity_rotates_session_key(): ...
```

## 15.5 Typed params tests

```python
def test_context_exposes_typed_params(): ...
def test_context_workflow_params_dict_remains_available(): ...
def test_resume_restores_typed_params(): ...
def test_missing_parameters_model_returns_empty_params(): ...
```

## 15.6 Route/effect tests

```python
def test_dict_transition_shorthand_still_works(): ...
def test_route_object_to_step_compiles(): ...
def test_route_complete_with_effects_compiles(): ...
def test_invalid_effect_worklist_reference_rejected(): ...
def test_advance_route_to_requires_target_when_if_exhausted_route(): ...
```

## 15.7 Worklist tests

```python
def test_worklist_from_artifact_selects_all_items(): ...
def test_selector_single_item_from_params(): ...
def test_scoped_step_receives_current_item(): ...
def test_artifact_template_can_use_item_dir_key(): ...
def test_advance_moves_to_next_item(): ...
def test_advance_completes_when_exhausted(): ...
```

## 15.8 Child workflow tests

```python
def test_invoke_workflow_with_typed_input(): ...
def test_child_result_exposes_typed_output(): ...
def test_child_result_preserves_low_level_metadata(): ...
def test_child_typed_output_validation_failure_is_recorded(): ...
```

## 15.9 Strictness tests

Update strictness tests to assert:

```text
workflow exports new authoring primitives
workflow does not export engine/compiler internals
workflow.toml remains metadata-only
docs mention ctx.open_session(..., scope=...)
docs do not introduce WorkflowBook or string flow parser as v3 authoring surface
```

---

# 16. Implementation Order

## Phase 1: Artifact model

Implement:

```text
Artifact.kind
Artifact.schema
Artifact.required
Artifact.owner_step
Artifact.qualified_name
Artifact.text/md/json/raw factories
ArtifactValidationResult
ArtifactHandle JSON/model helpers
```

Run focused artifact unit tests.

## Phase 2: Compiler artifact inventory

Implement:

```text
class-level artifact inventory
step-local artifact inventory
qualified names
step-local relative path resolution
RouteContract.required_artifacts resolution
schema validation
ambiguous reference rejection
```

Run compiler/validation tests.

## Phase 3: Runtime artifact enforcement

Implement:

```text
required artifact determination
Artifact.required enforcement
RouteContract.required_artifacts enforcement
optional-present schema validation
checkpoint on artifact validation failure
ProviderExecutionError for provider-owned steps
WorkflowExecutionError for SystemStep
```

Run engine contract tests.

## Phase 4: Session model

Implement:

```text
Continuity
Session.continuity
default session
SessionKey
auto-open sessions
preserve ctx.open_session(..., scope=...)
preserve ctx.get_session(..., scope=...)
session store protocol migration
filesystem session path migration
```

Run session and runtime tests.

## Phase 5: Typed params

Implement:

```text
ctx.params
typed params persistence
resume restoration
```

Run package CLI and context tests.

## Phase 6: Routes/effects

Implement:

```text
Route
Effect objects
route normalization
effect validation
basic effect execution
```

Run compiler and engine tests.

## Phase 7: Worklists

Implement:

```text
WorkItem
Worklist
Selector
Selection
scoped steps
ctx.selection/current/item
artifact item placeholders
Advance behavior
```

Run worklist and runtime tests.

## Phase 8: Typed child workflow IO

Implement:

```text
Input model convention
Output model convention
build_output
ChildWorkflowResult.output
metadata preservation
```

Run child workflow tests.

## Phase 9: Docs and full regression

Update docs and strictness tests.

Run:

```bash
pytest -q
```

---

# 17. Acceptance Criteria

The implementation is complete when:

1. Existing workflows compile and run.
2. Existing `Artifact("{workflow_folder}/x.md")` still works.
3. Existing `produces={"x": artifact}` still provides writable handles.
4. Step-local artifacts can be declared inline.
5. Step-local artifacts are accessible as `step.artifact_name`.
6. Relative step-local paths resolve under `{workflow_folder}/{step_name}/`.
7. Explicit artifact templates resolve exactly as before.
8. `Artifact.json(..., schema=Model)` validates content.
9. `required=True` enforces artifact existence and schema validity.
10. `RouteContract.required_artifacts` enforces selected-route artifact contracts.
11. Optional absent artifacts do not fail.
12. Optional present schema artifacts validate.
13. Missing/invalid required artifacts fail with checkpoint.
14. `expected_output_schema` validates only `Outcome.payload`.
15. Every run has a default provider session.
16. LLM/Pair steps without explicit sessions use default session.
17. Declared sessions auto-open.
18. `ctx.open_session(session)` still works.
19. `ctx.open_session(session, scope="x")` still works.
20. `ctx.open_session(session, "x")` still works if currently accepted.
21. `ctx.get_session(session, scope="x")` still works.
22. `Continuity` defines declarative default session reuse policy.
23. `scope=` acts as explicit runtime binding override.
24. `ctx.params` exposes typed parameters.
25. `ctx.workflow_params` remains available.
26. Dict transitions still work.
27. `Route` objects work.
28. Route effects work.
29. Worklists can drive scoped steps.
30. Child workflows can return typed outputs.
31. `workflow.toml` remains metadata-only.
32. Root `workflow` shim exports only authoring primitives.
33. Full `pytest` passes.

---

# 18. Final Mental Model

The final model should be:

```text
Workflow
  Python class defining state, steps, artifacts, sessions, routes, and handlers

Session
  named provider conversation slot

Continuity
  declarative default reuse policy for a session slot

ctx.open_session(..., scope=...)
  explicit runtime override to bind a session slot to a named logical scope key

requires
  artifacts that must exist before step execution

produces
  writable artifacts owned by the step

Artifact.schema
  validates artifact file content

Artifact.required
  default output requirement

RouteContract.required_artifacts
  selected-route output requirement

expected_output_schema
  validates provider Outcome.payload only

Route
  Python object describing route target and effects

Effect
  Python object describing route side effects

Worklist
  Python object describing repeated scoped work

ctx.invoke_workflow(...)
  explicit child workflow composition
```

The result should be a framework that feels like **plain Python**, but has strong enough abstractions to express durable agentic workflow contracts directly in code.
