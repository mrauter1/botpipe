Below is the **full standalone remaining-delta implementation spec** against the latest full pasted codebase. It excludes features already implemented in that paste, and it assumes **no legacy support, no migration aliases, and no compatibility shims**. The latest codebase still contains the hook phase restrictions, multi-arity hook execution, `AfterStepResult`, internal `on_route_hook`, route effects, old internal `outputs` vocabulary, handler aliasing, and wrapper-style engine collaborators, so those are included here as remaining work.

## Hook control semantics

* **Remove artificial hook phase restrictions**

  * Any author hook may return any valid hook result.
  * Remove `allow_direct_control` and `allow_redirect` as semantic gates.
  * Do not reject hook results because no candidate route exists yet.
  * Runtime validation should only check whether the returned value is valid:

    * route-tag string must be declared on the current step;
    * `Event.tag` must be declared on the current step;
    * `RequestInput.question` must be non-empty;
    * `Goto.target` must resolve to a declared step;
    * `Fail.reason` must be non-empty.

* **Allow `before` hooks to control execution**

  * `before`, `before_producer`, and `before_verifier` are full control hooks.
  * They may return:

    * `None`;
    * route-tag string;
    * `Event(...)`;
    * `RequestInput(...)`;
    * `Goto(...)`;
    * `Fail(...)`.
  * If a `before` hook returns `None`, execution continues normally.
  * If a `before` hook returns a route tag or `Event`, the step body is skipped and that declared route is finalized.
  * If a `before` hook returns `RequestInput`, `Goto`, or `Fail`, the step body is skipped and that runtime control is executed.
  * If a `before` hook returns an invalid route/control, the run fails with current state/session preserved.

* **Allow producer/verifier lifecycle hooks to control execution**

  * `before_producer` may short-circuit the whole `produce_verify_step`.
  * `after_producer` may:

    * continue to verifier with `None`;
    * return a route tag / `Event` and skip verifier;
    * return `RequestInput`, `Goto`, or `Fail`.
  * `before_verifier` may:

    * continue to verifier with `None`;
    * return a route tag / `Event` and skip verifier;
    * return `RequestInput`, `Goto`, or `Fail`.
  * `after_verifier` follows the same final hook return model.

* **Make hook short-circuiting traceable**

  * If a hook exits before provider/python execution, trace:

    * `provider_attempted: false`;
    * `candidate_route: null`;
    * `source_phase`;
    * `source_hook`;
    * selected route or runtime control;
    * target step / terminal / pending input id, if applicable.
  * If a hook exits after producer but before verifier, trace:

    * `producer_attempted: true`;
    * `verifier_attempted: false`;
    * selected route/control;
    * source hook/phase.

* **Keep provider retry attribution out of hook-originated control**

  * If no provider turn ran, provider retry must not run.
  * If a hook changes a provider-selected route, only obligations created by the provider-selected route are provider-attributable.
  * Obligations introduced only by hook route/control selection are hook/workflow-attributable.

---

## Hook calling convention

* **Use one public hook signature: `hook(ctx)`**

  * All public hooks must take exactly one argument:

```python
def before(ctx):
    ...

def after(ctx):
    ...

def on_taken(ctx):
    ...
```

* Remove positional overloads based on arity.

* Do not support final public hook forms such as:

  * `(ctx, outcome)`;
  * `(ctx, outcome, route)`;
  * `(state, outcome, artifacts, ctx)`;
  * `(state, ctx)`.

* Everything the hook needs must be available on `ctx`:

  * `ctx.state`;
  * `ctx.step_state`;
  * `ctx.item_state`;
  * `ctx.step_item_state`;
  * `ctx.artifacts`;
  * `ctx.outcome`;
  * `ctx.event`;
  * `ctx.route`;
  * `ctx.input_response`;
  * `ctx.meta`;
  * `ctx.history`.

* **Remove hook return state replacement**

  * Hooks mutate state through `ctx`.
  * Hooks must not return a `BaseModel` to replace state.
  * Final hook return set:

```python
None
str          # route tag
Event
RequestInput
Goto
Fail
```

* **Remove `AfterStepResult`**

  * Delete `AfterStepResult` from the final hook path.
  * Delete `_event_from_after_step_result(...)` and related normalization branches.
  * Replace all use cases with:

    * direct `ctx` mutation;
    * route-tag string;
    * `Event(...)`;
    * `RequestInput(...)`;
    * `Goto(...)`;
    * `Fail(...)`.

* **Unify hook result normalization**

  * Introduce one internal normalized hook result type used by:

    * `before`;
    * `after`;
    * `before_producer`;
    * `after_producer`;
    * `before_verifier`;
    * `after_verifier`;
    * route `on_taken`;
    * `python_step` handler normalization.
  * Suggested shape:

```python
@dataclass(frozen=True)
class HookResult:
    event: Event | None = None
    control: RequestInput | Goto | Fail | None = None
```

* State replacement must not be part of this result.

---

## Public and internal route-hook cleanup

* **Remove public `on_route` completely**

  * Remove `on_route` from:

    * declaration constructors;
    * simple declaration objects;
    * step classes;
    * generated capability surfaces;
    * topology/debug payloads;
    * docs/tests.

* **Remove internal `on_route_hook`**

  * Remove `on_route_hook` from `CompiledStep`.
  * Remove `getattr(step, "on_route", None)` from compilation.
  * Remove `step.on_route_hook` execution from the engine.
  * Remove `on_route_hook` from topology hash payloads and generated artifacts.
  * Final hook model is only:

    * `before`;
    * `after`;
    * `Route.to(..., on_taken=...)`.

* **Final route finalization model**

  * For route-based control:

```text
candidate route/control, if any
after hook, if applicable
route-local on_taken chain
final route validation
effective required-write validation
built-in finalized route state update
checkpoint
transition
```

* There must be no separate step-level `on_route` phase.

---

## `python_step` result model

* **Allow `python_step` handlers to return the same control model as hooks**

  * A `python_step` handler may return:

    * `None` → default `"done"`;
    * route-tag string;
    * `Event(...)`;
    * `RequestInput(...)`;
    * `Goto(...)`;
    * `Fail(...)`.

* **Remove old `python_step` return forms**

  * Do not support:

    * `BaseModel`;
    * `(BaseModel, Event)`;
    * `(BaseModel, str)`.
  * Python steps should mutate state through `ctx`, not by returning replacement state.

---

## Scoped state availability

* **Always expose `ctx.step_item_state` for scoped steps**

  * For any scoped step, `ctx.step_item_state` must exist.
  * If the author did not declare custom step-item state, expose a built-in-only state view.
  * Built-in step-item fields:

    * `visits`;
    * `last_route`;
    * `last_reason`;
    * `rework_count`;
    * `replan_count`.
  * Runtime-owned fields are read-only.
  * Custom fields, if declared, remain mutable.

* **Define `ctx.item_state` semantics explicitly**

  * `ctx.item_state` is work-item-wide state shared across steps.
  * It should be available if either:

    * the worklist declares an item-state model; or
    * Autoloop defines a built-in item runtime state model.
  * If no built-in item model is introduced, `ctx.item_state` should require explicit `Worklist(..., item_state=...)`.
  * If a built-in item model is introduced, keep it small and runtime-owned, for example:

    * `status`;
    * `last_step`;
    * `last_route`.
  * Error only when there is no active scoped item at all.

* **Preserve read-only built-in state**

  * Built-in fields remain runtime-owned and read-only.
  * Custom declared fields remain mutable.

---

## Runtime state and failure semantics

* **Preserve current state/session on all failures**

  * On hook failure, step failure, route-finalization failure, provider failure, artifact validation failure, or runtime-control validation failure:

    * do not restore previous state automatically;
    * do not restore previous sessions automatically;
    * checkpoint the current mutated state/session;
    * include structured failure context.

* **Keep built-in finalized route state truthful**

  * `visits` increments on step entry.
  * `last_route`, `last_reason`, `rework_count`, and `replan_count` update only after successful route-based finalization.
  * `RequestInput`, `Goto`, and `Fail` do not update `last_route`.
  * Failed candidate routes do not update finalized route state.
  * Candidate route/control data belongs in trace/history.

---

## Exception and failure model

* **Finish structured exception cleanup**

  * Remove dynamic exception metadata mutation such as attaching:

    * `checkpoint_state`;
    * `failure_context`;
    * `retry_kind`;
    * `pending_handoffs`.
  * Replace with structured exception types.

* **Remove `getattr`-based exception metadata readers**

  * Remove helpers that recover failure state from arbitrary exception attributes.
  * Failure data should come from typed exception fields.

* **Final failure context shape**

  * Structured failure context should include:

    * `kind`;
    * `step_name`;
    * `candidate_route`;
    * `final_route`;
    * `runtime_control`;
    * `provider_attributable`;
    * `source_hook`;
    * `source_phase`;
    * `target_step`;
    * `pending_input_id`;
    * `details`.

---

## Route effects and worklist side effects

* **Remove route effects from the public authoring model**

  * Route effects currently represent a second route side-effect language alongside hooks. They include `Refresh`, `ResetCompletion`, `SetStatus`, `Advance`, and `Handoff`. 
  * Final public route model should use only:

    * route target;
    * provider visibility;
    * required writes;
    * handoff metadata;
    * `on_taken`.

* **Add worklist helper APIs before deleting route effects**

  * The replacement for route effects is:

    * explicit `on_taken` hooks;
    * first-class worklist helper methods on `ctx`.
  * Worklist helpers mutate selection/status only.
  * Hook returns and route targets control execution.

---

## Worklist helper API

* **Add a first-class `ctx.worklists` surface**

  * Expose runtime worklist operations through:

```python
ctx.worklists.<name>
ctx.worklist(name)
ctx.current_worklist
```

* This is the public replacement for route effects.

* **Add `ctx.worklist(name)`**

  * Method:

```python
ctx.worklist(name: str | Worklist) -> WorklistRuntimeView
```

* Resolves a worklist by object or name.

* Raises clearly if unknown.

* Returns a runtime view bound to:

  * current context;
  * compiled worklist;
  * current selection.

* **Add `ctx.worklists` namespace**

  * Attribute access:

```python
ctx.worklists.phases
```

* Equivalent to:

```python
ctx.worklist("phases")
```

* Unknown worklist attributes raise `AttributeError` with a clear message.

* **Add `ctx.current_worklist`**

  * Returns the `WorklistRuntimeView` for the current scoped step’s active worklist.
  * Raises clearly if the current step is not scoped.

* **Add `WorklistRuntimeView`**

  * Suggested public shape:

```python
class WorklistRuntimeView(Generic[T]):
    name: str

    @property
    def selection(self) -> Selection[T]: ...

    @property
    def current(self) -> WorkItem[T] | None: ...

    @property
    def current_id(self) -> str | None: ...

    @property
    def current_index(self) -> int: ...

    @property
    def item_ids(self) -> tuple[str, ...]: ...

    @property
    def is_exhausted(self) -> bool: ...

    def refresh(self) -> Selection[T]: ...

    def set_current_status(self, status: str | None) -> Selection[T]: ...

    def reset_current_status(self) -> Selection[T]: ...

    def advance(self) -> bool: ...

    def advance_or(
        self,
        exhausted: str | Event | RequestInput | Goto | Fail | None = None,
    ) -> None | str | Event | RequestInput | Goto | Fail: ...

    def validate(self) -> None: ...

    def validation_error(self) -> str | None: ...
```

* **`selection`**

  * Returns the current runtime selection.
  * Read-only from author code.
  * Selection mutation happens through helper methods.

* **`current`**

  * Returns the active `WorkItem` or `None`.

* **`current_id`**

  * Returns the active item id or `None`.

* **`current_index`**

  * Returns the current selection index.

* **`item_ids`**

  * Returns selected item ids.

* **`is_exhausted`**

  * Returns `True` when there is no active current item.

* **`refresh()`**

  * Replaces public `Refresh(worklist)`.
  * Reloads the worklist selection from its source.
  * Updates context selection.
  * Returns refreshed selection.
  * Raises if selected item ids no longer exist.

* **`set_current_status(status)`**

  * Replaces public `SetStatus(worklist, status)`.
  * Updates the current item status.
  * Persists to the worklist source if the source is mutable.
  * Updates context selection/cache.
  * Returns updated selection.

* **`reset_current_status()`**

  * Replaces public `ResetCompletion(worklist)`.
  * Equivalent to:

```python
ctx.current_worklist.set_current_status(None)
```

* **`advance()`**

  * Replaces only the movement part of `Advance(worklist)`.
  * Advances the selection to the next item.
  * Updates context selection.
  * Returns:

```python
True   # another current item exists
False  # selection is exhausted
```

* Does not route, finish, await input, or fail.

* Authors decide what to return after exhaustion.

* **`advance_or(exhausted=...)`**

  * Convenience helper.
  * Semantics:

    * calls `advance()`;
    * if another item exists, returns `None`;
    * if exhausted, returns the explicitly provided `exhausted` value.
  * It must not infer `SELF`, `FINISH`, `AWAIT_INPUT`, or `FAIL`.
  * Example:

```python
def complete_phase(ctx):
    ctx.current_worklist.set_current_status("completed")
    return ctx.current_worklist.advance_or(Goto("finalize"))
```

* **`validate()`**

  * Validates the current worklist source/items.
  * Raises `WorkflowExecutionError` if invalid.
  * Does not return an error string.

* **`validation_error()`**

  * Returns `str | None`.
  * Useful when authors want to inspect rather than raise.

* **Do not make worklist helpers route automatically**

  * Worklist helpers mutate selection/status only.
  * Route targets and hook returns determine control flow.
  * Correct pattern:

```python
def complete_and_advance(ctx):
    ctx.current_worklist.set_current_status("completed")
    if not ctx.current_worklist.advance():
        return Goto("finalize")
    return None

routes={
    "accepted": Route.to(SELF, on_taken=complete_and_advance),
}
```

* **Checkpoint behavior**

  * Worklist helper mutations must be reflected in worklist selection checkpoints.
  * If the underlying source is mutable, source persistence remains source-owned.
  * On later failure, do not roll back selection/status automatically.
  * Checkpoint the current mutated selection/state.

* **Trace worklist helper mutations**

  * Emit events:

    * `worklist_refreshed`;
    * `worklist_status_set`;
    * `worklist_status_reset`;
    * `worklist_advanced`;
    * `worklist_exhausted`.
  * Include:

    * worklist name;
    * previous current item id;
    * new current item id;
    * previous status;
    * new status;
    * source hook;
    * source phase;
    * hook invocation id if available.

* **Replace route-effect examples**

  * Old model:

```python
Route.to(
    "implement",
    effects=[
        SetStatus(phases, "completed"),
        Advance(phases, if_exhausted="route", route_to="finalize"),
    ],
)
```

* New model:

```python
def complete_and_advance(ctx):
    ctx.current_worklist.set_current_status("completed")
    if not ctx.current_worklist.advance():
        return Goto("finalize")
    return None

Route.to(
    SELF,
    on_taken=complete_and_advance,
)
```

* **Delete route effects after helper migration**

  * Once helper APIs and tests exist, delete:

    * `effects=` from `Route`;
    * `CompiledRoute.effects`;
    * `Refresh`;
    * `ResetCompletion`;
    * `SetStatus`;
    * `Advance`;
    * engine `_apply_route_effects(...)`;
    * engine `_execute_route_effect(...)`.

---

## Internal vocabulary and authoring model cleanup

* **Rename internal `outputs` to `writes`**

  * Remove internal `outputs` from simple declarations and lowering.
  * Use `writes` consistently.

* **Rename internal `review_outputs` to `verifier_writes`**

  * Remove `review_outputs`.
  * Use `verifier_writes` consistently.

* **Remove `produces` / `outputs` aliases from capability/debug payloads**

  * Generated capability payloads, topology artifacts, and debug views should use only:

    * `writes`;
    * `producer_writes`;
    * `verifier_writes`.

* **Remove dunder-marker declaration detection**

  * Replace:

    * `__autoloop_simple_declaration__`;
    * `__autoloop_simple_artifact_spec__`;
    * `__workflow_abstract__`;
    * `__strict_workflow__`.
  * Use typed declaration classes and explicit `isinstance(...)` discovery.

* **Remove handler alias installation**

  * Delete automatic installation of `on_<step>` staticmethod aliases for `python_step`.
  * Python steps carry their handler explicitly.
  * Discovery must not mutate the workflow class.

* **Remove legacy-style workflow class methods from the public compiler path**

  * Remove public/simple support for:

    * `on_<step>` outcome handlers;
    * `on_start`;
    * class-level outcome middleware.
  * Use explicit step hooks and explicit workflow declarations.

* **Keep step-local routes as the only public topology model**

  * Do not expose class-level `transitions` or `flow` in the public path.
  * If strict/internal topology remains, isolate it from public authoring.

---

## Engine architecture

* **Turn collaborators into real owners**

  * Move logic into collaborator classes:

    * `StepDispatcher`: step-kind execution;
    * `RouteFinalizer`: hook/control/final route logic;
    * `HookRunner`: hook invocation and result normalization;
    * `ArtifactGuard`: effective required-write validation;
    * `StateRuntime`: state stores and built-in state updates;
    * `SessionRuntime`: session resolution/persistence;
    * `CheckpointManager`: checkpoint construction/failure checkpointing;
    * `WorkflowInvoker`: child workflow invocation;
    * `OperationRecorder`: `llm` / `classify` replay.
  * `Engine` should become only the orchestration loop.
  * Current collaborator classes still mostly delegate back into private `Engine` methods, so this remains incomplete. 

* **Refactor finalization around explicit data structures**

  * Avoid passing loosely coupled tuples/flags.
  * Use explicit structures for:

    * candidate route;
    * final route;
    * direct runtime control;
    * hook redirect chain;
    * provider attribution;
    * source hook/phase.

---

## Validation/compiler cleanup

* **Keep hook validation minimal**

  * Validate only:

    * hook is callable;
    * hook accepts exactly `ctx`;
    * hook is placed on a valid hook slot.
  * Do not infer route returns.
  * Do not forbid route/control returns from `before`.

* **Make route/control validation phase-independent**

  * Runtime validation should work for:

    * pre-step route tags;
    * post-step route tags;
    * hidden route tags;
    * `Event(...)`;
    * `RequestInput(...)`;
    * `Goto(...)`;
    * `Fail(...)`.

* **Remove strict transition-table lowering from public workflow discovery**

  * Public compiler path derives topology from step-local routes only.
  * Old transition machinery must not leak into simple authoring.

---

## Trace/history updates

* **Trace pre-step hook controls**

  * Add fields:

    * `provider_attempted`;
    * `producer_attempted`;
    * `verifier_attempted`;
    * `candidate_route`;
    * `final_route`;
    * `runtime_control`;
    * `target_step`;
    * `pending_input_id`;
    * `source_phase`;
    * `source_hook`.

* **Trace route/control source clearly**

  * Distinguish:

    * provider-selected route;
    * hook-selected route;
    * hook-selected direct control;
    * python-step-selected route/control.

* **Update history derivation**

  * History must not assume every step finish has a route.
  * It must handle:

    * `runtime_control=request_input`;
    * `runtime_control=goto`;
    * `runtime_control=fail`;
    * `provider_attempted=false`.
  * Route-based metrics should ignore direct controls unless explicitly requested.

---

## Optimizer and terminal/status cleanup

* **Ensure optimizer uses final status vocabulary**

  * Distinguish:

    * terminal: `AWAIT_INPUT`;
    * provider route tag: `"question"`;
    * status: `"awaiting_input"`.
  * Update:

    * trace normalization;
    * route/status filters;
    * terminal filtering;
    * optional artifact finalization logic;
    * run history normalization.

* **Ensure optimizer handles runtime controls**

  * Optimizer trace normalization should understand:

    * no provider attempt;
    * direct `Goto`;
    * direct `RequestInput`;
    * direct `Fail`;
    * hidden route transitions.
  * Do not treat every non-success path as provider failure.

---

## Tests to add or update

* **Hook restrictions removal**

  * `before` returns route tag.
  * `before` returns `Event`.
  * `before` returns `RequestInput`.
  * `before` returns `Goto`.
  * `before` returns `Fail`.
  * `before_producer` returns route/control.
  * `before_verifier` returns route/control.
  * No provider call occurs when a `before` hook short-circuits.
  * State/session mutations made before short-circuit are checkpointed.
  * Invalid route/control from `before` fails with current state/session preserved.

* **Single-arity hooks**

  * All hook phases accept `hook(ctx)`.
  * Multi-argument hooks are rejected.
  * No hook path relies on positional arity overload.

* **Removed hook/state result forms**

  * Hook returning `BaseModel` is rejected.
  * `AfterStepResult` cannot be imported/used.
  * Tuple state/event returns from `python_step` are rejected.

* **Internal `on_route` removal**

  * `on_route` cannot be passed to public declarations.
  * `CompiledStep` has no `on_route_hook`.
  * Engine does not execute a step-level route hook.

* **Scoped built-in item state**

  * Scoped step without custom step-item state exposes built-in `ctx.step_item_state`.
  * Worklist item state follows the chosen item-state rule:

    * either built-in item runtime model is always available;
    * or `ctx.item_state` requires explicit worklist `item_state`.
  * Unscoped step accessing item state fails clearly.

* **Worklist helpers**

  * `ctx.worklist("phases").refresh()` updates selection.
  * `ctx.worklists.phases.set_current_status("completed")` updates current item and persists mutable source.
  * `ctx.worklists.phases.reset_current_status()` clears status.
  * `ctx.worklists.phases.advance()` moves to next item and returns `True`.
  * `advance()` on final item returns `False`.
  * `advance_or(Goto("finalize"))` returns `Goto("finalize")` when exhausted.
  * `ctx.current_worklist` works only for scoped steps.
  * Helper mutations are checkpointed.
  * Helper events appear in trace/history.
  * Route-effect-equivalent workflows can be rewritten with `on_taken` hooks and produce the same behavior.

* **Route effects removal**

  * `Route.to(..., effects=...)` is rejected.
  * Worklist advancement use cases are covered by `on_taken` hooks/helpers.
  * No generated topology/capability payload includes route effects.

* **Structured errors**

  * Failure context is typed.
  * No runtime path depends on `getattr(exc, "failure_context")`.
  * Failure checkpoint preserves current mutated state/session.

* **Trace/history**

  * Pre-step `RequestInput` trace has `provider_attempted=false`.
  * Pre-step `Goto` trace has `target_step`.
  * Pre-step route return validates required writes and updates built-ins only if finalized.
  * Direct controls do not update `last_route`.

---

## Documentation updates

* **Document only final hook style**

```python
def before(ctx):
    ...

def after(ctx):
    ...

Route.to(..., on_taken=...)
```

* **Document final hook returns**

```python
None
"route_tag"
Event(...)
RequestInput(...)
Goto(...)
Fail(...)
```

* **Document direct-control semantics**

  * `RequestInput`: suspend with `AWAIT_INPUT`;
  * `Goto`: jump to declared step;
  * `Fail`: terminate failed;
  * strings are route tags only;
  * hidden routes are route tags not shown to provider.

* **Document worklist helper usage**

  * Mark current item completed.
  * Advance to next item.
  * Goto finalize when exhausted.
  * Request input when exhausted.
  * Refresh artifact-backed worklist.
  * Validate worklist after deterministic mutation.

* **Do not document**

  * positional hook arities;
  * state returns;
  * `AfterStepResult`;
  * `on_route`;
  * route effects;
  * class-level `on_<step>` handlers;
  * transition tables as public authoring;
  * `outputs` / `review_outputs` vocabulary.
