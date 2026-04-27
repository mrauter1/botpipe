# Standalone implementation plan: Autoloop v3 greenfield authoring cleanup

## 0. Context and governing observation

This project is **greenfield**. There is **no need to preserve legacy compatibility** for old public APIs, old `RouteContract` behavior, old provider request fields, old route-contract docs, or compatibility shims.

The current implementation already added pieces of the desired direction: `autoloop.simple`, `step`, `review_step`, `workflow_step`, `system_step`, `Json`, `Md`, `RouteInfo`, prompt constructors, `reads`, hooks, and partial workflow-step lowering. But the implementation still contains legacy `RouteContract` machinery and several incomplete integrations. 

This plan replaces the partial compatibility implementation with the final greenfield model.

Do **not** implement `autoloop eject`, source-code expansion, or any command that rewrites a simple workflow into a larger workflow package.

---

# 1. Final target model

The following workflow must compile, load, inspect, and run:

```python
from pydantic import BaseModel
from autoloop.simple import Workflow, step, review_step, Json, Md, chain

class Analysis(BaseModel):
    summary: str
    severity: str

class IncidentBrief(Workflow):
    analysis = step(
        "Analyze the incident request and write structured analysis.",
        out=Json("analysis", Analysis),
    )

    email = review_step(
        producer="Draft an executive email from {analysis}.",
        verifier="Accept only if the email is accurate, concise, and executive-ready.",
        reads=["analysis"],
        out=Md("email"),
    )

    flow = chain(analysis, email)
```

It must require no explicit:

```text
State
entry
transitions
RouteContract
prompt files
workflow metadata
session declarations
provider/model configuration
expected_output_schema duplication
on_<step> handler
```

The compiled workflow must still be deterministic, resumable, artifact-aware, route-validated, and compatible with the existing runtime engine architecture.

---

# 2. Public API

Use exactly one active public authoring surface:

```text
autoloop.simple
```

Export from `autoloop.simple`:

```python
Workflow
StrictWorkflow
step
review_step
system_step
workflow_step
WorkflowStep
chain
Json
Md
Text
Raw
Prompt
Route
RouteInfo
AfterHookResult
```

Update `autoloop/__init__.py` to re-export the same stable public surface.

Do not expose `RouteContract` anywhere in active public APIs.

If `workflow/primitives.py` remains, make it a thin re-export of `autoloop.simple`. Do not let it become a second public API.

Treat `core/*` as internal kernel code. If `core/__init__.py` exists, remove legacy authoring exports from it or keep only internal exports. It must not export `RouteContract`.

---

# 3. Delete `RouteContract` completely

Remove the concept from active code.

Delete or fully empty out:

```text
core/route_contracts.py
```

Remove:

```text
RouteContract
RouteContractSpec
normalize_route_contract
normalize_route_contracts
route_contracts fields
route_required_artifacts fields
route contract terminology in provider rendering
route contract terminology in capability payloads
route contract examples in docs
route contract tests
```

Search active code and docs, excluding archived migration notes if any, for:

```text
RouteContract
route_contracts
route_required_artifacts
"route contract"
```

Expected result: **no active matches**.

Use `RouteInfo` and `Route` metadata instead.

---

# 4. Route metadata model

## 4.1 `RouteInfo`

Define in `core/routes.py`:

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class RouteInfo:
    summary: str | None = None
    required_outputs: tuple[str, ...] = ()
    handoff: str | None = None
```

Validation:

```text
summary, if present, must be non-empty after stripping
required_outputs must be a sequence of non-empty strings
handoff, if present, must be non-empty after stripping
```

## 4.2 `Route`

Define:

```python
@dataclass(frozen=True, slots=True)
class Route:
    target: object | None = None
    effects: tuple[Effect, ...] = ()
    summary: str | None = None
    required_outputs: tuple[str, ...] = ()
    handoff: str | None = None
```

Constructors:

```python
Route.to(target, *effects, summary=None, required_outputs=(), handoff=None)
Route.complete(*effects, summary=None, required_outputs=(), handoff=None)
Route.pause(*effects, summary=None, required_outputs=(), handoff=None)
Route.fail(*effects, summary=None, required_outputs=(), handoff=None)
```

## 4.3 Route metadata precedence

For each source step and route tag:

```text
1. Route.summary wins over step.route_infos[tag].summary.
2. Route.required_outputs wins over step.route_infos[tag].required_outputs if non-empty.
3. If both Route.handoff and RouteInfo.handoff are present and differ, raise validation error.
4. If neither supplies summary, use standard fallback.
5. If neither supplies required_outputs, use ().
6. If neither supplies handoff, use None.
```

Fallback route summaries:

```text
done: Step completed and selected the default completion route.
accepted: Verifier accepted the governed output.
needs_rework: Verifier requested local repair within the same work boundary.
needs_replan: The current work boundary appears incorrect and replanning is needed.
question: Execution paused for a user answer.
blocked: Execution paused because the step is blocked.
failed: Execution failed.
other: Routes from '<source_step>' to '<target>'.
```

## 4.4 Required output resolution

`required_outputs` names are resolved preferably step-local:

```text
"analysis" resolves to "<source_step>.analysis" if produced by the source step.
"step.analysis" resolves by qualified name.
A required output that is not produced by the source step is invalid.
```

Route-required outputs are route-specific output obligations. They are not input requirements.

---

# 5. Reserved routes

Every provider/system/workflow step has these reserved routes available by default:

```text
question -> PAUSE
blocked -> PAUSE
failed -> FAIL
```

These routes must be inserted during workflow definition normalization, not merely documented.

If the author explicitly defines one of these routes, the explicit definition overrides the default.

Reserved routes must not require route summaries or route metadata.

---

# 6. Core step classes

Update `core/steps.py`.

## 6.1 Base `Step`

Final constructor fields:

```python
class Step:
    def __init__(
        *,
        name: str,
        session: Session | None = None,
        scope: Worklist | str | None = None,
        reads: Sequence[Artifact | str | Path | ReadRef] | None = None,
        requires: Sequence[Artifact | str] | None = None,
        produces: Mapping[str, Artifact] | None = None,
        log_artifacts: Sequence[Artifact] | None = None,
        expected_output_schema: Any | None = None,  # internal control schema only
        route_infos: Mapping[str, RouteInfo | str] | None = None,
        retry_policy: ProviderRetryPolicy | None = None,
        before: Callable | None = None,
        after: Callable | None = None,
    )
```

Remove `route_contracts`.

Normalize `route_infos`:

```text
None -> {}
str -> RouteInfo(summary=str)
RouteInfo -> unchanged
```

## 6.2 `LLMStep`

Keep as single-provider step.

## 6.3 `PairStep`

Keep as producer/verifier step.

The producer phase does not select final route. The verifier selects the final provider outcome route.

## 6.4 `SystemStep`

Add direct callable support:

```python
class SystemStep(Step):
    kind = "system"

    def __init__(..., handler: Callable | None = None, ...)
```

A simple `system_step(fn)` must lower to `SystemStep(handler=fn)`.

Do not require `on_<step>` for simple system steps.

## 6.5 `WorkflowStep`

Add a true core class:

```python
class WorkflowStep(Step):
    kind = "workflow"

    def __init__(
        *,
        name: str,
        workflow: str | type[Any],
        message: str | None = None,
        message_from: Artifact | str | Path | None = None,
        params: Mapping[str, object] | None = None,
        input: object | None = None,
        ...
    )
```

Do **not** lower `workflow_step(...)` to `SystemStep`.

Do **not** install generated `on_<step>` handlers for workflow steps.

The engine executes `WorkflowStep` directly.

---

# 7. Simple authoring API

Update `autoloop/simple.py`.

## 7.1 `Workflow`

`Workflow` is the non-strict simple authoring base.

```python
class EmptyState(BaseModel):
    pass

class Workflow:
    __workflow_abstract__ = True
    __strict_workflow__ = False
    State = EmptyState
    extensions: tuple[object, ...] = ()
```

It must not trigger full import-time metaclass validation.

## 7.2 `StrictWorkflow`

`StrictWorkflow` is opt-in strict authoring.

Subclasses of `StrictWorkflow` must not accidentally inherit an abstract flag that prevents validation.

Add tests for this.

## 7.3 `step(...)`

Signature:

```python
def step(
    prompt,
    *,
    name: str | None = None,
    reads=(),
    requires=(),
    out=None,
    outputs=(),
    routes=None,
    route_infos=None,
    route_summaries=None,
    before=None,
    after=None,
    control_schema=None,
    retry=None,
    session=None,
):
    ...
```

Do **not** include `provider`, `model`, or `effort`. Provider selection, model, and effort are runtime config / CLI concerns.

Lowering rules:

```text
raw str prompt -> Prompt.inline(...)
Path -> Prompt.file(...)
Prompt.inline/file -> unchanged
default completion route -> done
out/outputs -> declared produced artifacts
reads -> optional readable references
requires -> hard input artifact references
control_schema -> internal expected_output_schema
route_summaries -> RouteInfo(summary=...)
route_infos -> RouteInfo
before/after -> step hooks
```

## 7.4 `review_step(...)`

Signature:

```python
def review_step(
    producer,
    verifier,
    *,
    name: str | None = None,
    reads=(),
    requires=(),
    out=None,
    outputs=(),
    accepted="accepted",
    rework="needs_rework",
    route_infos=None,
    route_summaries=None,
    before=None,
    after=None,
    control_schema=None,
    retry=None,
    session=None,
):
    ...
```

Lower to `PairStep`.

Default routes:

```text
accepted -> next/SUCCESS through chain
needs_rework -> same review step
question -> PAUSE
blocked -> PAUSE
failed -> FAIL
```

The verifier controls the accepted/rework route.

## 7.5 `system_step(fn)`

Signature:

```python
def system_step(
    fn,
    *,
    name: str | None = None,
    reads=(),
    requires=(),
    out=None,
    outputs=(),
    routes=None,
    route_infos=None,
    route_summaries=None,
    before=None,
    after=None,
):
    ...
```

Lower to `SystemStep(handler=fn)`.

Supported `fn` signatures:

```python
fn(ctx)
fn(state, ctx)
```

Supported returns:

```text
None -> unchanged state, Event("done")
BaseModel -> returned state, Event("done")
"route" -> unchanged state, Event("route")
Event -> unchanged state, that Event
(state, "route") -> state, Event("route")
(state, Event) -> state, Event
```

Final route output enforcement applies exactly like any other step.

## 7.6 `workflow_step(...)`

Signature:

```python
def workflow_step(
    workflow,
    *,
    name: str | None = None,
    message: str | None = None,
    message_from=None,
    params=None,
    input=None,
    reads=(),
    requires=(),
    out=None,
    outputs=(),
    routes=None,
    route_infos=None,
    route_summaries=None,
    before=None,
    after=None,
):
    ...
```

Lower to true `core.steps.WorkflowStep`.

---

# 8. Artifact helpers

Keep:

```python
Json(name, schema=None, *, path=None, required=False)
Md(name, *, path=None, required=False)
Text(name, *, path=None, required=False)
Raw(name, *, path=None, required=False)
```

Default paths:

```text
{workflow_folder}/{step_name}/{artifact_name}.json
{workflow_folder}/{step_name}/{artifact_name}.md
{workflow_folder}/{step_name}/{artifact_name}.txt
{workflow_folder}/{step_name}/{artifact_name}
```

Artifact schema rules:

```text
Artifact schema validates the file.
Artifact schema never becomes provider expected_output_schema.
Json("analysis", Analysis) does not set provider control schema.
```

Required output sources:

```text
artifact.required=True
Route.required_outputs
RouteInfo.required_outputs
```

Optional typed output behavior:

```text
if absent -> no failure
if present and schema exists -> validate
```

Undeclared workspace outputs are allowed.

Provider prompt must say declared writable artifacts are governed surfaces, not an exclusive allow-list.

---

# 9. Reads and requires

## 9.1 Required inputs

`requires` are hard preconditions.

Rules:

```text
must resolve to declared artifact
must exist before step execution
missing required input fails before provider/system/workflow execution
if produced by workflow, producer must be topologically prior/reachable before consumer
```

## 9.2 Reads

`reads` are optional readable context.

Rules:

```text
may reference declared artifact by name
may reference workspace path
missing read does not fail
render with exists=false
does not impose hard runtime precondition
does not impose artifact graph ordering in default/prototype validation
```

## 9.3 Provider readable representation

Add:

```python
@dataclass(frozen=True, slots=True)
class ProviderReadableRef:
    name: str
    path: str
    exists: bool
    declared_artifact: bool
    kind: str | None = None
    qualified_name: str | None = None
    schema_name: str | None = None
```

Or extend `ProviderArtifactRef` with:

```python
declared_artifact: bool
```

Rules:

```text
Declared artifact reads -> declared_artifact=True
Path reads -> declared_artifact=False
Missing reads -> exists=False
```

## 9.4 Prompt placeholder inference

Prompt placeholders may infer `reads`, never `requires`.

Infer artifact reads from:

```text
{analysis}
{artifacts.analysis}
{step.analysis}
```

Do not infer from:

```text
{state.foo}
{params.foo}
{input.foo}
{item.title}
{workflow_folder}
{run_folder}
```

Bare placeholder inference:

```text
infer only when exactly one declared artifact has that name
do not infer if same name exists in State, Parameters, Input, or context names
if ambiguous, infer nothing
```

---

# 10. Prompt model

Update `core/prompts.py`.

```python
Prompt.inline(text: str)
Prompt.file(path: str | Path)
```

`ResolvedPrompt`:

```python
@dataclass(frozen=True, slots=True)
class ResolvedPrompt:
    path: str | None
    text: str | None
    source: Literal["inline", "file", "registry"]
```

Resolution order for file prompts:

```text
1. absolute path, if provided
2. workflow package/source directory
3. runtime prompt registry search roots
```

Runtime runner must always provide filesystem prompt registry.

Direct low-level `Engine` usage may require an explicit prompt registry for file prompts. Document and test this.

---

# 11. Workflow discovery and loading

Simple workflows must be discoverable by path, module, and catalog inspection.

## 11.1 Central helper

Create one helper:

```python
def is_workflow_class(candidate: object) -> bool:
    ...
```

Return true if:

```text
candidate is a class
candidate is not base Workflow or StrictWorkflow
candidate is subclass of autoloop.simple.Workflow or strict/core Workflow
candidate has at least one concrete Step member or simple declaration member
```

Simple declaration member:

```python
getattr(value, "__autoloop_simple_declaration__", False)
```

Consider inherited members when appropriate.

## 11.2 Update runtime loader

Update `runtime/loader.py::_locate_workflow_class`.

It must not require concrete `Step` members before lowering.

## 11.3 Update capability inspection

Update `core/workflow_capabilities.py::locate_workflow_class`.

It must also detect simple declaration workflows.

## 11.4 Required tests

These must work:

```bash
autoloop workflows show workflows/simple_example.py
autoloop run workflows/simple_example.py task-1 --message "..."
autoloop run simple_example task-1 --message "..."
```

where the name-based form is applicable.

---

# 12. Flow and transition lowering

## 12.1 `chain(...)`

`chain(a, b, c)` expands to:

```text
a.default_completion_route -> b
b.default_completion_route -> c
c.default_completion_route -> SUCCESS
```

Default completion routes:

```text
step -> done
review_step -> accepted
system_step -> done
workflow_step -> done
```

Explicit route:

```python
flow = chain((a, "custom_route"), b)
```

uses `"custom_route"`.

## 12.2 Explicit `routes`

Simple declarations may specify:

```python
routes={
    "done": next_step,
    "custom": Route.to(other_step, summary="...")
}
```

Lower route targets through declaration-to-step mapping.

## 12.3 Reserved route insertion

During normalization, for every step:

```text
question -> PAUSE
blocked -> PAUSE
failed -> FAIL
```

unless explicitly overridden.

## 12.4 Entry inference

If no `entry`:

```text
if flow exists -> first step in flow
else if exactly one step -> that step
else if graph has exactly one root -> root
else raise validation error
```

---

# 13. Compiler changes

## 13.1 `CompiledStep`

Final fields:

```python
name
kind
step
session_name
scope_name
reads
requires
produces
log_artifacts
available_routes
expected_output_schema
route_infos
route_required_outputs
retry_policy
producer_prompt
verifier_prompt
expected_output_validator
outcome_handler
system_handler
workflow_metadata / workflow handler fields if needed
before_hook
after_hook
```

Remove:

```text
route_contracts
```

## 13.2 `CompiledRoute`

Final fields:

```python
source_step
tag
target
effects
summary
required_outputs
handoff
```

## 13.3 Route metadata normalization

Implement:

```python
normalize_step_route_infos(definition, step, inventory) -> tuple[
    dict[str, RouteInfo],
    dict[str, tuple[str, ...]]
]
```

Inputs:

```text
Route.summary
Route.required_outputs
Route.handoff
step.route_infos
standard fallback summaries
topology fallback summaries
```

No route contracts.

---

# 14. Engine execution

## 14.1 Step finalization order

Use exact order:

```text
1. runtime extension before_step
2. workflow step before hook
3. resolve artifacts/readables
4. enforce required inputs
5. execute provider/system/workflow step
6. parse or construct candidate outcome/event
7. validate candidate route exists
8. run after hook
9. apply after-hook state changes to context
10. re-resolve artifacts after hook
11. validate final route exists
12. enforce final route required outputs
13. validate optional typed outputs that exist
14. apply route effects
15. schedule handoffs
16. runtime extension after_step
17. checkpoint/transition
```

## 14.2 Before hook

Supported signatures:

```python
before(ctx)
before(state, ctx)
```

Returns:

```text
None -> unchanged state
BaseModel -> new state
```

## 14.3 After hook

Supported signatures:

```python
after(ctx, outcome_or_event)
after(ctx, outcome_or_event, route_tag)
after(state, outcome_or_event, artifacts, ctx)
```

Returns:

```text
None
BaseModel
str route_tag
Event
AfterHookResult
```

Define:

```python
@dataclass(frozen=True, slots=True)
class AfterHookResult:
    state: BaseModel | None = None
    route: str | None = None
    event: Event | None = None
    handoff: str | None = None
```

Conflict rule:

```text
If event and route are both present and route != event.tag, raise.
```

## 14.4 Route override

After hooks may override route.

When route changes:

```text
validate final route exists
resolve final route target
recompute required outputs
re-resolve artifacts after state mutation
enforce final required outputs
record hook_route_override_from / hook_route_override_to in observability
```

## 14.5 Provider-attributable retry behavior

Do not automatically set provider-attributable false when a hook changes the route.

Simple rule:

```text
provider_attributable is based on step kind and artifact producer, not route override.
```

For provider steps, missing/invalid produced artifacts should remain retryable if provider retry policy allows it.

---

# 15. WorkflowStep execution

Implement direct engine path for `step.kind == "workflow"`.

## 15.1 Message resolution

Priority:

```text
1. explicit message
2. message_from declared artifact
3. message_from workspace path
4. default "Run child workflow <workflow>."
```

## 15.2 Invocation

Call:

```python
ctx.invoke_workflow(
    workflow,
    message=message,
    parameters=params,
    input=input,
)
```

## 15.3 Terminal mapping

```text
child SUCCESS -> Event("done")
child FAIL -> Event("failed")
child PAUSE with last_event.tag == "question" -> Event("question", question=...)
child PAUSE otherwise -> Event("blocked")
```

## 15.4 Output artifacts

If declared outputs exist:

```text
json -> child result metadata JSON
markdown/text -> human-readable summary
raw -> JSON bytes or text summary, choose one and test it
```

JSON payload:

```json
{
  "workflow_name": "...",
  "run_id": "...",
  "terminal": "...",
  "status": "...",
  "last_event": "...",
  "output_artifacts": {
    "name": "path"
  },
  "output_metadata": {}
}
```

## 15.5 Loop legality

WorkflowStep must be legal in verifier-gated loops:

```text
workflow_step -> review_step
review_step.needs_rework -> workflow_step
review_step.accepted -> next/SUCCESS
```

---

# 16. Provider request and rendering model

## 16.1 Remove fields

Remove everywhere:

```text
route_contracts
route_required_artifacts
```

## 16.2 Provider request/context fields

Use:

```python
expected_output_schema: Mapping[str, Any] | None
available_routes: tuple[str, ...]
route_infos: Mapping[str, RouteInfo]
route_required_outputs: Mapping[str, tuple[str, ...]]
readable_artifacts: tuple[ProviderReadableRef, ...]
required_artifacts: tuple[ProviderArtifactRef, ...]  # required inputs only
writable_artifacts: tuple[ProviderArtifactRef, ...]
retry_feedback: str | None
route_handoff: str | None
attempt: int
max_attempts: int
```

## 16.3 Provider control response format

Rendered prompts must instruct provider to return:

```json
{
  "tag": "<one available route>",
  "reason": "<short reason>",
  "payload": {}
}
```

Rules:

```text
payload may be omitted or empty when no control_schema is declared
if control_schema is declared, payload must validate against it
question route must include question field
blocked/failed should include reason
```

## 16.4 Renderer sections

Provider prompt structure:

```text
# Step: <step name>

<workflow-authored prompt>

## Runtime Step Contract

### Readable inputs
optional readable refs, exists flag

### Required inputs
hard preconditions

### Declared artifacts this step may write
governed output surfaces, not an exclusive allow-list

### Available routes
route, meaning, required outputs

### Control response
exact JSON outcome format
```

The phrase “route contract” must not appear.

---

# 17. Capability and inspection payloads

Remove payload keys:

```text
route_contracts
contracts_path if it specifically refers to route contracts
```

Important nuance:

Do **not** forbid user files named `contracts.py`. They may contain Pydantic models, artifact schemas, or validation specs. Removing `RouteContract` does not mean deleting every possible `contracts.py`.

If capability inspection reports support files, prefer names like:

```text
schema_paths
spec_paths
support_paths
```

Expose route metadata as:

```json
{
  "route_infos": {
    "done": {
      "summary": "Step completed and selected the default completion route.",
      "required_outputs": [],
      "handoff": null
    }
  },
  "route_required_outputs": {
    "done": []
  }
}
```

---

# 18. Validation

## 18.1 Prototype/default validation

Must catch:

```text
duplicate step names
invalid route targets
unknown required inputs
required input produced only after target
invalid artifact schema
invalid hook signatures
invalid after-hook route override
invalid required_outputs reference
invalid WorkflowStep child reference if statically resolvable
```

Must not require:

```text
metadata
prompt files
explicit State
route summaries
docs
tests
package layout
sessions
RouteContract
```

## 18.2 Strict validation

Strict validation is opt-in through `StrictWorkflow` or explicit validation level.

It may require or warn about:

```text
explicit State
external prompt files
declared outputs
explicit session policy
docs/tests/checklists if project policy requires them
```

Do not make strict validation default.

---

# 19. Import cleanup

Normalize imports.

Internal package code should use package-relative imports.

Public examples should import only from:

```python
from autoloop.simple import ...
```

or:

```python
from autoloop import ...
```

Avoid fallback imports such as:

```python
try:
    from autoloop_v3.core ...
except ModuleNotFoundError:
    from core ...
```

unless there is a documented test/runtime reason.

---

# 20. Documentation updates

Update active docs to state:

```text
project is greenfield
RouteContract removed
route metadata is optional RouteInfo / Route.summary
simple workflows are first-class
State is optional
prompt files are optional
artifact declarations are governed output surfaces, not exclusive write allow-lists
reads are optional context
requires are hard input preconditions
artifact schema is distinct from control_schema
provider/model defaults come from runtime config/CLI
WorkflowStep is a real graph step
system_step(fn) does not need on_<step>
no autoloop eject
```

Remove all active examples using `RouteContract`.

---

# 21. Tests

Add or update the following tests.

## 21.1 Simple workflow discovery

```python
class Simple(Workflow):
    a = step("Do A.")
    flow = chain(a)
```

Assert:

```text
compile_workflow(Simple) works
runtime loader finds it by file path
runtime loader finds it by module
capability inspection finds it
```

## 21.2 No State required

Simple workflow without explicit `State` compiles and runs.

## 21.3 `system_step(fn)`

Test returns:

```text
None
BaseModel
"done"
Event("done")
(state, "done")
(state, Event("done"))
```

All should reach expected routes.

## 21.4 `WorkflowStep`

Test:

```text
invokes child workflow
child SUCCESS -> done
child FAIL -> failed
child PAUSE question -> question
child PAUSE non-question -> blocked
writes output artifact
works in chain
review_step.needs_rework can route back to WorkflowStep
```

## 21.5 RouteContract removal

Tests:

```text
RouteContract not importable from autoloop
RouteContract not exported from core
provider models have no route_contracts field
capability payload has no route_contracts key
rendered prompt contains no "route contract"
active docs contain no RouteContract
```

## 21.6 Route metadata

Test:

```python
Route.to(next_step, summary="Custom summary", required_outputs=("report",))
```

and:

```python
step(..., route_infos={"done": RouteInfo(summary="Done summary")})
```

Assert precedence and conflict rules.

## 21.7 Reserved routes

For every step kind:

```text
question -> PAUSE
blocked -> PAUSE
failed -> FAIL
```

Assert provider/system/workflow returning those routes is legal without explicit declaration.

## 21.8 Reads/requires

Tests:

```text
missing read does not fail
missing require fails before execution
read path renders exists=false
declared artifact read renders exists correctly
prompt placeholder infers read, not require
ambiguous placeholder infers nothing
```

## 21.9 Artifact behavior

Tests:

```text
Json("analysis", Analysis) path is step-local
artifact schema validates file content
optional missing output does not fail
required output fails if missing
artifact schema does not become expected_output_schema
control_schema does become expected_output_schema
undeclared workspace file does not fail
```

## 21.10 Hooks

Tests:

```text
before hook runs
before hook mutates state
after hook runs
after hook mutates state
after hook overrides route by string
after hook overrides route by Event
conflicting AfterHookResult route/event fails
route override revalidates final route
artifacts re-resolved after after-hook state mutation
```

## 21.11 Provider rendering

Tests:

```text
readable inputs section exists
required inputs section exists
writable artifacts section says not exclusive allow-list
available routes use RouteInfo
control response format is shown
no route-contract terminology appears
```

---

# 22. Implementation order

Execute in this order:

1. Remove `RouteContract` exports and imports.
2. Delete `core/route_contracts.py`.
3. Remove `route_contracts` and `route_required_artifacts` fields from all models.
4. Finalize `RouteInfo` and `Route` metadata.
5. Update `Step` classes to use `route_infos`.
6. Add true `core.steps.WorkflowStep`.
7. Add direct `SystemStep(handler=...)`.
8. Update compiler dataclasses and route-info normalization.
9. Insert reserved routes during workflow normalization.
10. Update provider request/context/fake/rendering models.
11. Update engine request-control-contract generation.
12. Update engine finalization order and hook behavior.
13. Implement direct workflow-step execution in engine.
14. Update simple lowering for `step`, `review_step`, `system_step`, `workflow_step`.
15. Fix loader and capability discovery for simple declarations.
16. Implement final `reads` representation and semantics.
17. Remove provider/model/effort from simple helpers.
18. Update docs.
19. Update tests.
20. Run full test suite.
21. Run grep anti-regression checks for removed terms.

---

# 23. Definition of done

The implementation is complete when:

```text
A one-step simple workflow runs without State, entry, transitions, prompt files, RouteContract, session config, or metadata.

A multi-step simple workflow runs with chain(...).

review_step runs and needs_rework loops correctly.

system_step(fn) runs without on_<step>.

WorkflowStep is a real core graph step and invokes child workflows.

WorkflowStep can participate in verifier-gated loops.

Simple workflows are discoverable by path, module, and capability inspection.

RouteContract is absent from active public APIs, provider models, capability payloads, rendered prompts, docs, and tests.

Route summaries are represented only by RouteInfo / Route.summary / fallback inference.

Reserved routes are mechanically available for all step kinds.

reads are optional and do not fail when missing.

requires are hard target-step preconditions.

Artifact schemas validate files and never become provider control schemas.

control_schema explicitly controls provider expected_output_schema.

Undeclared workspace outputs are allowed.

before/after hooks work.

after can override route.

Artifacts are re-resolved after after-hook state mutation.

provider/model/effort simple parameters are removed.

All tests pass.

No autoloop eject or source-code expansion command exists.
```
