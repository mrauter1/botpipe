# Framework authoring-flexibility change specification

## 0. Purpose

Improve workflow authoring by removing rigidity that forces authors to make runtime-created data appear statically available, expose generic failure routes to providers, or hand-code common scoped-work mechanics.

The framework must continue to validate static contracts early, but it must defer validation of runtime-created data until the run reaches the code path that needs that data.

The current codebase already has the relevant foundations: route injection and provider route construction live in discovery/engine code, worklist selections are currently initialized eagerly in engine runtime, artifact templates already understand `item`/`worklist` placeholders, and board/source abstractions already support load/select/validate/scaffold-like behavior.  

---

# 1. Guiding principles

## 1.1 Validate static contracts early

Compile/discovery time should validate:

```text
workflow topology
step names
route names
declared worklist names
scoped-step references to declared worklists
artifact declaration shape
artifact reference ambiguity
prompt placeholder syntax
known static namespaces
callback existence and basic callable shape
```

## 1.2 Validate runtime-created data lazily

Runtime should validate:

```text
generated worklist contents
artifact-backed board payloads
selected work items
item-scoped artifact paths
runtime-created prompt context
semantic artifact validation
child workflow outputs
```

## 1.3 Keep runtime failures runtime-owned

The provider should not be asked to choose generic runtime failure routes. Runtime failures should remain handled through retry/failure contexts.

Examples:

```text
provider transport failure        → runtime retry/failure context
malformed provider output         → runtime retry/failure context
illegal provider route            → runtime retry/failure context
missing required output artifact  → runtime retry/failure context
invalid output artifact           → runtime retry/failure context
```

## 1.4 Expose only domain-relevant routes to providers

The provider route contract should contain authored domain routes plus policy-allowed interactive routes.

Do not inject generic `blocked` or `failed` as provider-visible routes.

## 1.5 Reuse existing abstractions

Do not create a parallel board/worklist/structured-validation subsystem. Reuse or adapt the existing board/source/selector and structured artifact validation concepts already present in the codebase. The framework layer already defines board sources with `ensure`, `load`, `validate`, `select`, `set_status`, `write`, prompt rendering, and mutation classification capabilities. 

---

# 2. Non-goals

Do not implement or modify a specific workflow package as part of this change.

Do not add a broad flow DSL.

Do not unify every step kind into a single public abstraction.

Do not weaken retry behavior, checkpointing, artifact validation, provider boundary checks, or typed output validation.

Do not preserve compatibility with the current default `blocked`/`failed` route injection behavior. Tests should be updated to the new contract.

---

# 3. Milestone A: route policy and lazy scoped runtime

Milestone A is the runtime-semantics milestone. It should land before authoring sugar.

It includes:

```text
runtime interaction policy
removal of default blocked/failed route injection
policy-gated question route exposure
removal of hard-coded blocked/failed payload validation
lazy worklist materialization
lazy work-item session binding
checkpoint/resume compatibility for lazy selections
inspection/static-graph updates for route policy
```

---

## 3.1 Runtime interaction policy

### Problem

The current route-injection path adds default control routes. Provider-facing steps currently get `question`, `blocked`, and `failed`; Python/child workflow steps can get `failed`. 

This makes provider contracts too broad and encourages generic provider outcomes instead of domain-specific routes or runtime-owned failures.

### New behavior

Default control route behavior must be:

```text
question:
  available to provider only when runtime is interactive / not full-auto

blocked:
  never injected by default

failed:
  never injected by default
```

`blocked` and `failed` are ordinary route names if explicitly authored.

### New policy model

Add a small runtime policy object.

Suggested location:

```text
autoloop/core/providers/models.py
```

or:

```text
autoloop/core/runtime_policy.py
```

Suggested model:

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class RuntimeInteractionPolicy:
    allow_provider_questions: bool = True
```

Runner/config plumbing must set:

```python
RuntimeInteractionPolicy(
    allow_provider_questions=not full_auto,
)
```

Direct `Engine(...)` construction should default to interactive behavior:

```python
interaction_policy = RuntimeInteractionPolicy(allow_provider_questions=True)
```

### Engine constructor change

Add an optional keyword argument:

```python
Engine(
    ...,
    interaction_policy: RuntimeInteractionPolicy | None = None,
)
```

Store:

```python
self.interaction_policy = interaction_policy or RuntimeInteractionPolicy()
```

### Full-auto semantics

```text
full_auto = false:
  provider may receive question when the step allows auto question support

full_auto = true:
  provider must not receive the default question route
```

If a provider returns `question` when the route is not in the provider-visible route contract, the existing illegal-route retry path should handle it.

---

## 3.2 Replace reserved-route injection with explicit control-route capability

### Current behavior to change

The current `_inject_reserved_routes(...)` mutates transitions by adding default routes. That must stop for `blocked` and `failed`, and `question` must not be treated as a permanently provider-visible compile-time route. 

### Required behavior

Discovery/lowering should no longer add:

```text
blocked → AWAIT_INPUT
failed  → FAIL
```

by default.

For provider-facing steps, the framework may record that the step supports automatic question routing, but provider visibility must be resolved at provider-request time from runtime policy.

### Suggested authoring model

Replace the current boolean-ish `control_routes` behavior with a typed control policy.

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True, slots=True)
class ControlRoutes:
    question: Literal["auto", "always", "never"] = "auto"
```

Default by step kind:

```text
provider-facing steps:
  ControlRoutes(question="auto")

python / operation / child workflow steps:
  ControlRoutes(question="never")
```

Meaning:

```text
question="auto":
  provider-visible only when interaction_policy.allow_provider_questions is true

question="always":
  provider-visible regardless of interaction policy

question="never":
  not automatically available
```

This object must not contain `blocked` or `failed`.

### Minimal implementation option

If adding `ControlRoutes` is too invasive for the first patch:

* keep an internal boolean/enum flag on compiled steps, such as `allows_auto_question`
* derive it from existing `control_routes`
* stop injecting `blocked` and `failed`
* defer the public `ControlRoutes` object to a follow-up patch

The behavior contract is more important than the exact API shape.

---

## 3.3 Provider route construction must be runtime-policy-aware

### Problem

The engine currently builds provider-facing `available_routes` from compiled route metadata and `provider_visible`. 

That is the right boundary for applying full-auto behavior.

### Required behavior

Provider request construction must include:

```text
authored provider-visible routes
+
question only if:
  step allows default question route
  and interaction_policy.allow_provider_questions is true
```

Provider request construction must not include default `blocked` or default `failed`.

### Update these engine paths

Update provider-visible route helpers:

```text
_provider_available_routes_for_step(...)
_routes_for_step(...)
_route_required_writes_for_step(...)
```

So they apply runtime policy.

### Provider-visible route rules

For each step:

```text
include authored route if:
  route.provider_visible is true

include default question if:
  step supports auto question
  and interaction_policy.allow_provider_questions is true

exclude default question if:
  full_auto is true
```

### Route metadata for question

The default `question` route should still resolve to the existing await-input terminal internally.

But it should be treated as runtime control metadata, not as an authored domain route.

---

## 3.4 Remove hard-coded `blocked` and `failed` payload validation

### Problem

The current engine gives `blocked` and `failed` special validation semantics by requiring a non-empty reason. 

Once those routes are no longer reserved defaults, this hidden behavior is wrong.

### Required behavior

Only `question` remains special:

```text
question requires a non-empty question field
```

Remove all hard-coded checks equivalent to:

```python
if outcome.tag in {"blocked", "failed"} and not outcome.reason.strip():
    ...
```

and:

```python
if event.tag in {"blocked", "failed"} and not event.reason.strip():
    ...
```

If a workflow wants a reason for a `blocked`, `failed`, or `cannot_continue` route, it should declare an expected output schema or route-level payload contract.

### Runtime `Fail(...)` remains separate

The runtime-control object `Fail(...)` may still have its own type semantics. This change concerns route names, not direct runtime controls.

---

## 3.5 Explicit child workflow route mapping

### Problem

Child workflow result mapping can emit events such as:

```text
done
question
blocked
failed
```

The current child mapper may emit `failed` when a child fails and `blocked` when a child is awaiting input without a concrete question. 

If default `blocked`/`failed` routes are removed, child workflow steps that can emit these events must declare them explicitly.

### Required behavior

For child workflow steps:

```text
done:
  may remain the default completion route when no routes are declared

question:
  may be available if explicitly declared or policy-enabled as runtime control

blocked:
  must be explicitly declared if child mapping can emit it

failed:
  must be explicitly declared if child mapping can emit it
```

### Implementation options

Option A: strict mapper

* Keep mapper behavior.
* If child terminal maps to `blocked` or `failed`, require the current step to declare that route.
* Otherwise route validation fails with a clear error.

Option B: neutral mapper

* Map child failure/awaiting-input-without-question to a less opinionated route only if the workflow declared it.
* Otherwise fail with a clear runtime error explaining the missing route.

Preferred first implementation: **Option A**, because it preserves explicitness while minimizing mapper changes.

### Error message requirement

If a child workflow step returns a terminal that maps to an undeclared route, error message must include:

```text
child step name
child terminal
mapped route
declared routes
recommended fix: declare the route or change child-result mapping
```

---

## 3.6 Lazy worklist materialization

### Problem

The engine currently initializes all worklist selections at fresh-run start and restore starts by initializing all worklists before applying saved snapshots. 

This is too eager. Many practical workflows create the backing worklist during an earlier step.

### Required behavior

At compile time, validate only static worklist contracts:

```text
worklist name
selector declaration
source object shape/interface
item-state model
scoped step references a declared worklist
```

At runtime, validate worklist contents only when the worklist is first used:

```text
first scoped step using the worklist
first ctx.selection(...)
first ctx.current(...)
first ctx.worklist(...).selection/current
first artifact template requiring {item...}
first prompt render requiring item/worklist runtime context
first session continuity requiring current work item
```

### Fresh run behavior

Current:

```python
selections = initialize_worklist_selections(context)
```

New:

```python
selections = {}
```

Do not load any worklist source at run start.

### Resume behavior

Current restore initializes all worklists and then applies snapshots.

New behavior:

```text
restore only checkpointed selections
do not initialize absent selections
leave missing selections lazy
```

If a checkpoint has no `worklist_selections`, treat it as an empty mapping.

### Required StateRuntime API

Replace eager APIs with lazy APIs.

Current conceptual shape:

```python
initialize_worklist_selections(context) -> dict[str, Selection]
restore_worklist_selections(context, snapshots) -> dict[str, Selection]
```

New conceptual shape:

```python
restore_worklist_selections(context, snapshots) -> dict[str, Selection]
ensure_worklist_selection(context, worklist_name) -> Selection
```

`restore_worklist_selections` must:

```text
restore only snapshots that exist
not load any source for absent snapshots
not call initial_selection for every worklist
```

`ensure_worklist_selection` must:

```text
1. return existing selection if already materialized
2. resolve declared worklist
3. load/source-create as source policy allows
4. validate loaded items
5. apply selector
6. store selection in context
7. emit runtime event
8. return selection
```

### Source-driven missing-source behavior

Missing backing data is not always an error. The existing board source protocol supports an `ensure(ctx)` concept, and artifact-backed board sources can scaffold missing payloads. 

Therefore first-use behavior must be source-policy-driven:

```text
if source supports ensure/scaffold:
  source may create/scaffold backing data at first use

if source represents a required external input:
  missing source should fail at first use

if source creates an empty board:
  selection may still fail if empty selection is invalid
```

Do not hard-code “missing worklist source always fails.”

### Runtime error quality

When lazy materialization fails, raise `WorkflowExecutionError` with:

```text
worklist name
source type
source path if available
failure phase: ensure/load/validate/select
selector details if selection failed
underlying error text
```

Do not load unrelated worklists while reporting one worklist failure.

### Runtime events

Emit an event when lazy selection is first materialized:

```text
worklist_selection_resolved
```

Payload:

```json
{
  "worklist_name": "...",
  "mode": "...",
  "item_ids": ["..."],
  "current_index": 0,
  "lazy": true,
  "source": "...",
  "step_name": "..."
}
```

The exact event name can reuse existing selection-resolved event naming if present; the important distinction is that first-use lazy materialization is observable.

---

## 3.7 Context lazy-selection API

### Current behavior

`Context.selection(worklist)` raises if the selection is missing. 

### Required behavior

Add:

```python
def ensure_selection(self, worklist: Worklist[Any] | str) -> Selection[Any]:
    ...
```

Change:

```python
def selection(self, worklist):
    return self.ensure_selection(worklist)
```

Change:

```python
def current(self, worklist):
    return self.ensure_selection(worklist).current
```

Change `Context.item`:

```text
if no active worklist:
  return None

if active worklist exists:
  ensure its selection
  return current item
```

### Context-to-engine callback

`Context` does not own source loading by itself. It needs a callback installed by engine runtime, such as:

```python
context._set_worklist_selection_resolver(callback)
```

or reuse/extend the existing selection sync callback pattern.

The callback should call `StateRuntime.ensure_worklist_selection(...)`.

### WorklistRuntimeView

Update runtime view methods/properties so:

```text
view.selection
view.current
view.items
view.refresh()
view.advance()
view.set_current_status(...)
```

all operate on materialized selections and can trigger lazy materialization when necessary.

---

## 3.8 Scoped step entry sequencing

### Problem

The current engine loop reads current scoped item data before dispatching the step, for item-state keys, item runtime state, trace metadata, and session selection. 

With lazy selections, the selection must be materialized before any of those reads.

### Required sequencing

Before computing:

```text
current item state key
item_state_store
step_item_state_store
item runtime state on entry
step execution scope/item id
scoped artifact paths
work-item session key
pending handoff matching by item
```

ensure the scoped selection exists if `step.scope_name is not None`.

Suggested engine-loop insertion point:

```python
if step.scope_name is not None:
    context.ensure_selection(step.scope_name)
```

This should happen immediately after constructing `Context` for the step and before:

```python
_current_item_state_key(...)
_ensure_item_state_store(...)
_current_step_scope_item(...)
_notify_before_step(...)
step_dispatcher.execute(...)
```

Also keep a defensive ensure inside `StepDispatcher.execute(...)`, because artifact resolution may happen there too.

---

## 3.9 Checkpointing for lazy selections

### Required behavior

Only checkpoint materialized selections.

Do not materialize unused worklists just to save a checkpoint.

### Save behavior

`_snapshot_worklist_selections(...)` should continue to snapshot the selections mapping it receives, but that mapping should contain only materialized selections.

### Resume behavior

```text
if checkpoint.worklist_selections is None:
  selections = {}

if checkpoint.worklist_selections has some entries:
  restore only those entries

if a declared worklist has no checkpointed selection:
  leave it lazy
```

### Old checkpoint compatibility

If an older checkpoint has:

```text
no worklist_selections field
or null worklist_selections
```

treat it as empty.

Do not attempt to initialize every declared worklist during resume.

---

## 3.10 Lazy work-item session binding

### Problem

Work-item session continuity derives a session key from the current work item. Today that fails if the current item has not already been materialized. 

### Required behavior

Authors should be able to declare work-item continuity without manually opening sessions.

Conceptually:

```python
worker = Session(continuity=Continuity.work_item("phases"))
```

At runtime:

```text
when step needs session:
  ensure referenced worklist selection
  resolve current item
  derive stable session key
```

### Session key rule

For work-item continuity:

```text
domain: work_item
value: <worklist_name>:<item_dir_key_or_id>
```

Use `dir_key` if present, otherwise item ID.

### Scoped step behavior

For a scoped step whose session continuity references the same worklist:

```text
selection must be materialized before session resolution
current item must exist
session key binds to current item
```

### Non-scoped behavior

For non-scoped steps with work-item continuity:

```text
try to ensure referenced worklist selection
resolve current item
if no current item exists, fail clearly
```

Do not add a blanket compile-time prohibition against non-scoped work-item continuity. Some workflows intentionally operate on a current selection from a non-scoped step.

### Error message

If no current item is available:

```text
session '<name>' uses work-item continuity for worklist '<worklist>',
but no current work item is available.
```

Include the step name when available.

---

# 4. Milestone B: authoring ergonomics

Milestone B should land after Milestone A. It should not change the provider route contract further.

It includes:

```text
narrow worklist effects
repairable validation-step helper
artifact ownership diagnostics
late-bound prompt item/worklist context
inspection and docs polish
```

---

## 4.1 Narrow worklist effects

### Problem

Common scoped-work mechanics require imperative hook code:

```python
ctx.current_worklist.set_current_status("completed")
ctx.current_worklist.advance()
return Event("next")
```

The framework already has worklist runtime events and mutation operations, but the hook return surface only accepts events and direct controls. 

### Required behavior

Add a narrow typed effect object for worklist operations only.

Do not add a general effects DSL in this patch.

### New effect type

Suggested module:

```text
autoloop/core/effects.py
```

Suggested model:

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True, slots=True)
class WorklistEffect:
    worklist: str | None = None
    refresh: bool = False
    set_current_status: str | None = None
    reset_current_status: bool = False
    advance: bool = False
    exhausted: str | Event | None = None

    @classmethod
    def refresh_current(cls) -> "WorklistEffect": ...

    @classmethod
    def complete_current(cls) -> "WorklistEffect": ...

    @classmethod
    def advance_current(cls, *, exhausted: str | Event | None = None) -> "WorklistEffect": ...

    @classmethod
    def complete_and_advance(cls, *, exhausted: str | Event | None = None) -> "WorklistEffect": ...
```

### Supported operations

Initial version supports only:

```text
refresh worklist
set current item status
reset current item status
advance current selection
route to exhausted route/event when selection is exhausted
```

### Return normalization

Update hook/Python-step result normalization to accept:

```python
WorklistEffect
```

It should not replace existing accepted returns:

```text
None
str
Event
RequestInput
Goto
Fail
```

### Execution order

When applying a `WorklistEffect`:

```text
1. ensure referenced worklist selection
2. refresh if requested
3. set/reset current status
4. advance if requested
5. if exhausted and exhausted route/event is set, return that event
6. otherwise return no event override
```

### Validation

Invalid combinations:

```text
set_current_status and reset_current_status both set
worklist=None with no active worklist
advance with no current selection
set status with no current item
```

### Route helper sugar

Optional after base effect works:

```python
Route.complete_current("next", exhausted="after_items")
Route.advance("next", worklist="phases", exhausted="after_phases")
Route.refresh("next", worklist="surfaces")
```

These should lower to `on_taken=WorklistEffect(...)`.

---

## 4.2 Repairable validation-step helper

### Problem

Semantic validation currently requires repeated custom Python plumbing:

```python
try:
    validate()
except Error as exc:
    write_feedback()
    return Event("repair")
```

The codebase already has structured artifact contract utilities and feedback builders. 

### Required behavior

Add a helper that standardizes repairable validation routing and feedback writing without creating a new schema framework.

### Public API

Expose:

```python
validation_step
ValidationResult
```

Suggested model:

```python
from dataclasses import dataclass
from collections.abc import Sequence

@dataclass(frozen=True, slots=True)
class ValidationResult:
    ok: bool
    message: str | None = None
    title: str = "Validation Feedback"
    details: tuple[str, ...] = ()

    @classmethod
    def valid(cls) -> "ValidationResult": ...

    @classmethod
    def invalid(
        cls,
        message: str,
        *,
        title: str = "Validation Feedback",
        details: Sequence[str] = (),
    ) -> "ValidationResult": ...
```

Suggested helper:

```python
@validation_step(
    name="validate_manifest",
    requires=[MANIFEST],
    feedback=MANIFEST_FEEDBACK,
    success="done",
    repair="repair",
    failed=FAIL,
)
def validate_manifest(ctx) -> ValidationResult:
    error = validate_structured_artifact(...)
    if error is None:
        return ValidationResult.valid()
    return ValidationResult.invalid(error)
```

### Lowering behavior

The helper lowers to a Python step with routes:

```text
success route
repair route
optional failed route
```

If result is valid:

```python
Event(success)
```

If result is invalid:

```text
write feedback artifact
emit validation event
return Event(repair, reason=message, handoff=...)
```

If the function raises:

```text
if failed route declared:
  route/fail according to declared failed behavior
else:
  raise runtime error
```

### Feedback format

Default feedback artifact:

```markdown
# <title>

<message>

## Details
- ...
```

### Runtime events

Emit:

```text
validation_step_passed
validation_step_failed_repairable
```

Payload:

```text
step_name
feedback_artifact path
message
details
```

### Alignment with existing utilities

This helper must be usable with existing structured validation functions such as:

```text
validate_structured_artifact(...)
build_structured_artifact_validation_feedback(...)
```

Do not duplicate structured schema logic.

---

## 4.3 Artifact ownership diagnostics

### Problem

Compiled artifacts distinguish workflow-level artifacts and step-produced artifacts. The compiled artifact metadata includes `workflow_level` and `producer_steps`. 

Authors can accidentally declare the same artifact as both a workflow-level artifact and a step output.

### Required behavior

Fail clearly at compile time when artifact ownership is ambiguous.

### Rule

If the same artifact object or public artifact name is both:

```text
workflow-level
and
produced by one or more steps
```

raise `WorkflowValidationError`, unless an explicit managed/shared role is introduced later.

### Error message must include

```text
artifact name
qualified name if available
workflow-level declaration location/name
producer step names
recommended fix
```

Recommended fix:

```text
For external/input artifacts:
  keep as workflow class attribute and remove from step writes.

For produced artifacts:
  keep as step writes only and do not assign as workflow class attribute.

For managed/shared artifacts:
  use explicit managed role once available.
```

### Initial scope

Do not add `Artifact.input(...)`, `Artifact.produced(...)`, or `Artifact.managed(...)` in the first patch unless tests force it.

Start with diagnostics.

---

## 4.4 Late-bound prompt context for item/worklist runtime facts

### Problem

Prompt placeholder validation is useful, but currently treats `item` placeholders narrowly, especially through `item.state.<field>`, and rejects runtime item/worklist facts that are only meaningful during scoped execution. 

Artifact template resolution is a separate path and already handles `item`/`worklist` roots at runtime. 

### Required behavior

Keep early typo protection for static names, but allow late-bound runtime item/worklist placeholders.

### Keep static validation for

```text
placeholder syntax
known root namespaces
declared params fields
declared state fields
declared input fields
declared step names
declared artifact names when unambiguous
unknown static names
unknown worklist names
```

### Allow for scoped steps

For scoped steps, allow:

```text
item.id
item.title
item.status
item.dir_key
item.payload
item.payload.<any path>
item.state.<field>                # existing item-state behavior remains valid
```

### Allow explicit worklist references

If worklist name is declared, allow:

```text
worklist.<name>.current.id
worklist.<name>.current.title
worklist.<name>.current.status
worklist.<name>.current.dir_key
worklist.<name>.current.payload
worklist.<name>.current.payload.<any path>
worklist.<name>.item_ids
worklist.<name>.current_index
worklist.<name>.is_exhausted
```

### Compile-time validation

At compile time:

```text
validate worklist name exists
validate root namespace exists
do not require backing worklist source to exist
do not require selected items to exist
do not validate payload subpaths
```

### Runtime rendering

At runtime:

```text
lazy materialize referenced worklist
resolve current item
resolve payload path
raise clear WorkflowExecutionError if missing
```

Runtime error must include:

```text
placeholder text
step name
worklist name if applicable
missing field/path
```

### Artifact template resolution is separate

Do not conflate prompt placeholder validation with artifact path template resolution.

Artifact templates should:

```text
ensure active worklist selection before resolving {item...}
raise if required item is unavailable
never silently substitute empty strings for required item/worklist path components
```

---

## 4.5 Inspection and static graph updates

### Problem

Inspection/static graph outputs currently reflect compiled routes, which currently include injected routes. After this change, provider route visibility depends partly on runtime policy.

### Required behavior

Inspection should distinguish:

```text
authored routes
runtime control routes
provider-visible routes under a given interaction policy
```

### Minimal API

Expose either:

```python
inspect_workflow(..., interaction_policy=...)
```

or include separate sections:

```json
{
  "authored_routes": [...],
  "runtime_control_routes": [...],
  "provider_visible_routes": [...]
}
```

Avoid making every inspection payload overly verbose by default.

### Static graph

Default static graph should show authored topology.

It may annotate runtime control edges such as `question`, but:

```text
default blocked must not appear
default failed must not appear
question must be marked as runtime-control / policy-gated if shown
```

---

# 5. Detailed implementation plan

## 5.1 Milestone A implementation order

1. Add `RuntimeInteractionPolicy`.
2. Pass interaction policy from runner/config into `Engine`.
3. Stop injecting default `blocked` and `failed`.
4. Make default `question` provider-visible only when policy allows.
5. Remove hard-coded `blocked`/`failed` payload validation.
6. Update child workflow step route mapping expectations.
7. Make fresh runs start with empty worklist selections.
8. Make resume restore only checkpointed selections.
9. Add `ensure_selection(...)` to `Context`.
10. Wire lazy selection resolver from engine runtime into context.
11. Ensure scoped selection before item-state/session/artifact resolution.
12. Implement lazy work-item session binding.
13. Update checkpointing to snapshot only materialized selections.
14. Update runtime/inspection/static graph tests for route policy and lazy selections.

## 5.2 Milestone B implementation order

1. Add `WorklistEffect`.
2. Support `WorklistEffect` returns in hook/Python normalization.
3. Add optional `Route` helper sugar for worklist effects.
4. Add `ValidationResult`.
5. Add `validation_step(...)` helper.
6. Add artifact ownership diagnostic.
7. Expand prompt validation for late-bound item/worklist context.
8. Update docs and examples.

---

# 6. Required test plan

## 6.1 Route policy tests

1. Provider-facing step in interactive mode receives default `question`.
2. Provider-facing step in full-auto mode does not receive default `question`.
3. Provider-facing step never receives default `blocked`.
4. Provider-facing step never receives default `failed`.
5. Python step does not receive default `failed`.
6. Child workflow step does not receive default `failed`.
7. Explicit authored `blocked` route is preserved.
8. Explicit authored `failed` route is preserved.
9. Explicit `failed` route has no hidden non-empty-reason requirement.
10. Explicit `blocked` route has no hidden non-empty-reason requirement.
11. `question` still requires non-empty question text.
12. Provider returning `question` in full-auto mode is treated as illegal route and follows retry policy.
13. Provider transport failure still uses runtime retry/failure context, not provider route selection.
14. Malformed provider output still uses runtime retry/failure context.
15. Missing required output artifact still uses artifact validation retry/failure context.

## 6.2 Child workflow route tests

1. Child terminal `FINISH` maps to `done`.
2. Child terminal `FAIL` maps to `failed` only when step declares `failed`.
3. Child terminal `FAIL` without declared `failed` gives a clear runtime route error.
4. Child terminal `AWAIT_INPUT` with question maps to `question` when allowed.
5. Child terminal `AWAIT_INPUT` without question maps to `blocked` only when step declares `blocked`.
6. Child terminal `AWAIT_INPUT` without question and no `blocked` route gives clear runtime error.

## 6.3 Lazy worklist tests

1. Declared artifact-backed worklist compiles when backing artifact does not exist.
2. Fresh run does not load unused worklist source.
3. Non-scoped path can finish without materializing unused worklist.
4. First scoped step materializes the worklist.
5. `ctx.selection("x")` materializes the worklist.
6. `ctx.current("x")` materializes the worklist.
7. `ctx.item` materializes active scoped worklist.
8. Missing source with scaffold/ensure support is created at first use.
9. Missing source without scaffold/ensure support fails at first use.
10. Invalid source fails at first use with clear error.
11. Empty board fails at selection time if selector cannot select empty board.
12. Refresh reloads source after materialization.
13. Checkpoint includes only materialized selections.
14. Resume restores materialized selections without loading unrelated worklists.
15. Resume lazily materializes previously unused worklist later.
16. Old checkpoint with missing/null worklist selections resumes with empty lazy selection map.

## 6.4 Scoped sequencing tests

1. Scoped step materializes selection before item state key is computed.
2. Scoped step materializes selection before step execution ID is computed.
3. Scoped step materializes selection before scoped artifact path resolution.
4. Pending handoff item matching works after lazy selection.
5. Worklist sync updates item and step item state after advance.

## 6.5 Work-item session tests

1. Work-item continuity does not load source at compile time.
2. Scoped step with work-item continuity materializes selection before session resolution.
3. Different items produce different session keys.
4. Same item resumes same session key.
5. Session key uses `dir_key` when available.
6. Non-scoped step with work-item continuity fails clearly when no current item exists.
7. Non-scoped step with resolvable current item can use work-item continuity.

## 6.6 Worklist effect tests

1. Hook can return `WorklistEffect.complete_current()`.
2. Hook can return `WorklistEffect.advance_current(exhausted="done")`.
3. Python step can return a worklist effect.
4. Status effect persists through source-backed worklist.
5. Refresh effect reloads backing source.
6. Exhausted route is emitted only when selection is exhausted.
7. Worklist effect with no active worklist and no explicit worklist fails clearly.
8. Invalid combination of set/reset status fails clearly.
9. Effect mutation is captured in checkpoint state.

## 6.7 Validation helper tests

1. Valid `ValidationResult` routes to success.
2. Invalid `ValidationResult` writes feedback and routes to repair.
3. Invalid result includes handoff pointing to feedback artifact.
4. Details render deterministically.
5. Exception in validator routes to declared failed route if configured.
6. Exception in validator raises if no failed route configured.
7. Feedback artifact is declared as a write.
8. Helper works with existing structured artifact validation utilities.

## 6.8 Artifact ownership tests

1. Workflow-level input artifact compiles.
2. Step-produced artifact compiles when not workflow-level.
3. Same artifact declared workflow-level and step-produced fails.
4. Same public artifact name with ambiguous ownership fails clearly.
5. Error includes producer step names.
6. Error message includes recommended fix.

## 6.9 Prompt context tests

1. Scoped prompt can reference `{item.id}`.
2. Scoped prompt can reference `{item.title}`.
3. Scoped prompt can reference `{item.dir_key}`.
4. Scoped prompt can reference `{item.payload.foo}`.
5. Scoped prompt can still reference `{item.state.foo}` when item state declares `foo`.
6. Prompt can reference `{worklist.phases.current.id}` when `phases` exists.
7. Unknown worklist placeholder fails at compile time.
8. `{item.id}` on non-scoped step fails unless explicit worklist context is supported.
9. Runtime missing current item fails clearly.
10. Runtime missing payload path fails clearly.
11. Prompt rendering materializes worklist only when step is reached.

## 6.10 Inspection/static graph tests

1. Static graph does not show default `blocked`.
2. Static graph does not show default `failed`.
3. Static graph distinguishes authored `failed` from runtime failure mechanics.
4. Inspection shows `question` provider-visible in interactive mode.
5. Inspection hides `question` provider-visible in full-auto mode.
6. Inspection can show runtime control routes separately from authored domain routes.

---

# 7. Acceptance criteria

The change is complete when:

1. No provider request includes default `blocked`.
2. No provider request includes default `failed`.
3. Default `question` appears in provider requests only when interaction policy allows provider questions.
4. Runtime/provider failures still use retry and failure contexts.
5. `blocked` and `failed` route names have no hidden reason requirement.
6. Child workflow mapped `blocked`/`failed` outcomes require explicit routes.
7. Worklist sources are not loaded at compile time or fresh-run start.
8. Resume does not initialize unused worklists.
9. Worklist selection materializes at first use.
10. Source missing behavior is source-policy-driven: scaffold/ensure or fail.
11. Only materialized selections are checkpointed.
12. Work-item session continuity resolves lazily from active/current item.
13. Common scoped progression can be expressed through narrow worklist effects.
14. Repairable semantic validation can be expressed through `validation_step`.
15. Artifact ownership ambiguity fails with an actionable diagnostic.
16. Prompt validation supports late-bound item/worklist context without losing static typo protection.
17. Static graph and inspection reflect authored routes separately from policy-gated runtime controls.
18. All tests listed above pass.

---

# 8. Final target architecture

After these changes, workflow authors should be able to declare static intent like:

```text
this step is scoped to this worklist
this session follows the current work item
this prompt uses the active item
this route completes and advances the current item
this validation failure repairs through this producer
```

without manually pre-creating worklist contents, mirroring active item state in workflow state, or exposing generic provider failure routes.

The resulting framework rule is:

```text
static names and topology are validated early;
runtime-created data is validated when reached;
provider-visible routes are domain-specific and policy-aware;
runtime failures remain runtime-owned.
```
