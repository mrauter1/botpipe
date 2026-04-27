Below is the full standalone revised plan.

---

# Standalone implementation plan for Autoloop v3 authoring simplification

You are working in the Autoloop v3 repository. Implement a progressive authoring model that makes simple workflows easy to write while preserving the existing deterministic runtime model.

The core objective is to remove accidental authoring ceremony from tier-1 workflows without weakening tier-3 explicitness. The existing strict runtime model, provider execution engine, filesystem artifacts, checkpointing, route validation, provider retries, and workflow graph semantics must remain intact. The current repository already has strict workflow discovery/validation, route-contract-oriented provider rendering, step classes, route/effect primitives, session continuity, and runtime extension seams; this plan refactors the authoring surface and normalizes it into the existing runtime concepts rather than replacing the engine. 

Do **not** implement `autoloop eject`, source-code expansion, source-code generation, or any command that rewrites a simple workflow into a full explicit workflow package.

## 1. Design goals

Implement a simpler authoring surface where a user can write:

```python
from pydantic import BaseModel
from autoloop.simple import Workflow, step, review_step, workflow_step, Json, Md, chain

class Analysis(BaseModel):
    summary: str
    severity: str

class IncidentBrief(Workflow):
    analysis = step(
        "Analyze the incident request and write a structured analysis.",
        out=Json("analysis", Analysis),
    )

    email = review_step(
        producer="Draft an executive email from {analysis}.",
        verifier="Accept if the email is accurate, concise, and executive-ready.",
        reads=["analysis"],
        out=Md("email"),
    )

    flow = chain(analysis, email)
```

This should compile to a normal deterministic Autoloop workflow with:

* `EmptyState` inferred.
* Entry inferred from `flow` or first unambiguous step.
* Inline prompt support.
* Step name inferred from assignment.
* Step-local artifact paths inferred.
* Optional route summaries inferred from route names and topology.
* No required route contracts.
* No provider `expected_output_schema` unless explicitly declared as a control schema.
* Target-step-owned input requirements through `requires`.
* Optional readable inputs through `reads`.
* Allowed undeclared workspace outputs.
* Standard review loop behavior for `review_step`.
* Support for `before` and `after` callbacks.
* `WorkflowStep` as a first-class graph node for child workflow invocation.

## 2. Non-goals

Do not implement:

1. `autoloop eject`.
2. Source-code expansion into explicit workflow classes.
3. Source-code generation migration tools.
4. Automatic `State` generation from prompt variables.
5. Automatic requiredness from prompt references.
6. Automatic provider `expected_output_schema` from artifact schema.
7. Mandatory workflow metadata.
8. Mandatory workflow package directory structure.
9. Mandatory prompt files.
10. Mandatory route summaries.
11. Mandatory route contracts.
12. A second runtime engine.
13. A ban on undeclared workspace outputs.
14. Full CLI validation-profile machinery unless it already exists or is trivial to wire.

## 3. Core architectural rules

Preserve these rules:

1. The runtime remains narrow and mechanical.
2. The workflow owns global control flow.
3. The provider owns cognition inside the current step contract.
4. Filesystem artifacts remain durable truth.
5. Declared artifacts are governed surfaces, not the provider’s entire write permission set.
6. Undeclared workspace outputs are allowed unless runtime policy forbids them.
7. Route contracts disappear from public authoring.
8. Required input artifacts are owned by the target step.
9. Route-level required outputs are optional and rare.
10. Prompt-referenced artifacts may be inferred as readable inputs, never required inputs.
11. Artifact schemas validate artifact files.
12. Provider control schemas validate compact provider route/control payloads only when explicitly configured.
13. Runtime/provider defaults come from runtime config or CLI.
14. Workflow-level provider overrides remain optional.
15. Strict validation remains available by opt-in.
16. Simple `Workflow` authoring must not perform class-definition/import-time validation by default.
17. `WorkflowStep` must be allowed inside verifier-gated loop topologies.
18. `after` callbacks may override the selected route.

## 4. Public API target

Create a single ergonomic public API surface:

```text
autoloop/simple.py
```

Expose from `autoloop.simple`:

```python
Workflow
StrictWorkflow
step
review_step
workflow_step
system_step
chain
Json
Md
Text
Raw
Prompt
Route
RouteInfo
WorkflowStep
```

Also re-export stable public items from `autoloop/__init__.py` when safe.

Avoid adding another competing public surface unless necessary. Treat `core/*` as internal kernel/compatibility code. Users should not need to import from `core`.

## 5. Compatibility strategy

Do not break existing bundled workflows in the first pass.

Implement in phases:

### Phase 1: Add new model beside current strict model

* Add `autoloop.simple.Workflow` as the non-strict simple authoring base.
* Keep the existing strict/core `Workflow` behavior initially if needed for existing bundled workflows.
* Add `StrictWorkflow` for explicit strict class-definition validation.
* Add compatibility adapters for old `route_contracts` where necessary.
* Do not document `RouteContract` in the new public API.

### Phase 2: Migrate internals and public docs

* Replace route-contract-oriented public examples with route metadata / inferred summaries.
* Update bundled workflows or provide compatibility shims.
* Ensure provider rendering no longer requires or refers to “route contracts” except through temporary compatibility.

### Phase 3: Remove public `RouteContract`

* Remove `RouteContract` from public exports.
* Keep an internal deprecated adapter only if tests/bundled workflows still need it temporarily.
* Eventually delete `route_contracts.py` after all internal references are gone.

## 6. Workflow and strict validation model

### 6.1 Non-strict simple workflow

Implement a non-strict simple workflow base:

```python
class Workflow:
    __workflow_abstract__ = True
    __strict_workflow__ = False
```

This class must not trigger full validation at import/class-definition time.

Validation should occur lazily at compile/run time, using prototype validation.

### 6.2 Strict workflow

Implement:

```python
class StrictWorkflow(Workflow, metaclass=WorkflowMeta):
    __strict_workflow__ = True
```

or equivalent.

`StrictWorkflow` may preserve existing import-time validation.

If changing the existing top-level `Workflow` immediately would break bundled workflows, leave the existing strict class in place temporarily and introduce the new base through `autoloop.simple.Workflow`.

### 6.3 Optional `State`

If a workflow does not define nested `State`, synthesize/use:

```python
from pydantic import BaseModel

class EmptyState(BaseModel):
    pass
```

Do not require empty state declarations.

`State` should become necessary only when:

* The author explicitly declares state fields.
* A hook/handler uses or mutates state.
* A state projection feature is later added.
* `build_output` uses state.
* Strict validation requires explicit state.

## 7. Step name inference

Allow:

```python
analysis = step("Analyze the request.")
```

instead of:

```python
analysis = LLMStep(name="analysis", ...)
```

Implementation requirements:

* Make the user-facing step name optional in simple helpers.
* Use Python descriptor `__set_name__(owner, attr_name)` or equivalent workflow discovery to bind the class attribute name as the step name.
* If an explicit `name` is provided, preserve it.
* In prototype validation, explicit name and attribute name may differ.
* In strict validation, warn or error on name drift depending policy.
* Compiled names must be stable and deterministic.

## 8. Prompt model

### 8.1 Add explicit prompt constructors

Enhance `Prompt`:

```python
Prompt.inline(text: str)
Prompt.file(path: str | Path)
```

`ResolvedPrompt` should carry:

```python
path: str | None
text: str
source: Literal["inline", "file", "registry"]
```

### 8.2 Simple API prompt behavior

In `autoloop.simple` helpers:

* raw `str` means inline prompt
* `Path` means file prompt
* `Prompt.inline(...)` means inline prompt
* `Prompt.file(...)` means file prompt

In strict/core APIs, avoid ambiguous string heuristics if possible. Preserve backward compatibility only where necessary.

### 8.3 Lazy resolution

Prompt file resolution should happen at compile/run time, not class-definition time.

Missing prompt files must fail with clear errors.

## 9. Artifact helpers and output policy

### 9.1 Add lightweight artifact helpers

Implement:

```python
Json(name, schema=None, *, path=None, required=False)
Md(name, *, path=None, required=False)
Text(name, *, path=None, required=False)
Raw(name, *, path=None, required=False)
```

Semantics:

* `name` is the artifact name.
* `path` is optional.
* `required=False` by default.
* `schema` validates file content for `Json`.
* Artifact schema does **not** become provider expected-output schema.

### 9.2 Step-local inferred paths

If path is omitted, infer deterministic step-local paths:

```text
{workflow_folder}/{step_name}/{artifact_name}.json
{workflow_folder}/{step_name}/{artifact_name}.md
{workflow_folder}/{step_name}/{artifact_name}.txt
{workflow_folder}/{step_name}/{artifact_name}
```

For `Raw`, use no automatic extension unless a better existing convention exists.

### 9.3 Declared artifacts are governed surfaces

Declared artifacts mean:

* named
* typed
* optionally required
* validated when required or present
* rendered to provider as writable artifacts
* available for symbolic references
* available to downstream `reads`/`requires`
* available as workflow outputs

Declared artifacts do **not** mean the provider is forbidden from writing other workspace files.

Do not implement automatic “recent changed files” prompt sections for now. Let steps inspect the workspace themselves.

### 9.4 Artifact schema vs provider control schema

If a step has:

```python
out=Json("analysis", Analysis)
```

do **not** set provider `expected_output_schema=Analysis`.

Default provider control payload may remain minimal:

```json
{"tag": "done", "reason": "..."}
```

Only configure provider expected-output schema if the author explicitly passes:

```python
control_schema=SomeControlPayload
```

or equivalent.

## 10. Reads vs requires

### 10.1 Add `reads`

Extend steps to support:

```python
reads: tuple[Artifact | str, ...]
requires: tuple[Artifact | str, ...]
```

Semantics:

* `reads` are optional readable artifacts.
* Missing `reads` do not fail execution.
* `requires` are hard target-step input preconditions.
* Missing `requires` fail before step execution.

### 10.2 Prompt references infer reads only

Parse prompt placeholders.

If a placeholder unambiguously refers to a known artifact, infer it as a `read`.

Never infer requiredness.

Placeholder rules:

```text
{artifacts.analysis} -> artifact read
{analysis} -> artifact read only if unambiguous
{step.analysis} -> artifact read if known
{state.foo} -> state field
{params.foo} -> workflow parameter
{input.foo} -> workflow input
{item.title} -> work-item context
{run_folder} -> runtime context
```

For bare placeholders:

* Infer artifact read only if no same-name input, param, state field, or context field exists.
* If ambiguous, do not infer.
* In prototype validation, record a warning if warnings infrastructure exists.
* In strict validation, require qualification.

## 11. Route model without RouteContract

### 11.1 Remove RouteContract from public authoring

`RouteContract` should disappear from public authoring.

Do not document it.

Do not export it from `autoloop.simple`.

Eventually remove it from top-level public exports after compatibility is addressed.

### 11.2 Add `RouteInfo`

Implement:

```python
@dataclass(frozen=True)
class RouteInfo:
    summary: str | None = None
    required_outputs: tuple[str, ...] = ()
    handoff: str | None = None
```

This is optional route metadata only.

### 11.3 Extend `Route`

Extend `Route`:

```python
@dataclass(frozen=True, slots=True)
class Route:
    target: object | None = None
    effects: tuple[Effect, ...] = ()
    summary: str | None = None
    required_outputs: tuple[str, ...] = ()
    handoff: str | None = None
```

Update constructors:

```python
Route.to(target, *effects, summary=None, required_outputs=(), handoff=None)
Route.complete(*effects, summary=None, required_outputs=(), handoff=None)
Route.pause(*effects, summary=None, required_outputs=(), handoff=None)
Route.fail(*effects, summary=None, required_outputs=(), handoff=None)
```

### 11.4 Route summaries

Route summaries are optional and resolved by priority:

1. `Route.summary`
2. step-level `route_summaries[tag]`
3. standard fallback:

   * `done`: “Step completed and selected the default completion route.”
   * `accepted`: “Verifier accepted the governed output.”
   * `needs_rework`: “Verifier requested local repair within the same work boundary.”
   * `needs_replan`: “The current work boundary appears incorrect and replanning is needed.”
   * `question`: “Execution paused for a user answer.”
   * `blocked`: “Execution paused because the step is blocked.”
   * `failed`: “Execution failed.”
4. topology fallback:

   * “Routes from `<source>` to `<target>`.”

Summaries are for provider rendering and inspection only. They are not contracts.

### 11.5 Route-level required outputs

Route-level output obligations are optional and rare.

Use:

```python
Route.to(next_step, required_outputs=("report",))
```

Terminology:

* `requires` = target step input preconditions.
* `required_outputs` = selected route output obligations.
* Avoid generic `required_artifacts` where it conflates input and output.

### 11.6 Validation changes

Update validation so:

* Missing route metadata is never an error.
* Route metadata for unknown routes is an error if explicitly declared.
* `Route.required_outputs` must reference known produced artifacts if declared.
* Application routes are valid when present in transitions or generated by a helper.
* Reserved routes are globally understood.

Remove validation that requires every application route to have a route contract.

## 12. Reserved routes

Reserved routes should be globally understood:

```text
question -> PAUSE
blocked -> PAUSE
failed -> FAIL
```

Do not require authors to redeclare them.

If runtime policy wants a different `blocked` behavior, make it runtime config/policy, not authoring boilerplate.

## 13. Step helpers

### 13.1 `step(...)`

Implement:

```python
step(
    prompt,
    *,
    reads=(),
    requires=(),
    out=None,
    outputs=(),
    routes=None,
    route_summaries=None,
    before=None,
    after=None,
    control_schema=None,
    provider=None,
    model=None,
    effort=None,
    retry=None,
    session=None,
)
```

Semantics:

* Single-provider LLM step.
* Raw string prompt means inline prompt in simple API.
* `Path` means prompt file.
* `out` is one primary declared output.
* `outputs` is multiple declared outputs.
* `reads` are optional inputs.
* `requires` are hard input preconditions.
* `control_schema` maps to provider expected-output schema.
* If routes omitted, default route is `done`.
* No route contracts.

### 13.2 `review_step(...)`

Implement:

```python
review_step(
    producer,
    verifier,
    *,
    reads=(),
    requires=(),
    out=None,
    outputs=(),
    accepted="accepted",
    rework="needs_rework",
    before=None,
    after=None,
    route_summaries=None,
    provider=None,
    model=None,
    effort=None,
    retry=None,
    session=None,
)
```

Semantics:

* Verifier-gated pair/review step.
* Standard route behavior:

  * `accepted -> next/SUCCESS`
  * `needs_rework -> same review step`
* Producer cannot self-accept.
* Verifier controls accepted/rework route selection.
* Route summaries are optional and inferred if absent.
* Runtime/provider defaults come from config/CLI unless overridden.

### 13.3 `system_step(...)`

Implement:

```python
system_step(
    fn,
    *,
    reads=(),
    requires=(),
    outputs=(),
    routes=None,
    before=None,
    after=None,
)
```

Semantics:

* Deterministic local/system callback.
* Does not call provider.
* Can return event/route result.
* Supports before/after hooks.

## 14. WorkflowStep

### 14.1 Add core class

Implement:

```python
class WorkflowStep(Step):
    kind = "workflow"
```

### 14.2 Add helper

Implement:

```python
workflow_step(
    workflow,
    *,
    message=None,
    message_from=None,
    params=None,
    input=None,
    reads=(),
    requires=(),
    out=None,
    outputs=(),
    routes=None,
    before=None,
    after=None,
)
```

### 14.3 Semantics

`WorkflowStep`:

* Invokes a child workflow through existing runtime machinery.
* Is deterministic orchestration, not a provider step.
* Can be any graph node.
* Can be the source or target of transitions.
* Can be inside verifier-gated loop topologies.
* Can be routed back to by a verifier’s `needs_rework`.
* Does not need to be embedded inside `PairStep` internals in the first implementation.

Minimum acceptable behavior:

```text
WorkflowStep -> review verifier -> accepted next
                            -> needs_rework back to WorkflowStep
```

### 14.4 Child terminal mapping

Default mapping:

```text
child SUCCESS -> done
child PAUSE   -> blocked or question based on child last event if available
child FAIL    -> failed
```

Allow author override through routes or `after` hook.

### 14.5 Outputs

If `out` or `outputs` configured:

* Write child result summary/metadata artifact.
* Include child terminal status.
* Include child run id.
* Include child output artifact references when available.

## 15. `chain(...)` and flow inference

### 15.1 Add `chain`

Implement:

```python
chain(step1, step2, step3)
chain((step1, "done"), (step2, "accepted"), SUCCESS)
```

Semantics:

* If a step has exactly one non-reserved completion route, route may be inferred.
* For `step(...)`, completion route is `done`.
* For `review_step(...)`, completion route is `accepted`; `needs_rework` loops to same step.
* Final step completion routes to `SUCCESS`.
* No route contracts.

### 15.2 Add `flow` alias

Allow:

```python
flow = chain(a, b, c)
```

as an alias for transitions.

If both `flow` and `transitions` exist:

* Merge if non-conflicting.
* Raise if conflicting.

### 15.3 Entry inference

If no explicit `entry`:

1. If `flow` exists, entry is the first source step in flow.
2. Else if exactly one step exists, entry is that step.
3. Else if graph has exactly one root, infer that root.
4. Else raise a compile/run validation error.

## 16. Hooks and callbacks

### 16.1 Add step-level hooks

All step kinds support:

```python
before=None
after=None
```

### 16.2 `before` behavior

Runs before step execution.

May:

* mutate files
* return new state
* return `None`
* raise failure/blocking errors according to current runtime behavior

Accepted signatures should be flexible:

```python
before(ctx)
before(state, ctx)
```

Use introspection to call supported signature.

### 16.3 `after` behavior

Runs after step execution and raw outcome parsing.

May:

* mutate files
* return new state
* return route tag string
* return `Event`
* return `AfterHookResult`
* return `None`

Define:

```python
@dataclass(frozen=True)
class AfterHookResult:
    state: BaseModel | None = None
    route: str | None = None
    event: Event | None = None
    handoff: str | None = None
```

If both `event` and `route` are present, reject ambiguity unless route equals `event.tag`.

Accepted signatures should be flexible:

```python
after(ctx, outcome)
after(state, outcome, artifacts, ctx)
after(ctx, outcome, route)
```

### 16.4 After can override route

This is required.

When `after` changes route:

1. Validate final route exists.
2. Recompute route target.
3. Recompute route required outputs.
4. Enforce required outputs for final selected route.
5. Record that hook overrode route in trace/event metadata where available.

### 16.5 Hook ordering

Use this order for provider steps:

```text
runtime extension before_step
workflow step before hook
resolve artifacts
execute provider step
parse outcome
validate raw outcome shape
validate candidate route exists
workflow step after hook
if hook changed route/event/state, normalize result
validate final route exists
enforce final route required outputs
validate required/available artifacts for final route
apply route effects
runtime extension after_step
checkpoint/transition
```

Do not perform final route-specific artifact enforcement before `after`, because `after` may change the route.

For `WorkflowStep`:

```text
before hook
invoke child workflow
build child result outcome/event
validate candidate route
after hook
validate final route
apply route effects
```

For `SystemStep`:

```text
before hook
call system function
validate candidate event/route
after hook
validate final route
apply route effects
```

## 17. Provider request/rendering model

### 17.1 Rename route fields

Provider request/response models should not expose `route_contracts` after migration, except temporary compatibility shims/tests.

Replace with:

```python
route_infos: Mapping[str, RouteInfo]
route_required_outputs: Mapping[str, tuple[str, ...]]
```

### 17.2 Add readable artifacts

Provider turn context should include:

```python
readable_artifacts: tuple[ProviderArtifactRef, ...]
required_artifacts: tuple[ProviderArtifactRef, ...]
writable_artifacts: tuple[ProviderArtifactRef, ...]
route_infos: Mapping[str, RouteInfo]
route_required_outputs: Mapping[str, tuple[str, ...]]
expected_output_schema: Mapping[str, Any] | None
```

Here `required_artifacts` refers only to required **inputs**. Consider renaming internally to `required_input_artifacts` if feasible, but preserve compatibility carefully.

### 17.3 Rendering sections

Provider rendering should show:

1. Step name and role.
2. Workflow-authored prompt.
3. Runtime step contract:

   * readable inputs
   * required inputs
   * writable declared artifacts
   * available routes
   * route targets/summaries
   * route-required outputs, if any
   * control payload schema, only if explicitly declared
4. Retry feedback, if any.
5. Route handoff, if any.

Do not mention “route contracts” in rendered prompts except compatibility paths.

Do not imply undeclared files cannot be written.

If no control schema exists, omit the “Output payload” section or clearly say no structured control payload is required beyond route selection.

## 18. Engine/compiler changes

### 18.1 CompiledStep

Extend compiled step metadata:

```python
reads
requires
produces
available_routes
route_infos
control_schema / expected_output_schema
before_hook
after_hook
```

If temporary compatibility requires keeping old names internally, ensure they no longer imply public `RouteContract`.

### 18.2 CompiledRoute

Extend:

```python
source_step
tag
target
effects
summary
required_outputs
handoff
```

### 18.3 Request control contract

Update `_request_control_contract` equivalent to produce:

```python
{
    "expected_output_schema": step.control_schema,  # only explicit
    "available_routes": ...,
    "route_infos": ...,
    "readable_artifacts": ...,
    "required_artifacts": ...,       # required inputs only
    "writable_artifacts": ...,
    "route_required_outputs": ...,
    "retry_feedback": ...,
    "route_handoff": ...,
    "attempt": ...,
    "max_attempts": ...,
}
```

### 18.4 Output enforcement

Replace route-contract-derived enforcement.

New priority:

1. `CompiledRoute.required_outputs`
2. produced artifacts with `required=True`
3. no additional required outputs

Optional typed output artifacts validate only if they exist.

Required outputs fail if missing.

### 18.5 Reads vs requires enforcement

Execution fails only for missing `requires`.

`reads` render with `exists=False` if missing.

### 18.6 WorkflowStep execution

Add `step.kind == "workflow"` execution path.

It must:

* resolve required inputs
* run before hook
* invoke child workflow
* map child terminal to route
* write configured child result output if present
* run after hook
* allow after hook route override
* apply route effects
* checkpoint/transition normally

## 19. RouteContract migration

Search for:

```text
RouteContract
route_contracts
normalize_route_contract
normalize_route_contracts
required_artifacts
```

Update all relevant files:

```text
core/route_contracts.py
core/__init__.py
core/steps.py
core/compiler.py
core/validation.py
core/engine.py
core/providers/models.py
core/providers/rendering.py
core/providers/fake.py
stdlib/*
workflows/*
docs/*
tests/*
```

Migration strategy:

1. Introduce `RouteInfo` and `Route` metadata.
2. Keep `RouteContract` as deprecated internal adapter if necessary.
3. Stop exporting/documenting `RouteContract`.
4. Convert `route_contracts` into `route_infos` where compatibility required.
5. Remove strict validation requiring route contracts.
6. Migrate built-in workflows and helpers.
7. Delete `route_contracts.py` only after all references are gone.

## 20. BoardMutation trap

Current engine has a public `BoardMutation` effect branch that raises at runtime. This is a trap. 

If low-risk in this implementation pass:

* Fail at compile time when public workflows use `BoardMutation` and the feature is not implemented/enabled.

If not low-risk:

* Leave as a follow-up.
* Do not let this block the main authoring simplification.

## 21. Validation profiles

### 21.1 Prototype validation

Default compile/run validation.

Must catch:

* duplicate step names
* invalid route targets
* impossible transitions
* unknown required inputs
* required artifact produced only after target step
* invalid artifact schemas
* invalid hook signatures
* invalid route override from hook
* invalid `WorkflowStep` child reference when statically resolvable

Must not require:

* explicit `State`
* metadata
* prompt files
* route summaries
* route contracts
* explicit sessions
* docs
* tests
* package layout

### 21.2 Strict validation

Strict validation is opt-in.

It may require or warn about:

* explicit `State`
* external prompt files
* route summaries
* declared inputs/outputs
* explicit session policy
* docs/tests/checklists, if project policy requires them

Implement strict validation as an internal function/flag first. CLI validation profile support is optional unless already present.

## 22. Documentation updates

Update authoring documentation to explain:

* `autoloop.simple`
* `Workflow` vs `StrictWorkflow`
* `step`
* `review_step`
* `workflow_step`
* `system_step`
* `chain`
* inline prompts
* prompt files
* `reads` vs `requires`
* declared vs undeclared outputs
* artifact schemas vs control schemas
* route metadata without RouteContract
* inferred route summaries
* before/after hooks
* optional strict validation
* no required metadata
* no mandatory package layout
* no mandatory prompt files

Remove all public examples using `RouteContract`.

Do not document any `autoloop eject` command.

## 23. Tests

Add or update tests for the following.

### 23.1 Simple authoring

* Single `step(...)` workflow compiles with no explicit `State`.
* Step name inferred from assignment.
* Entry inferred from single step.
* Entry inferred from `flow`.
* `chain(a, b)` infers transitions and terminal success.
* Raw string prompt in simple API resolves inline.

### 23.2 Prompts

* `Prompt.inline` works.
* `Prompt.file` works.
* `Path("prompt.md")` in simple API loads a file.
* Missing prompt file fails clearly.
* Prompt placeholders infer reads but not requires.
* Ambiguous bare placeholder does not infer artifact read.

### 23.3 Artifacts

* `Json("analysis", Analysis)` creates typed declared output.
* Default artifact path is step-local.
* Artifact schema validates file content if file exists.
* Artifact schema does not become provider expected-output schema.
* `required=False` by default.
* Required declared output fails if missing.
* Optional declared output does not fail if missing.
* Undeclared workspace files do not fail validation.

### 23.4 Reads vs requires

* Missing `reads=["analysis"]` does not fail.
* Missing `requires=["analysis"]` fails before step execution.
* Target step owns required input enforcement.
* Route metadata does not create input requirements.

### 23.5 Routes

* No route contracts required.
* Route summaries inferred from route tag.
* Explicit `Route.summary` renders.
* Step-level route summary renders.
* Unknown provider route fails.
* `Route.required_outputs` enforces only when declared.
* Reserved routes work without explicit metadata.
* Provider rendered prompts do not mention route contracts.

### 23.6 Review step

* `review_step` generates accepted route to next/SUCCESS.
* `needs_rework` loops to same step.
* Verifier controls accepted route.
* Producer cannot self-accept.
* Runtime retry/rework defaults come from runtime config unless overridden.

### 23.7 Hooks

* `before` hook runs before provider/system/workflow step.
* `before` can mutate state.
* `after` hook runs after outcome parsing.
* `after` can mutate state.
* `after` can override route with string.
* `after` can override route with `Event`.
* Invalid route override fails clearly.
* Hook route override causes required outputs for final selected route to be checked.
* Hook route override is recorded in trace/event metadata where available.

### 23.8 WorkflowStep

* `WorkflowStep` invokes child workflow.
* Child `SUCCESS` maps to default completion route.
* Child `FAIL` maps to failed route.
* Child `PAUSE` maps to blocked/question behavior.
* WorkflowStep output artifact is written if configured.
* WorkflowStep can appear in `chain`.
* WorkflowStep can be part of verifier-gated loop topology where verifier `needs_rework` routes back to WorkflowStep.
* WorkflowStep is not prohibited inside loops.

### 23.9 Validation modes

* Simple `Workflow` does not perform full import-time validation.
* `StrictWorkflow` validates at class definition time or through explicit strict validation.
* Prototype validation catches duplicate step names, invalid route targets, invalid schemas, and unknown required inputs.
* Prototype validation does not require metadata, explicit route summaries, prompt files, docs, tests, or explicit `State`.

### 23.10 Public API and compatibility

* `RouteContract` is not exported from `autoloop.simple`.
* Public docs contain no `RouteContract` examples.
* Existing bundled workflows still compile or have compatibility shims.
* Existing tests keep passing unless they explicitly assert removed public RouteContract behavior.
* Provider request/fake provider tests updated from route contracts to route infos.
* No `autoloop eject` command exists.

## 24. Revised implementation order

Use this order to reduce breakage:

1. Add `Prompt.inline` / `Prompt.file`.
2. Add `RouteInfo` and route metadata fields on `Route`.
3. Add `reads` separate from `requires`.
4. Update provider models/rendering to support route info, readable inputs, required inputs, writable outputs, and route-required outputs while temporarily accepting old fields.
5. Add `Json`, `Md`, `Text`, `Raw` helpers.
6. Add `autoloop/simple.py`.
7. Add `step`, `review_step`, `system_step`, and `chain`.
8. Add `EmptyState` and entry inference for simple workflows.
9. Relax route-contract validation; keep compatibility adapter if needed.
10. Add before/after hooks with after route override.
11. Add `WorkflowStep` as graph node.
12. Add non-strict simple `Workflow` and `StrictWorkflow` without breaking existing core workflows.
13. Migrate tests.
14. Migrate docs and public exports.
15. Remove or deprecate public `RouteContract`.
16. Optional low-risk cleanup: BoardMutation compile-time guard.

## 25. Acceptance criteria

The implementation is complete when all of the following are true:

1. A one-step workflow can be written in one file with no explicit `State`, no metadata, no prompt file, no route contracts, no session config, and no explicit `entry`.
2. A two-step workflow can be written with `chain(...)`.
3. A review-gated workflow can be written with `review_step(...)`, and `needs_rework` loops correctly.
4. `RouteContract` is gone from documented/public authoring.
5. Route summaries are optional and inferred when absent.
6. Required input enforcement is target-step-owned through `requires`.
7. Prompt references may infer readable inputs, never required inputs.
8. Artifact schemas validate files but do not set provider expected-output schemas.
9. Provider expected-output schema is absent unless explicit `control_schema` is provided.
10. Undeclared workspace outputs are allowed.
11. `before` and `after` hooks work.
12. `after` can override route.
13. Route override triggers validation/enforcement for the final selected route.
14. `WorkflowStep` works as a first-class graph node.
15. `WorkflowStep` can be part of verifier-gated loop topologies.
16. Simple `Workflow` does not perform full import-time metaclass validation.
17. Strict validation remains available by opt-in.
18. Existing bundled workflows compile or have compatibility shims.
19. Existing runtime determinism, checkpointing, route validation, artifact validation, provider retry behavior, and reserved routes remain intact.
20. There is no `autoloop eject` command or source-generation upgrade path.

## 26. Final implementation guidance

Be conservative with engine changes. Prefer adding a normalization/authoring layer that compiles simple declarations into the existing runtime model. Where the current strict runtime model forces accidental authoring ceremony, relax validation and move explicitness into opt-in strict validation.

Do not remove the ability to write fully explicit workflows. Do remove the requirement that every workflow start fully explicit.
