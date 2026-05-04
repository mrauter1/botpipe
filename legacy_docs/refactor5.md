# Framework authoring-flexibility change spec

## Goal

Improve workflow-authoring ergonomics by removing framework rigidity that forces authors to pre-create runtime data, expose generic failure routes to providers, or duplicate common runtime mechanics in workflow code.

The framework should preserve early validation of static contracts, but defer validation of runtime-created data until the run reaches the code path that needs it.

Current examples motivating these changes:

* Reserved routes are injected by default: provider-facing steps currently receive `question`, `blocked`, and `failed`, while Python and child workflow steps receive `failed`. 
* Worklist selections are initialized eagerly at run start and restored by first initializing all worklists, which requires backing data before the workflow has created it. 
* Context selection currently raises when a worklist selection is missing instead of materializing it lazily. 
* Work-item session continuity currently fails if no active work item exists at key-derivation time. 
* Artifact inventory currently distinguishes workflow-level artifacts and step-produced artifacts, but authoring can accidentally combine both roles. 
* Prompt placeholder validation performs strong static checks, including item-state and artifact-reference checks, which is useful for typos but too eager for runtime-created context. 

## Non-goals

Do not implement any specific workflow package as part of this change.

Do not add a broad flow DSL.

Do not unify all step kinds into one abstraction.

Do not weaken runtime failure handling, retry feedback, checkpointing, or artifact validation.

Do not keep compatibility shims for old default provider routes. Existing tests should be updated to the new behavior rather than preserving the old blanket `blocked`/`failed` defaults.

---

# 1. Runtime interaction policy and provider route exposure

## Problem

Provider-visible route sets currently include generic routes that are not necessarily domain routes. This encourages providers to choose vague `blocked` or `failed` outcomes instead of using domain-specific repair routes or letting runtime failures remain runtime-owned.

## Required behavior

Default provider-visible control routes must be:

```text
question: exposed only when runtime is interactive / not full-auto
blocked: never injected by default
failed: never injected by default
```

Runtime failures must remain runtime-owned:

```text
provider transport failure        → runtime retry/failure context
malformed provider output         → runtime retry/failure context
illegal provider route            → runtime retry/failure context
missing required output artifact  → runtime retry/failure context
invalid output artifact           → runtime retry/failure context
```

The provider should not be asked to choose `failed` for runtime failures.

## New policy object

Add a small runtime policy object, likely in `autoloop/core/providers/models.py` or a nearby runtime-policy module:

```python
@dataclass(frozen=True, slots=True)
class RuntimeInteractionPolicy:
    allow_provider_questions: bool = True
```

The runner must set:

```python
allow_provider_questions = not full_auto
```

For direct engine usage, default to interactive mode unless explicitly configured:

```python
RuntimeInteractionPolicy(allow_provider_questions=True)
```

## Engine constructor

Add an optional argument:

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

## Reserved route injection

Replace blanket reserved-route injection.

Current behavior in discovery injects:

```text
question → AWAIT_INPUT
blocked  → AWAIT_INPUT
failed   → FAIL
```

for provider steps, and injects `failed → FAIL` for Python/child workflow steps. 

New behavior:

* Do not inject `blocked`.
* Do not inject `failed`.
* Inject or compile an internal `question → AWAIT_INPUT` route only for provider-facing steps that allow automatic question support.
* `question` must be provider-visible only when `interaction_policy.allow_provider_questions` is true.
* If an author explicitly declares `blocked` or `failed`, treat them as ordinary authored routes, not reserved routes with special validation.

## Suggested implementation

Introduce a typed control-route declaration:

```python
@dataclass(frozen=True, slots=True)
class ControlRoutes:
    question: Literal["auto", "always", "never"] = "auto"
```

Default for provider-facing steps:

```python
ControlRoutes(question="auto")
```

Default for Python and child workflow steps:

```python
ControlRoutes(question="never")
```

Mapping:

```text
question="auto"   → compile internal route; provider-visible only when allow_provider_questions
question="always" → compile internal route; provider-visible always
question="never"  → no default question route
```

Do not include `blocked` or `failed` in this control route object.

## Provider request construction

Modify `_provider_available_routes_for_step()` and `_routes_for_step()` so route visibility is policy-aware.

Rules:

* Explicit authored routes with `provider_visible=True` are included.
* Internal `question` route is included only when:

  * the step allows question control, and
  * `interaction_policy.allow_provider_questions` is true.
* Internal `question` route is excluded in full-auto mode.

## Outcome/event validation

Current validation has hard-coded payload requirements for `blocked` and `failed`. Remove those hard-coded reserved semantics.

Keep special validation only for `question`:

```text
if route == "question":
    question text must be non-empty
```

For any explicit route named `blocked` or `failed`, do not impose a special reason requirement unless the workflow declares such a requirement through an expected output schema or route-level contract.

## Tests

Add/update tests:

1. Provider-facing step with no explicit control routes receives `question` only in interactive mode.
2. Same step receives no `question` route in full-auto mode.
3. Provider-facing step does not receive default `blocked`.
4. Provider-facing step does not receive default `failed`.
5. Python step does not receive default `failed`.
6. Child workflow step does not receive default `failed`.
7. Explicit authored `blocked` route is preserved.
8. Explicit authored `failed` route is preserved.
9. Explicit authored `failed` route does not require a non-empty reason unless schema requires it.
10. Provider returning `question` in full-auto mode is illegal and receives retry feedback.
11. Runtime provider failures still use runtime retry/failure context, not provider `failed`.

---

# 2. Lazy worklist materialization

## Problem

Worklists are currently materialized too early. The engine initializes all worklist selections at fresh-run start and restore starts by initializing all worklists before applying snapshots. 

This makes workflows awkward when a previous step creates the worklist source artifact.

## Required behavior

Compile time should validate only static worklist contracts:

```text
worklist name
selector declaration
source object interface
item-state model
scoped step references declared worklist
```

Runtime should validate worklist contents only when needed:

```text
first ctx.selection(...)
first ctx.worklist(...).selection/current
first scoped step using that worklist
artifact template requiring {item...}
session continuity requiring current work item
```

## Engine start behavior

Fresh run:

* Do not call `initialize_worklist_selections(context)` for every worklist.
* Start with:

```python
selections = {}
```

Resume:

* Restore only checkpointed worklist selections.
* Do not initialize missing selections during restore.
* Missing selections remain lazy.

## StateRuntime changes

Replace eager APIs with lazy APIs.

Current shape:

```python
initialize_worklist_selections(context) -> dict[str, Selection]
restore_worklist_selections(context, snapshots) -> dict[str, Selection]
```

New shape:

```python
restore_worklist_selections(context, snapshots) -> dict[str, Selection]
ensure_worklist_selection(context, worklist_name) -> Selection
```

`restore_worklist_selections` should restore from snapshots without loading every source.

`ensure_worklist_selection` should:

1. Return existing selection if present.
2. Resolve the declared worklist.
3. Load items from source.
4. Validate loaded items.
5. Apply selector.
6. Store selection into context via `_set_selection`.
7. Emit a runtime event such as `worklist_selection_resolved`.
8. Return the selection.

## Context changes

Modify:

```python
Context.selection(worklist)
Context.current(worklist)
Context.item
Context.current_worklist
WorklistRuntimeView.selection
```

to call lazy selection materialization.

Current `Context.selection()` raises when selection is absent.  It should instead call an internal lazy selection resolver.

Suggested method on `Context`:

```python
def ensure_selection(self, worklist: Worklist[Any] | str) -> Selection[Any]:
    ...
```

`selection()` should become:

```python
def selection(self, worklist):
    return self.ensure_selection(worklist)
```

`item` should ensure selection for `self._active_worklist` before returning current item.

## Scoped step entry

Before resolving artifacts or item state for a scoped step, ensure the scoped selection exists.

Reason: artifact templates may use `{item.dir_key}` and required-artifact resolution happens before provider execution.

Suggested location:

* In `StepDispatcher.execute()` after:

```python
context._set_active_worklist(step.scope_name)
```

add:

```python
if step.scope_name is not None:
    context.ensure_selection(step.scope_name)
```

Alternatively, make `context.item` lazy enough that artifact resolution triggers this automatically. The explicit dispatcher call is clearer and easier to test.

## Checkpointing

Only checkpoint selections that have been materialized.

`_snapshot_worklist_selections(...)` should continue to snapshot existing selections, but must not force lazy selections to load.

## Worklist validation failures

When lazy materialization fails:

* Raise `WorkflowExecutionError` with:

  * worklist name
  * source type
  * whether source was missing, malformed, empty, or validation-invalid
  * selector details if selection failed
* Do not hide this as declaration validation.
* Do not load all other worklists while reporting one failure.

## Tests

Add tests:

1. Workflow with declared artifact-backed worklist compiles when backing artifact does not exist.
2. Fresh run does not load worklist source before first scoped step.
3. Non-scoped path can finish without materializing unused worklist.
4. First scoped step materializes selection.
5. Missing worklist source fails at first scoped use with clear error.
6. Invalid worklist source fails at first scoped use with clear error.
7. `ctx.worklist("x").refresh()` reloads the source after it has been created.
8. Checkpoint includes only materialized selections.
9. Resume restores existing materialized selections without loading unrelated worklists.
10. Resume can lazily materialize a previously unused worklist later.

---

# 3. Lazy work-item session continuity

## Problem

Work-item session continuity currently depends on resolving the current work item immediately. If no active item is present, it raises. 

## Required behavior

A workflow author should be able to declare:

```python
worker = Session(continuity=Continuity.work_item("phases"))
```

and have the runtime bind the actual session key when a current item exists.

## Session key derivation

When deriving a work-item session key:

1. Ensure the referenced worklist selection exists.
2. Resolve the current item.
3. If no current item exists, fail with a clear runtime error.
4. Use `dir_key` if present, otherwise `id`.
5. Use a stable key:

```text
<worklist_name>:<item_dir_key_or_id>
```

## Scoped steps

For a scoped step whose session continuity references the same worklist:

* The dispatcher should materialize the worklist selection before selecting the session.
* The current item should be available by the time `_resolve_session()` runs.

## Non-scoped steps

For non-scoped steps using work-item continuity:

* Allow it only if `ctx.current(worklist_name)` resolves a current item.
* Otherwise fail at runtime with a clear message.

Do not add a compile-time restriction that forbids all non-scoped work-item continuity. Some workflows intentionally inspect or operate on a current selection outside a scoped step.

## Tests

Add tests:

1. Work-item continuity does not load source at workflow declaration/compile time.
2. Scoped step with work-item session materializes selection and opens item-scoped session.
3. Different items get different session keys.
4. Same item resumes same session key.
5. Non-scoped step with work-item continuity fails clearly when no current item exists.
6. Work-item continuity uses `dir_key` before `id`.

---

# 4. Narrow typed worklist effects

## Problem

Common workflow mechanics require imperative hook code:

```python
ctx.current_worklist.set_current_status("completed")
ctx.current_worklist.advance()
return Event("next")
```

The runtime already has worklist runtime operations such as status set/reset and advance, but authors must manually wire them in hooks and Python steps. 

## Required behavior

Add a narrow typed effect system for common, deterministic worklist operations.

Do not add a broad DSL.

## New effect types

Add a new module, for example:

```text
autoloop/core/effects.py
```

Define:

```python
@dataclass(frozen=True, slots=True)
class WorklistEffect:
    worklist: str | None = None  # None means current active worklist
    refresh: bool = False
    set_current_status: str | None = None
    reset_current_status: bool = False
    advance: bool = False
    exhausted: str | Event | RequestInput | Goto | Fail | None = None
```

```python
@dataclass(frozen=True, slots=True)
class Effects:
    worklists: tuple[WorklistEffect, ...] = ()
    event: str | Event | RequestInput | Goto | Fail | None = None
```

Convenience constructors:

```python
Effects.then("next")
Effects.advance(worklist=None, exhausted="after_items")
Effects.complete_and_advance(worklist=None, exhausted="after_items")
Effects.refresh(worklist)
```

## Hook/Python return normalization

Update `HookRunner.normalize_result(...)` and Python step result normalization to accept `Effects`.

Effect execution order:

1. Apply refresh effects.
2. Apply status effects.
3. Apply advance effects.
4. Determine final event/control:

   * explicit `Effects.event` wins
   * if an advance exhausts and has `exhausted`, use that
   * otherwise no route override

Rules:

* If `worklist=None`, require an active worklist.
* If both `set_current_status` and `reset_current_status` are set, raise.
* If `advance=True` and current selection is missing, lazy materialize it first.
* Emit existing worklist runtime events for refresh/status/advance/exhaustion.
* Effects must be checkpoint-safe because they mutate normal runtime state and source-backed worklists through existing worklist APIs.

## Route helper API

Add helpers to `Route`, if consistent with existing style:

```python
Route.advance(target, worklist=None, status=None, exhausted=None)
Route.refresh(target, worklist)
Route.complete_current(target, worklist=None)
```

These helpers should lower to `Route(..., on_taken=Effects(...))` or equivalent.

## Tests

Add tests:

1. Hook can return `Effects.complete_and_advance(exhausted="done")`.
2. Python step can return `Effects.advance(exhausted="done")`.
3. Status effect persists through mutable worklist source.
4. Refresh effect reloads source.
5. Exhausted route is returned only when selection is exhausted.
6. Effect with no active worklist fails clearly.
7. Effects participate in checkpoint state.
8. Route helper lowers to same behavior as explicit effect.

---

# 5. Standard repairable validation step contract

## Problem

Higher-level validation currently requires repeated custom Python plumbing:

```python
try:
    validate()
except Error:
    write feedback
    return Event("repair")
```

Artifact schema validation exists, but semantic validation is often workflow-specific and repairable.

## Required behavior

Add a reusable validation-step helper that standardizes:

* validation result shape
* feedback writing
* success route
* repair route
* failure messaging
* runtime events

## Public API

Add to the public authoring surface:

```python
validation_step
ValidationResult
```

Suggested model:

```python
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

Helper:

```python
@validation_step(
    name="validate_manifest",
    feedback=MANIFEST_FEEDBACK,
    success="done",
    repair="repair",
    failed=FAIL,
    requires=[MANIFEST],
)
def validate_manifest(ctx) -> ValidationResult:
    ...
```

Lowering:

* Generates a Python step.
* Routes:

  * `success` route
  * `repair` route
  * optional `failed` route
* If result is valid:

  * return `Event(success)`
* If invalid:

  * write feedback artifact
  * return `Event(repair, reason=result.message, handoff=...)`

## Feedback artifact formatting

Default:

```markdown
# <title>

<message>

## Details
- ...
```

Allow custom renderer later, but not necessary for this change.

## Runtime events

Emit:

```text
validation_step_passed
validation_step_failed_repairable
```

with:

```text
step_name
feedback_artifact path
message
details
```

## Tests

Add tests:

1. Valid result routes to success.
2. Invalid result writes feedback and routes to repair.
3. Invalid result handoff points to feedback artifact.
4. Exception in validation function routes to failed or raises if no failed route.
5. Feedback artifact is declared as a write.
6. Helper works with artifact `requires`.
7. Helper works in direct engine tests.

---

# 6. Artifact ownership diagnostics

## Problem

Workflow-level artifacts and step-produced artifacts are distinct roles, but the same artifact can be accidentally declared in both places. Artifact inventory already tracks `workflow_level` and `producer_steps`. 

## Required behavior

Make artifact role mistakes fail clearly at compile time.

## Rule

If an artifact is both workflow-level and produced by one or more steps, raise `WorkflowValidationError`, unless it is explicitly marked as managed/shared by a new intentional mechanism.

Initial implementation may omit the managed escape hatch if no current tests require it.

Error message should include:

```text
artifact name
qualified name
workflow-level declaration
producer step names
recommended fix
```

Recommended fix:

```text
For external/input artifacts: keep as workflow class attribute and remove from step writes.
For produced artifacts: keep as step writes only and do not assign as workflow class attribute.
For managed artifacts: use the explicit managed-artifact role once implemented.
```

## Optional explicit roles

Add later if needed:

```python
Artifact.input(...)
Artifact.produced(...)
Artifact.managed(...)
```

or:

```python
Artifact(..., role="input" | "produced" | "managed")
```

Do not block the main diagnostic on this optional role work.

## Tests

Add tests:

1. Workflow-level request artifact compiles.
2. Step-produced artifact compiles when not workflow-level.
3. Same artifact declared workflow-level and step-produced fails.
4. Same artifact name with separate identities gives clear duplicate/ambiguous diagnostic.
5. Error message includes producer step names.

---

# 7. Late-bound prompt context for runtime-created facts

## Problem

Static prompt placeholder validation is useful, but it currently rejects some placeholders that are only meaningful at runtime, especially active item and worklist context. The current validation includes strict item-state and artifact checks. 

## Required behavior

Keep early typo checks for static names, but allow late-bound runtime namespaces.

## Early validation should keep checking

```text
placeholder syntax
known root namespaces
declared params fields
declared state fields
declared step names
declared artifact names when unambiguous
unknown obvious names
```

## Late-bound namespaces

Allow these when the step is scoped or can otherwise materialize the referenced worklist:

```text
item.id
item.title
item.status
item.dir_key
item.payload
item.payload.<any path>
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

Static validation should verify the worklist name exists, but should not require the backing items to exist.

## Runtime rendering

At runtime, rendering must:

* Lazy materialize referenced worklist selection.
* Fail with a clear `WorkflowExecutionError` if:

  * current item is required but no current item exists
  * payload path does not exist
  * worklist source cannot be loaded
* Include placeholder text in error messages.

## Artifact template placeholders

Artifact template resolution already supports `item` and `worklist` roots.  Ensure lazy selection is compatible with that path:

* `{item.dir_key}` should trigger selection materialization if active worklist exists.
* `{worklist.phases.current.dir_key}` or equivalent should be supported if artifact template placeholder syntax is extended.
* Do not silently substitute empty strings for runtime-created facts that are required for artifact paths.

## Tests

Add tests:

1. Prompt with `{item.id}` compiles for a scoped step.
2. Prompt with `{item.payload.foo}` compiles for a scoped step.
3. Prompt with `{item.id}` fails for a non-scoped step unless explicit worklist context is declared.
4. Prompt with `{worklist.phases.current.id}` compiles when `phases` worklist exists.
5. Prompt with unknown worklist fails at compile time.
6. Runtime missing current item fails clearly.
7. Runtime payload path missing fails clearly.
8. Lazy prompt rendering materializes the worklist only when step is reached.

---

# 8. Remove hard-coded special treatment of route names `blocked` and `failed`

## Problem

If `blocked` and `failed` are no longer default provider routes, their names should not carry hidden reserved semantics.

Current validation treats `blocked` and `failed` specially by requiring a non-empty reason. 

## Required behavior

Only `question` remains a reserved runtime route with built-in payload requirements.

`blocked` and `failed` are ordinary application route names if explicitly authored.

Remove all hard-coded checks of:

```python
if outcome.tag in {"blocked", "failed"} ...
if event.tag in {"blocked", "failed"} ...
```

unless they are guarding a specifically declared runtime-control object, not a provider/application route.

## Tests

Add tests:

1. Explicit route named `blocked` can be returned without reason if no schema requires reason.
2. Explicit route named `failed` can be returned without reason if no schema requires reason.
3. `question` still requires non-empty question.
4. Runtime `Fail(...)` control still requires/records reason according to its own type semantics, independent of provider route names.

---

# 9. Inspection and static graph updates

## Problem

Inspection and static graph tests likely assume injected control routes.

## Required behavior

Update all inspection/static graph outputs to distinguish:

```text
authored routes
internal runtime control routes
provider-visible routes under current interaction policy
```

## Add inspection fields

For each step, expose:

```json
{
  "authored_routes": [...],
  "runtime_control_routes": [...],
  "provider_visible_routes_interactive": [...],
  "provider_visible_routes_full_auto": [...]
}
```

If this is too much, at minimum expose provider-visible routes for a passed policy.

## Static graph

Static graph should include internal `question` route only as a runtime control edge, not as a normal authored domain edge.

Do not include default `blocked` or default `failed`.

## Tests

Update tests that currently snapshot route lists.

Add tests:

1. Static graph does not show default blocked/failed.
2. Static graph distinguishes authored failed route from injected runtime failure behavior.
3. Inspection shows question as provider-visible only in interactive policy.

---

# 10. Runner/config plumbing

## Required behavior

Carry full-auto or interaction mode into the engine.

Where the runtime currently parses or stores full-auto behavior, convert that into:

```python
RuntimeInteractionPolicy(allow_provider_questions=not full_auto)
```

Pass the policy to the engine.

## CLI/config semantics

Keep the current user-facing full-auto setting name if it already exists.

Behavior:

```text
full_auto=false → provider may ask question when step allows auto question route
full_auto=true  → provider is not shown question route by default
```

If a workflow explicitly declares a domain route named `question`, it should still be subject to route visibility rules. Prefer avoiding the name `question` for ordinary domain routes.

## Tests

1. Runner with full-auto false exposes question to provider.
2. Runner with full-auto true does not expose question.
3. Direct Engine default is interactive unless policy provided.
4. Direct Engine with explicit `allow_provider_questions=False` hides question.

---

# 11. Documentation updates

Update framework authoring documentation with these principles:

```text
Static validation:
  workflow topology
  names
  declared routes
  declared worklists
  artifact reference ambiguity
  callback existence
  schema shape

Runtime validation:
  worklist contents
  generated boards
  runtime-created prompt context
  item-scoped artifact paths
  semantic validation steps
```

Document route policy:

```text
Only question is a default provider control route, and only when not full-auto.
blocked and failed are never injected by default.
Use explicit application routes for domain-level blocked/failure states.
Runtime failures are handled by runtime retry/failure mechanisms.
```

Document lazy worklists:

```text
Declared worklists do not need to exist at workflow start.
A worklist source is loaded when first used.
Use refresh/advance/status helpers for scoped progression.
```

Document artifact ownership:

```text
Workflow-level artifacts are inputs or managed external artifacts.
Step writes are produced artifacts.
Do not declare the same artifact as both unless using an explicit managed role.
```

---

# Implementation order

Implement in this order to minimize breakage:

1. Add interaction policy object and engine plumbing.
2. Stop injecting default `blocked` and `failed`.
3. Make `question` provider-visible only when policy allows.
4. Remove hard-coded `blocked`/`failed` payload validation.
5. Make worklist selections lazy in context and engine start/resume.
6. Make work-item session continuity work with lazy selections.
7. Add narrow typed worklist effects.
8. Add validation-step helper.
9. Add artifact ownership diagnostic.
10. Relax prompt validation for late-bound item/worklist context.
11. Update inspection/static graph outputs.
12. Update docs and tests.

---

# Required regression test suite

Add or update tests in the existing contract, runtime, and unit test areas.

Minimum coverage:

## Provider route policy

1. Interactive provider step receives default `question`.
2. Full-auto provider step does not receive default `question`.
3. Provider step never receives default `blocked`.
4. Provider step never receives default `failed`.
5. Explicit `blocked` route remains available.
6. Explicit `failed` route remains available.
7. Explicit `failed` route has no hidden reason requirement.
8. Runtime provider failures still retry/fail via runtime context.

## Lazy worklists

9. Declared artifact-backed worklist compiles with missing source.
10. Fresh run does not load unused worklist.
11. First scoped step materializes worklist.
12. Missing source fails at first use, not compile/start.
13. Invalid source fails at first use with clear error.
14. Refresh reloads source.
15. Resume restores only checkpointed selections.
16. Resume lazily materializes previously unused worklist.

## Work-item sessions

17. Work-item continuity binds at scoped step execution.
18. Different items produce different session keys.
19. Same item resumes same session key.
20. Missing current item gives clear runtime error.

## Effects

21. Hook return effect sets current status.
22. Hook return effect advances current worklist.
23. Exhausted worklist effect routes to exhausted route.
24. Effect refresh reloads source.
25. Effect without active worklist fails clearly.

## Validation helper

26. Valid result routes to success.
27. Invalid result writes feedback and routes to repair.
28. Exception in validator routes/fails according to declared failed route.
29. Feedback artifact is written deterministically.

## Artifact ownership

30. Workflow-level input artifact compiles.
31. Produced step artifact compiles.
32. Artifact declared both workflow-level and produced fails with actionable diagnostic.

## Prompt context

33. Scoped prompt can reference `item.id`.
34. Scoped prompt can reference `item.payload.foo`.
35. Prompt can reference `worklist.<name>.current.id`.
36. Unknown worklist placeholder fails at compile time.
37. Missing runtime current item fails at runtime with placeholder context.

## Inspection/static graph

38. Static graph does not include default blocked/failed.
39. Static graph marks question as runtime control.
40. Inspection reflects provider-visible route differences between interactive and full-auto policies.

---

# Acceptance criteria

The change is complete when:

1. No provider request includes default `blocked` or default `failed`.
2. Default `question` appears only when interaction policy allows provider questions.
3. Runtime failure categories still use runtime retry/failure contexts.
4. Worklist source artifacts are not required at compile time or run start.
5. Worklist selection is materialized at first use and checkpointed only after materialization.
6. Work-item session continuity works without manual session opening in scoped item steps.
7. Common worklist progression can be expressed with typed effects rather than imperative glue.
8. Repairable validation loops can be expressed with the validation-step helper.
9. Artifact ownership mistakes fail with clear diagnostics.
10. Prompt validation allows runtime-created item/worklist context without losing typo protection.
11. Existing tests are updated to the new route contract, and all new tests above pass.

