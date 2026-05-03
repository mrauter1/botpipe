## Standalone remaining-delta implementation spec

* **General implementation principle**

  * Remove artificial framework restrictions unless they protect a real invariant.
  * Do not preserve legacy compatibility paths, aliases, or migration shims.
  * Prefer a smaller public authoring model with explicit typed runtime controls.
  * Preserve functionality by replacing old mechanisms with clearer APIs, not by deleting behavior.
  * Avoid surprising runtime errors in long-running processes:

    * invalid declared routes should fail clearly;
    * invalid `Goto` targets should fail clearly;
    * invalid `RequestInput` / `Fail` payloads should fail clearly;
    * but hooks should not fail merely because they run in an earlier lifecycle phase.

---

## Hook model

* **Use one public hook signature**

  * All public hooks must be:

```python
def hook(ctx):
    ...
```

* Remove all positional hook arity overloads.

* Do not support public hook forms such as:

  * `hook(ctx, outcome)`;
  * `hook(ctx, outcome, route)`;
  * `hook(state, outcome, artifacts, ctx)`;
  * `hook(state, ctx)`.

* Every value needed by hooks should be available on `ctx`:

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
  * `ctx.history`;
  * `ctx.worklists`;
  * `ctx.current_worklist`.

* **Final hook return model**

  * Hooks may return only:

    * `None`;
    * route-tag `str`;
    * `Event`;
    * `RequestInput`;
    * `Goto`;
    * `Fail`.

* **Remove state-return hooks**

  * Hooks must mutate state through `ctx`.
  * Hooks must not return a Pydantic model to replace state.
  * Remove all hook state-replacement branches.

* **Remove `AfterStepResult`**

  * Delete `AfterStepResult`.
  * Delete all normalization code for `AfterStepResult`.
  * Replace existing uses with:

    * direct `ctx` mutation;
    * route-tag string;
    * `Event`;
    * `RequestInput`;
    * `Goto`;
    * `Fail`.

* **Remove artificial hook phase restrictions**

  * Remove `allow_direct_control` and `allow_redirect` gates.
  * Any hook phase may return any valid hook result.
  * Do not reject hook results because no candidate route exists yet.
  * Runtime validation should care only about the returned value:

    * string must be a declared route tag on the current step;
    * `Event.tag` must be a declared route tag on the current step;
    * `RequestInput.question` must be non-empty;
    * `Goto.target` must resolve to a declared step;
    * `Fail.reason` must be non-empty.

* **Allow `before` hooks to control execution**

  * `before`, `before_producer`, and `before_verifier` may:

    * continue normally with `None`;
    * return a route tag;
    * return `Event`;
    * return `RequestInput`;
    * return `Goto`;
    * return `Fail`.
  * If `before` returns a route tag or `Event`, skip the step body and finalize that route.
  * If `before` returns `RequestInput`, `Goto`, or `Fail`, skip the step body and execute that runtime control.
  * If `before` returns an invalid route/control, fail with current state/session preserved.

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
  * `after_verifier` follows the same hook result model.

* **Remove public and internal `on_route`**

  * Remove `on_route` from:

    * public declaration constructors;
    * simple declaration objects;
    * step classes;
    * compiled step metadata;
    * topology hash payloads;
    * generated topology artifacts;
    * engine finalization.
  * Final route-hook model:

    * `before`;
    * `after`;
    * `Route.to(..., on_taken=...)`.

* **Route-local `on_taken` remains**

  * `on_taken` remains the route-specific hook.
  * It receives `ctx`.
  * It may return:

    * `None`;
    * route-tag string;
    * `Event`;
    * `RequestInput`;
    * `Goto`;
    * `Fail`.

* **Hook chaining**

  * If `on_taken` returns another valid route tag or `Event`, continue processing the newly selected route’s `on_taken`.
  * If `on_taken` returns `RequestInput`, `Goto`, or `Fail`, stop route-hook chaining and execute that runtime control.
  * Keep a generic redirect cap, for example:

```python
max_hook_redirects = 16
```

* If the cap is exceeded, fail with current state/session preserved and record the redirect chain.

---

## `python_step` result model

* **Use the same control result model for `python_step` handlers**

  * A `python_step` handler may return:

    * `None` → default `"done"` route;
    * route-tag string;
    * `Event`;
    * `RequestInput`;
    * `Goto`;
    * `Fail`.

* **Remove old `python_step` return forms**

  * Do not support:

    * returning `BaseModel`;
    * returning `(BaseModel, Event)`;
    * returning `(BaseModel, str)`.
  * Python steps should mutate state through `ctx`.

---

## Hook/result normalization

* **Create one normalized hook result type**

  * Use one internal structure for all hook and python-step returns.

```python
@dataclass(frozen=True)
class HookResult:
    event: Event | None = None
    control: RequestInput | Goto | Fail | None = None
```

* State replacement is not part of `HookResult`.

* Use this for:

  * `before`;
  * `after`;
  * `before_producer`;
  * `after_producer`;
  * `before_verifier`;
  * `after_verifier`;
  * `Route.on_taken`;
  * `python_step` handler normalization.

* **Validation is phase-independent**

  * Runtime validation must work before or after provider execution.
  * No validation branch should depend on “candidate route exists.”

---

## Runtime state and failure semantics

* **Preserve current state/session on failure**

  * On hook failure, step failure, route-finalization failure, provider failure, artifact validation failure, runtime-control validation failure, or redirect cap failure:

    * do not restore earlier state automatically;
    * do not restore earlier sessions automatically;
    * checkpoint current workflow state;
    * checkpoint current step state;
    * checkpoint current item state;
    * checkpoint current step-item state;
    * checkpoint current session bindings;
    * include structured failure context.

* **Keep built-in route state truthful**

  * `visits` increments when the step is entered.
  * `last_route`, `last_reason`, `rework_count`, and `replan_count` update only after successful route-based finalization.
  * Candidate routes do not update built-in route state.
  * Failed route validation does not update built-in route state.
  * `RequestInput`, `Goto`, and `Fail` do not update `last_route`.
  * Runtime-control details belong in trace/history.

---

## Scoped item state

* **Always expose `ctx.step_item_state` for scoped steps**

  * For scoped steps, `ctx.step_item_state` must exist even if the author declared no custom step-item state model.
  * If there is no custom model, expose a built-in-only state view.
  * Built-in step-item fields:

    * `visits`;
    * `last_route`;
    * `last_reason`;
    * `rework_count`;
    * `replan_count`.
  * Built-in fields are runtime-owned and read-only.
  * Custom fields, when declared, are mutable.

* **Define `ctx.item_state` explicitly**

  * `ctx.item_state` is work-item-wide state shared across steps.
  * It should exist if either:

    * the worklist declares an `item_state` model; or
    * the framework defines a built-in item runtime state model.
  * If a built-in item runtime state model is added, keep it small:

    * `status`;
    * `last_step`;
    * `last_route`.
  * If no built-in item runtime model is added, accessing `ctx.item_state` should require explicit worklist item state.
  * Accessing item state from an unscoped step should fail clearly.

---

## Trace and history

* **Trace hook short-circuiting**

  * If a hook exits before provider/python execution, trace:

    * `provider_attempted: false`;
    * `candidate_route: null`;
    * `source_phase`;
    * `source_hook`;
    * selected route or runtime control;
    * target step / terminal / pending input id, if applicable.

* **Trace producer/verifier short-circuiting**

  * If a hook exits after producer but before verifier, trace:

    * `producer_attempted: true`;
    * `verifier_attempted: false`;
    * selected route/control;
    * source hook/phase.

* **Trace route/control source**

  * Distinguish:

    * provider-selected route;
    * hook-selected route;
    * python-step-selected route/control;
    * hook-selected direct runtime control.

* **Update history derivation**

  * History must not assume every completed step has a route.
  * History must handle:

    * `runtime_control=request_input`;
    * `runtime_control=goto`;
    * `runtime_control=fail`;
    * `provider_attempted=false`.
  * Route metrics should ignore direct runtime controls unless explicitly requested.

* **Provider retry attribution**

  * If no provider turn ran, provider retry must not run.
  * If a hook changes a provider-selected route, only obligations from the provider-selected route are provider-attributable.
  * Obligations introduced only by hook route/control selection are hook/workflow-attributable.

---

## Exception and failure model

* **Replace dynamic exception metadata**

  * Remove patterns that attach runtime fields dynamically to arbitrary exceptions, such as:

    * `checkpoint_state`;
    * `failure_context`;
    * `retry_kind`;
    * `pending_handoffs`.

* **Use structured exception types**

  * Add typed failure data instead of `setattr` / `getattr` conventions.

```python
@dataclass(frozen=True)
class FailureContext:
    kind: str
    step_name: str
    candidate_route: str | None = None
    final_route: str | None = None
    runtime_control: str | None = None
    provider_attributable: bool = False
    source_hook: str | None = None
    source_phase: str | None = None
    target_step: str | None = None
    pending_input_id: str | None = None
    details: dict[str, object] = field(default_factory=dict)
```

```python
class StepExecutionError(WorkflowExecutionError):
    checkpoint_state: BaseModel | None
    failure_context: FailureContext
    retry_kind: RetryKind | None
```

* **Remove `getattr`-based failure readers**

  * Failure state should come from typed exception fields.
  * Remove helper paths that recover checkpoint/failure/retry data from arbitrary exception attributes.

---

## Result dataclasses

* **Replace long positional tuples**

  * Replace long step/finalization/provider tuples with dataclasses.
  * Add:

    * `StepExecutionResult`;
    * `RouteFinalizationResult`;
    * `HookExecutionResult`;
    * `PairProviderResult`;
    * `ProviderExecResult`.

* **`StepExecutionResult`**

  * Should contain the full result of one step execution.

```python
@dataclass(frozen=True, slots=True)
class StepExecutionResult:
    state: BaseModel
    destination: str
    event: Event | None
    outcome: Outcome | None
    pending_handoffs: tuple[PendingHandoff, ...]

    producer_raw_output: str | None = None
    verifier_raw_output: str | None = None
    provider_usage: StepProviderUsage | None = None

    finalization: StepFinalizationRecord | None = None
    pending_input: PendingInput | None = None
```

* It should contain `StepFinalizationRecord`; it should not replace it.

* **`RouteFinalizationResult`**

  * Should replace the large `_finalize_step_result(...)` tuple.

```python
@dataclass(frozen=True, slots=True)
class RouteFinalizationResult:
    state: BaseModel
    destination: str
    event: Event | None
    pending_handoffs: tuple[PendingHandoff, ...]
    finalization: StepFinalizationRecord
    pending_input: PendingInput | None = None
```

* **`HookExecutionResult`**

  * Should represent hook output after normalization.

```python
@dataclass(frozen=True, slots=True)
class HookExecutionResult:
    event: Event | None = None
    control: RequestInput | Goto | Fail | None = None
    redirect: HookRouteRedirect | None = None
```

* **`PairProviderResult`**

  * Should replace producer/verifier tuple returns.

```python
@dataclass(frozen=True, slots=True)
class PairProviderResult:
    producer_raw_output: str
    verifier_raw_output: str | None
    outcome: Outcome | None
    producer_session: SessionBinding | None
    verifier_session: SessionBinding | None
    usage: StepProviderUsage
    direct_control: RequestInput | Goto | Fail | None = None
```

* **`ProviderExecResult`**

  * Should replace provider parse tuples.

```python
@dataclass(frozen=True, slots=True)
class ProviderExecResult:
    text: str
    session_id: str | None
    provider_metadata: dict[str, object]
    usage: TokenUsage | None = None
```

---

## Worklist helper API

* **Add `ctx.worklists`**

  * Expose worklist runtime operations through:

    * `ctx.worklists.<name>`;
    * `ctx.worklist(name)`;
    * `ctx.current_worklist`.

* **Add `ctx.worklist(name)`**

```python
ctx.worklist(name: str | Worklist) -> WorklistRuntimeView
```

* Resolves by object or name.

* Raises clearly if unknown.

* **Add `ctx.worklists.<name>`**

  * Attribute access equivalent to `ctx.worklist("name")`.
  * Unknown names raise `AttributeError`.

* **Add `ctx.current_worklist`**

  * Returns the active scoped step’s worklist view.
  * Fails clearly for unscoped steps.

* **Add `WorklistRuntimeView`**

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

* **Worklist helper semantics**

  * `selection` is read-only from author code.
  * `refresh()` reloads and updates the current selection.
  * `set_current_status(status)` updates the current item status and persists mutable sources.
  * `reset_current_status()` clears current status.
  * `advance()` only advances selection and returns:

    * `True` if another current item exists;
    * `False` if exhausted.
  * `advance()` must not route, finish, await input, or fail.
  * `advance_or(exhausted=...)`:

    * calls `advance()`;
    * returns `None` if another item exists;
    * returns the explicit `exhausted` value if exhausted.
  * `validate()` raises on invalid worklist source/items.
  * `validation_error()` returns `str | None`.

* **Worklist helper routing pattern**

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

* Worklist helpers mutate selection/status.

* Hook returns and route targets control execution.

* **Worklist helper trace events**

  * Emit:

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

* **Checkpoint behavior**

  * Worklist helper mutations must be reflected in worklist selection checkpoints.
  * Do not roll back helper mutations automatically on later failure.

---

## Route effects

* **Remove route effects from the public authoring model**

  * Do not expose route effect DSL as a public control mechanism.
  * Public route model should contain:

    * target;
    * provider visibility;
    * required writes;
    * handoff metadata;
    * `on_taken`.

* **Migrate route-effect use cases to worklist helpers**

  * Replace:

    * `Refresh(worklist)` → `ctx.worklists.<name>.refresh()`;
    * `SetStatus(worklist, status)` → `ctx.worklists.<name>.set_current_status(status)`;
    * `ResetCompletion(worklist)` → `ctx.worklists.<name>.reset_current_status()`;
    * `Advance(worklist, ...)` → `advance()` / `advance_or(...)` plus explicit hook return;
    * `Handoff(message)` → route `handoff` metadata or `Event(..., handoff=...)`.

* **Delete route effects after helper migration**

  * Remove:

    * `effects=` from `Route`;
    * `CompiledRoute.effects`;
    * `Refresh`;
    * `ResetCompletion`;
    * `SetStatus`;
    * `Advance`;
    * `_apply_route_effects(...)`;
    * `_execute_route_effect(...)`.

---

## Context architecture

* **Split public hook context from internal runtime context**

  * Public hooks receive a safe `ctx`.
  * Internal runtime collaborators receive a mutable internal runtime context or focused services.
  * Public `ctx` must not expose underscore mutators such as:

    * `_set_state`;
    * `_set_route`;
    * `_set_outcome`;
    * `_set_selection`;
    * `_cache_worklist_items`.

* **Keep public `ctx` ergonomic**

  * Public author-facing context should expose:

    * state;
    * params;
    * artifacts;
    * sessions;
    * worklists;
    * history;
    * route/event/outcome;
    * runtime controls;
    * input response.

* **Split internals into services**

  * Suggested internal services:

    * `ContextFiles`;
    * `ContextState`;
    * `ContextSessions`;
    * `ContextWorklists`;
    * `ContextArtifacts`;
    * `ContextHistory`;
    * `ContextControl`.

---

## Engine architecture

* **Make collaborators own behavior**

  * Move actual behavior into collaborators:

    * `StepDispatcher`: step-kind execution;
    * `RouteFinalizer`: hook/control/final route logic;
    * `HookRunner`: hook invocation and result normalization;
    * `ArtifactGuard`: effective required-write validation;
    * `StateRuntime`: state stores and built-in state updates;
    * `SessionRuntime`: session resolution/persistence;
    * `CheckpointManager`: checkpoint construction/failure checkpointing;
    * `WorkflowInvoker`: child workflow invocation;
    * `OperationRecorder`: `llm` / `classify` replay.
  * `Engine` should be only the orchestration loop.

* **Provider contract builder**

  * Extract provider contract assembly into `ProviderContractBuilder`.
  * Engine should not construct provider-visible route tables, artifact context, retry feedback, handoff context, and writable/required/readable artifact payloads directly.
  * `ProviderContractBuilder` should build:

    * step contracts;
    * producer contracts;
    * verifier contracts;
    * operation contracts if needed.

---

## Compiler and caching

* **Remove class-attached compile cache as source of truth**

  * Do not rely on `workflow_cls.__compiled_workflow__` or similar hidden class mutation as the authoritative cache.
  * Use an explicit compiler cache keyed by source/topology fingerprint.
  * If class definition changes, recompile.

* **Resume semantics**

  * Resume should load the saved run contract/topology from the run folder.
  * If current source/topology differs, warn and continue by default.
  * Do not hard-error on source/topology mismatch by default.
  * Fail only if an actual executable element needed to continue cannot be resolved.
  * Strict resume mode may hard-fail if explicitly configured.

* **Public topology source**

  * Public compiler path derives topology from step-local routes.
  * Class-level transition tables / `flow` should not be public simple authoring.

* **Hook validation**

  * Validate only:

    * hook is callable;
    * hook signature is exactly `hook(ctx)`;
    * hook is used in a valid slot.
  * Do not infer hook-returned routes statically.
  * Do not forbid route/control returns from `before`.

---

## Reads, requires, and prompt references

* **Keep implicit reads**

  * Prompt references may infer reads.
  * Inferred reads should appear in:

    * compile report;
    * provider contract;
    * topology/capability artifacts;
    * optimizer/history analysis.

* **`requires` is the hard precondition mechanism**

  * Missing `requires` fails before execution.
  * Missing implicit reads should not automatically block execution.
  * Missing implicit reads should render as unavailable context, not silently as an empty string.

* **Prompt placeholder validation**

  * Unknown prompt placeholders fail at compile/preflight.
  * Ambiguous prompt placeholders fail at compile/preflight.
  * Unknown artifact-template placeholders should fail.
  * Do not silently substitute `""` for unknown roots/attributes.
  * Optional placeholder behavior must be explicit if needed.

---

## Route/status/terminal vocabulary

* **Centralize status classification**

  * Add a central status/route/terminal module.
  * It should define helpers such as:

    * `is_terminal(...)`;
    * `terminal_to_run_status(...)`;
    * `runtime_control_to_terminal(...)`;
    * `route_is_rework(...)`;
    * `route_is_replan(...)`;
    * `route_is_input_request(...)`;
    * `normalize_run_status(...)`.

* **Use centralized helpers everywhere**

  * Engine, history, optimizer, trace normalization, static graph analysis, and docs should use the same classification logic.
  * Distinguish:

    * terminal: `AWAIT_INPUT`;
    * provider route tag: `"question"`;
    * runtime control: `RequestInput`;
    * run status: `"awaiting_input"`.

---

## Extension failure policy

* **Make extension failure policy explicit**

  * Add extension failure policies:

```python
ExtensionFailurePolicy = Literal["propagate", "record_and_continue"]
```

* **Default policies**

  * Runtime-critical extensions:

    * tracing;
    * observability;
    * git/workspace durability;
    * checkpoint-adjacent persistence;
    * default to `"propagate"`.
  * Non-critical observer extensions:

    * notifications;
    * metrics sidecars;
    * external logging;
    * default to `"record_and_continue"` unless configured otherwise.

* **Failure behavior**

  * Critical extension failure may fail the run.
  * Non-critical extension failure should be recorded in trace/events and should not override the original workflow failure.
  * Fatal handling should preserve the original workflow failure and add extension failures as structured diagnostics.

---

## Schema registry

* **Register every persisted schema**

  * Every persisted generated file should have a schema id:

    * run metadata;
    * checkpoint;
    * topology;
    * static graph;
    * trace records;
    * event records;
    * history summaries;
    * replay records;
    * provider contract snapshots.

* **Reader behavior**

  * Readers validate schema id.
  * Known old schemas migrate or fail with a clear migration error.
  * Do not use ad hoc schema strings outside the registry.

---

## Package/import boundaries

* **Enforce package import boundaries**

  * Production code should not import top-level:

    * `core`;
    * `runtime`;
    * `stdlib`;
    * `extensions`.
  * Use:

    * `autoloop.core`;
    * `autoloop.runtime`;
    * `autoloop.stdlib`;
    * `autoloop.extensions`.

* **Optimizer boundary**

  * Optimizer should use stable `autoloop.*` APIs and read-only inspection/query APIs.
  * Optimizer should not reach into arbitrary runtime internals.
  * Optimizer trace/status logic must understand:

    * hidden routes;
    * direct `Goto`;
    * direct `RequestInput`;
    * direct `Fail`;
    * no provider attempt.

---

## Internal vocabulary cleanup

* **Use final vocabulary everywhere**

  * Replace internal `outputs` with `writes`.
  * Replace internal `review_outputs` with `verifier_writes`.
  * Replace “system step” wording with `python_step`.
  * Replace old “pause” wording with “await input.”
  * Generated artifacts and capability payloads should use:

    * `writes`;
    * `producer_writes`;
    * `verifier_writes`.

* **Remove dunder-marker discovery**

  * Replace marker checks like:

    * `__autoloop_simple_declaration__`;
    * `__autoloop_simple_artifact_spec__`;
    * `__workflow_abstract__`;
    * `__strict_workflow__`.
  * Use typed declaration classes and `isinstance(...)`.

* **Remove handler alias installation**

  * Do not auto-install `on_<step>` staticmethod aliases.
  * Python steps carry their handler explicitly.
  * Discovery must not mutate workflow classes.

* **Remove legacy-style workflow class methods from public compiler path**

  * Remove public/simple support for:

    * `on_<step>` handlers;
    * `on_start`;
    * class-level outcome middleware.
  * Use explicit step hooks and declarations.

---

## `autoloop.core` boundary

* **Define `autoloop.core` as internal/power-user**

  * Do not document it as the main authoring surface.
  * Public authoring examples should import from `autoloop`.
  * Remove public route-effect exports once helpers replace them.
  * Keep internal kernel APIs only where intentionally supported.

---

## Tests

* **Hook control tests**

  * `before` returns route tag.
  * `before` returns `Event`.
  * `before` returns `RequestInput`.
  * `before` returns `Goto`.
  * `before` returns `Fail`.
  * `before_producer` returns route/control.
  * `before_verifier` returns route/control.
  * No provider call occurs when `before` short-circuits.
  * State/session mutations made before short-circuit are checkpointed.
  * Invalid route/control from `before` fails with current state/session preserved.

* **Single-arity hook tests**

  * All hook phases accept only `hook(ctx)`.
  * Multi-argument hooks are rejected.
  * No code path relies on positional hook arity overload.

* **Removed hook/state result tests**

  * Hook returning `BaseModel` is rejected.
  * `AfterStepResult` cannot be imported or used.
  * Tuple state/event returns from `python_step` are rejected.

* **`on_route` removal tests**

  * `on_route` cannot be passed to public declarations.
  * `CompiledStep` has no `on_route_hook`.
  * Engine does not execute a step-level route hook.

* **Scoped state tests**

  * Scoped step without custom step-item state exposes built-in `ctx.step_item_state`.
  * Worklist item state follows the chosen model:

    * either built-in item runtime state is always available;
    * or `ctx.item_state` requires explicit worklist item state.
  * Unscoped step accessing item state fails clearly.

* **Worklist helper tests**

  * `ctx.worklist("phases").refresh()` updates selection.
  * `ctx.worklists.phases.set_current_status("completed")` updates current item and persists mutable source.
  * `ctx.worklists.phases.reset_current_status()` clears status.
  * `ctx.worklists.phases.advance()` moves to next item and returns `True`.
  * `advance()` on final item returns `False`.
  * `advance_or(Goto("finalize"))` returns `Goto("finalize")` when exhausted.
  * `ctx.current_worklist` works only for scoped steps.
  * Helper mutations are checkpointed.
  * Helper events appear in trace/history.
  * Route-effect-equivalent workflows can be rewritten with `on_taken` hooks and preserve behavior.

* **Route-effect removal tests**

  * `Route.to(..., effects=...)` is rejected.
  * Generated topology/capability payloads contain no route effects.
  * Worklist advancement use cases are covered by helpers and `on_taken`.

* **Result dataclass tests**

  * No long tuple unpacking remains in step execution/finalization paths.
  * New fields can be added to result dataclasses without changing positional call sites.

* **Structured error tests**

  * Failure context is typed.
  * No runtime path depends on dynamic exception attributes.
  * Failure checkpoint preserves current mutated state/session.

* **Trace/history tests**

  * Pre-step `RequestInput` trace has `provider_attempted=false`.
  * Pre-step `Goto` trace has `target_step`.
  * Pre-step route return validates required writes and updates built-ins only if finalized.
  * Direct controls do not update `last_route`.

* **Compiler/cache/resume tests**

  * Workflow class change recompiles for new runs.
  * Resume warns on topology/source mismatch by default.
  * Strict resume mode hard-fails.
  * Resume continues with saved run contract when possible.

* **Import-boundary tests**

  * Production code imports through `autoloop.*`.
  * Public docs/examples import from `autoloop`.
  * No top-level `core`, `runtime`, or `stdlib` imports in production code.

---

## Documentation

* **Document final hook style only**

```python
def before(ctx):
    ...

def after(ctx):
    ...

Route.to(..., on_taken=...)
```

* **Document final hook returns only**

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

* **Document worklist helpers**

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
