Below is the standalone implementation spec for autoloop. It supersedes the previous specs where they conflict.

## Implementation target

* **Preserve the current successful direction**

---

## Canonical public naming

* **Use `produce_verify_step` as the final canonical name**

  * Do not reintroduce `review_step`.
  * Do not introduce `do_review_step`.
  * Do not support `do=` / `review=` aliases.
  * Keep the canonical parameter names:

```python
produce_verify_step(
    producer_prompt=...,
    verifier_prompt=...,
    producer_writes=[...],
    verifier_writes=[...],
)
```

* **Public API should include**

  * `Workflow`
  * `step`
  * `produce_verify_step`
  * `python_step`
  * `workflow_step`
  * `llm`
  * `classify`
  * `Prompt`
  * `Md`
  * `Json`
  * `Text`
  * `Raw`
  * `Route`
  * `Session`
  * `Continuity`
  * `Worklist`
  * `StateVar`
  * `Event`
  * `Outcome`
  * `FINISH`
  * `PAUSE`
  * `FAIL`
  * `SELF`

* **Public API should not include**

  * `SUCCESS`
  * `review_step`
  * `do_review_step`
  * `system_step`
  * `StrictWorkflow`
  * `RouteInfo`
  * `chain`
  * `Checkpoint`
  * `ChildWorkflowResult`
  * `ResolvedArtifacts`
  * old `out`
  * old `outputs`
  * public `produces`
  * `Param`

* **Reintroduce/export `StateVar` only as inline state sugar**

  * `StateVar` is no longer the canonical state model.
  * But it should be publicly available because the inline `state={...}` sugar needs it.
  * Do not reintroduce `Param`; workflow params remain Pydantic model based.

---

## Remove unneeded compatibility bridges

* **Remove the root package compatibility bridge**

  * Remove the root-level code that imports and calls `bridge_core_package(f"{__name__}.core")`. The current codebase still contains this compatibility bridge. 

* **Remove `autoloop_v3.core` compatibility package**

  * Delete or disable `autoloop_v3/core/__init__.py`, which currently exists only to bridge `autoloop_v3.core` imports through `bridge_core_package(__name__)`. 

* **Remove `core/_compat.py`**

  * Delete `core/_compat.py` after all imports no longer depend on it.
  * Remove all references to `bridge_core_package`.

* **Remove fallback imports in `autoloop/simple.py`**

  * Current `autoloop/simple.py` still tries `autoloop_v3.core` imports and then falls back to root `core` imports. 
  * Replace with one canonical import path.
  * For the current package layout, use direct `core...` imports unless the codebase is physically moved under `autoloop/core`.
  * Do not support both `autoloop_v3.core` and `core` long term.

* **Update strictness tests**

  * Remove tests that assert `autoloop_v3.core` bridge identity.
  * Add tests that importing `autoloop_v3.core` fails after migration.
  * Add tests that no production files import `core._compat` or `autoloop_v3.core`.
  * Keep only one canonical import path.

---

## Step state architecture

* **Every step must have built-in runtime state**

  * Built-in state is runtime-owned.
  * Built-in state is always present, even when the author declares no custom state.

* **Built-in state for every step**

```python
class StepRuntimeState(BaseModel):
    visits: int = 0
    last_route: str | None = None
    last_reason: str | None = None
```

* **Additional built-in state for `produce_verify_step`**

```python
class ProduceVerifyRuntimeState(StepRuntimeState):
    rework_count: int = 0
    replan_count: int = 0
```

* **Persist built-in state in checkpoints**

  * Persist:

    * `visits`
    * `last_route`
    * `last_reason`
    * `rework_count`
    * `replan_count`
  * Do not derive these from traces during normal execution.
  * Runtime should update these live and checkpoint them.

* **Update built-in state at runtime**

  * On step entry:

```text
step_state.visits += 1
```

* After hook resolution produces the final route:

```text
step_state.last_route = final_event.tag
step_state.last_reason = final_event.reason
```

* For `produce_verify_step`:

```text
if final_route in rework route set:
    step_state.rework_count += 1

if final_route in replan route set:
    step_state.replan_count += 1
```

* **Default route sets for counters**

  * Default rework routes:

```python
{"needs_rework", "minor_rework"}
```

* Default replan routes:

```python
{"needs_replan", "major_replan"}
```

* Allow `produce_verify_step` to override these later if needed:

```python
produce_verify_step(
    ...,
    rework_routes=("needs_rework",),
    replan_routes=("needs_replan",),
)
```

* This override is optional; the first implementation can hard-code the default sets if simpler.

---

## Reserved built-in state names

* **Use Option A: reserve built-in field names**

  * Built-in runtime fields and custom state fields share the same state object surface.
  * Therefore custom state may not define built-in names.

* **Reserved names for all steps**

  * `visits`
  * `last_route`
  * `last_reason`

* **Additional reserved names for `produce_verify_step`**

  * `rework_count`
  * `replan_count`

* **Compile-time validation**

  * If custom step state declares one of these names, raise a clear compile error:

```text
Step 'legal_review' custom state field 'last_route' conflicts with built-in runtime state.
Use ctx.step_state.last_route directly, or choose a different custom field name.
```

* **Important implication**

  * This sugar form is accepted in general:

```python
state={
    "attempts": StateVar(0),
    "custom_last_route": StateVar[str | None](None),
}
```

* But this exact form should fail because `last_route` is built in:

```python
state={
    "attempts": StateVar(0),
    "last_route": StateVar[str | None](None),
}
```

---

## Custom workflow state

* **Canonical workflow state uses Pydantic**

  * Workflow-level state remains declared through `State`.

```python
class ArticlePublicationState(BaseModel):
    approved: bool = False
    last_terminal_reason: str | None = None

class ArticlePublication(Workflow):
    State = ArticlePublicationState
```

* **If absent**

  * Use an empty Pydantic model:

```python
class EmptyState(BaseModel):
    pass
```

* **Runtime access**

```python
ctx.state.approved = True
```

* **Prompt access**

```text
{state.approved}
{state.last_terminal_reason}
```

* **Checkpoint behavior**

  * Instantiate fresh per run.
  * Serialize with `model_dump(mode="json")`.
  * Restore with `StateModel.model_validate(payload)`.
  * Deep-copy for hook rollback.

The pasted state architecture already specifies Pydantic-compatible checkpoint serialization and restore behavior. 

---

## Workflow params

* **Canonical workflow params use Pydantic**

  * Use `Params`, not `Parameters`.
  * Do not use public `Param(...)`.

```python
class ArticlePublicationParams(BaseModel):
    max_legal_attempts: int = 3

class ArticlePublication(Workflow):
    Params = ArticlePublicationParams
```

* **If absent**

  * Use an empty Pydantic model:

```python
class EmptyParams(BaseModel):
    pass
```

* **Runtime access**

```python
ctx.params.max_legal_attempts
```

* **Prompt access**

```text
{params.max_legal_attempts}
```

* **Validation**

  * Runtime parameter overrides must validate through the `Params` model.
  * If a workflow declares `Parameters`, fail clearly:

```text
Use Params, not Parameters.
```

---

## Custom step state

* **Canonical step state uses Pydantic**

```python
class LegalReviewState(BaseModel):
    attempts: int = 0
    approved_risk_level: str | None = None

legal_review = produce_verify_step(
    ...,
    state=LegalReviewState,
)
```

* **If absent**

  * Use only built-in step runtime state.
  * No custom fields.

* **Runtime access**

  * Built-in and custom fields are accessed through the same surface:

```python
ctx.step_state.visits
ctx.step_state.last_route
ctx.step_state.attempts
```

* **Prompt access**

```text
{legal_review.state.visits}
{legal_review.state.last_route}
{legal_review.state.attempts}
```

* **Validation**

  * Step state model must be a Pydantic `BaseModel` subclass.
  * It must be instantiable without required arguments.
  * It must not declare reserved built-in names.

---

## `StateVar` inline state sugar

* **Support dictionary sugar for step state**

```python
legal_review = produce_verify_step(
    ...,
    state={
        "attempts": StateVar(0),
        "approved_risk_level": StateVar[str | None](None),
    },
)
```

* **Compile sugar into a generated Pydantic model**

  * This should behave the same as:

```python
class GeneratedLegalReviewState(BaseModel):
    attempts: int = 0
    approved_risk_level: str | None = None
```

* **`StateVar` forms to support**

```python
StateVar(0)
StateVar(False)
StateVar("pending")
StateVar[str | None](None)
StateVar[list[str]](default_factory=list)
StateVar[dict[str, str]](default_factory=dict)
```

* **Type inference**

  * `StateVar(0)` infers `int`.
  * `StateVar(False)` infers `bool`.
  * `StateVar("x")` infers `str`.
  * `StateVar(None)` without an explicit type should fail because the type is ambiguous.
  * `StateVar[str | None](None)` is valid.

* **Mutable defaults**

  * Prefer `default_factory` for lists, dicts, and sets.
  * Either reject mutable literal defaults or deep-copy them safely.
  * Recommended: fail with a helpful error unless `default_factory` is provided.

* **Rejected sugar**

  * Do not support this pseudo-syntax:

```python
state={
    "attempts": int(0),
    "last_route": [str | None],
}
```

* Reasons:

  * `int(0)` is just `0` and loses type intent.
  * `[str | None]` is a list value, not a standard type declaration.
  * It conflicts with real list defaults.
  * It creates a custom mini-language that LLMs are likely to misuse.

---

## Item state

* **Implement item state**

  * Item state is required for scoped/worklist workflows.
  * It should be available, not deferred.

* **Worklist item state**

  * Worklist item state is shared by all steps operating on the same item.

```python
class ArticleItemState(BaseModel):
    status: str = "pending"
    attempts: int = 0

articles = Worklist.from_param(
    "articles",
    item_state=ArticleItemState,
)
```

* **Runtime access**

```python
ctx.item_state.status = "in_progress"
```

* **Prompt access**

```text
{item.state.status}
```

* **Storage key**

  * Store item state by:

    * run id;
    * worklist name;
    * item id.

---

## Step-item state

* **Implement step-item state**

  * Step-item state is specific to one step on one worklist item.
  * It prevents counters from being shared across items.

* **Declaration**

```python
class PerItemLegalReviewState(BaseModel):
    attempts: int = 0
    selected_risk: str | None = None

legal_review = produce_verify_step(
    ...,
    scope=articles,
    item_state=PerItemLegalReviewState,
)
```

* **Runtime access**

```python
ctx.step_item_state.attempts += 1
```

* **Prompt access**

```text
{legal_review.item_state.attempts}
```

* **Storage key**

  * Store step-item state by:

    * run id;
    * step name;
    * worklist name;
    * item id.

* **Built-in step-item state**

  * Scoped steps should also have built-in step-item runtime fields:

```python
visits
last_route
last_reason
```

* Scoped `produce_verify_step` step-item state additionally has:

```python
rework_count
replan_count
```

* **Aggregate and item-specific state**

  * For a scoped step, maintain both:

```text
legal_review.state
    aggregate across all items

legal_review.item_state
    state for this step on the current item
```

* **Collision rule**

  * Step-item custom state may not declare reserved built-in names.

---

## Checkpoint and resume changes

* **Checkpoint payload should include**

  * workflow state;
  * workflow params snapshot;
  * step states;
  * item states;
  * step-item states;
  * session bindings;
  * worklist selections;
  * pending handoffs;
  * pending questions/answers;
  * operation replay records, if applicable;
  * failure context.

* **Pydantic serialization**

  * Serialize all state models using:

```python
model_dump(mode="json")
```

* Restore using:

```python
StateModel.model_validate(payload)
```

* **Hook rollback**

  * Before route-finalization hooks, snapshot:

    * workflow state;
    * current step state;
    * current item state;
    * current step-item state;
    * session snapshot.

* **On hook failure**

  * Restore all snapshots.
  * Checkpoint failure context.
  * Emit hook failure event.

---

## Hook rerouting

* **Hooks may redirect routes**

  * This changes current behavior. The current implementation rejects non-`None` route-hook returns with “route hooks cannot redirect execution,” and tests currently encode rejection of hook route redirects. Both should change.

* **Allowed hook return values**

  * `None`: keep current route.
  * `str`: treat as a new route tag.
  * `Event`: use the event’s tag/reason/question/handoff.
  * If an internal structured hook result still exists, normalize it to one of the above.

* **Disallowed hook return values**

  * raw step objects;
  * raw terminal constants as destinations;
  * raw `Route` objects;
  * arbitrary destination strings.

* **Important distinction**

  * A hook returns a **route tag**, not a destination.
  * The returned route tag must be legal for the same step.
  * The compiled route table resolves the final target.

* **Example**

```python
def cap_rework(ctx):
    if ctx.step_state.rework_count >= ctx.params.max_legal_attempts:
        return "rejected"
    return None

legal_review = produce_verify_step(
    ...,
    routes={
        "accepted": FINISH,
        "needs_rework": Route.to(SELF, on_taken=cap_rework),
        "rejected": FINISH,
    },
)
```

* **Validation**

  * If hook returns `"rejected"`, `"rejected"` must be a declared route tag on the current step.
  * If hook returns `"some_unknown_route"`, fail with a clear runtime error.
  * Unknown hook routes should be workflow/runtime errors, not provider-attributable errors.

---

## Hook chaining

* **Allow hook chaining**

  * If a hook redirects to another valid route, the runtime should continue processing hooks for the new route.
  * Do not add a special one-hop rule.
  * Do not skip the redirected route’s hooks.

* **Generic hook-chain algorithm**

  * Start with candidate event from provider/python step.
  * Validate candidate route tag.
  * Run the step’s `after` / `after_verifier` hook once.
  * If it returns a route/Event, update the event and validate the new route tag.
  * Enter route-finalization loop:

    * Set `ctx.route` to the current route metadata.
    * Run step-level `on_route`, if present.
    * If it redirects, update event, emit redirect trace, and restart loop.
    * Run route-level `on_taken`, if present.
    * If it redirects, update event, emit redirect trace, and restart loop.
    * If no hook redirects, exit loop.
  * Validate selected-route required writes for the final route.
  * Resolve final route target.
  * Apply legacy internal effects if still present.
  * Checkpoint.
  * Transition.

* **Maximum hook redirects**

  * Add a generic safety cap:

```python
max_hook_redirects = 16
```

* If exceeded, fail with clear failure context:

```text
Hook redirect limit exceeded for step 'legal_review'.
Possible redirect cycle: needs_rework -> needs_replan -> needs_rework.
```

* This is not ad hoc logic; it is the hook equivalent of `max_steps`.

* **Hook trace events**

  * Emit:

    * `hook_started`
    * `hook_finished`
    * `hook_failed`
    * `hook_route_redirected`

* **Redirect trace payload**

```json
{
  "event_type": "hook_route_redirected",
  "step_name": "legal_review",
  "hook": "cap_rework",
  "phase": "on_taken",
  "from_route": "needs_rework",
  "to_route": "rejected"
}
```

* **Final step trace should include**

  * candidate route;
  * final route;
  * hook redirect chain.

```json
{
  "event_type": "step_finished",
  "step_name": "legal_review",
  "candidate_route": "needs_rework",
  "final_route": "rejected"
}
```

---

## Hook context updates

* **Context should expose route-finalization state**

  * During route hooks, expose:

```python
ctx.route.tag
ctx.route.target
ctx.route.summary
ctx.route.handoff
ctx.outcome
ctx.event
```

* **Context should expose mutable state**

  * `ctx.state`
  * `ctx.step_state`
  * `ctx.item_state`
  * `ctx.step_item_state`

* **Context should expose artifacts**

  * `ctx.artifacts`
  * `ctx.read(...)`
  * `ctx.write(...)`
  * `ctx.read_json(...)`
  * `ctx.write_json(...)`

* **Context should expose sessions**

  * `ctx.reset_global_session()`
  * `ctx.set_global_session(...)`
  * `ctx.open_session(...)`

* **Context should expose history**

  * `ctx.history`
  * See history section below.

---

## Effective required writes

* **Fix the current weird provider contract behavior**

  * If `writes=[Md("report", required=True)]`, the rendered provider contract should not show route `"done"` as requiring no writes.
  * Effective route required writes should be visible to the harness.

* **Route required writes semantics**

  * Change route required writes to distinguish:

```python
required_writes=None  # inherit artifact-level required=True writes
required_writes=[]    # this route requires no writes
```

* **Effective required writes formula**

```python
if route.required_writes is not None:
    effective_required_writes = route.required_writes
else:
    effective_required_writes = all step writes where required=True
```

* **Provider rendering**

  * Render effective required writes per route.
  * The provider should see:

```text
Route done requires: report
```

not:

```text
Route done requires: none
```

* **Topology artifacts**

  * `topology.json`, `route_table.md`, and provider contracts should include both:

    * explicit route required writes;
    * effective route required writes.

* **Runtime validation**

  * Validate final selected route using effective required writes.

---

## Built-in state vs derived telemetry

* **Persist only small built-in state**

  * Persist:

    * `visits`
    * `last_route`
    * `last_reason`
    * `rework_count`
    * `replan_count`

* **Do not persist telemetry dump**

  * Do not persist these as mutable checkpointed state:

    * status;
    * completed;
    * accepted_once;
    * retry_count;
    * timestamps;
    * durations;
    * errors;
    * artifact validation failures;
    * token usage;
    * do/verify attempts.

* **Derive large telemetry from events/traces**

  * Implement read-only history/telemetry layer.

---

## Derived telemetry

* **Add a history reader**

  * Add either:

```text
core/history.py
```

* or:

```text
runtime/history.py
```

* Prefer `core/history.py` if `Context` will expose it directly without creating a core→runtime dependency problem.

* **Context access**

```python
ctx.history.events()
ctx.history.trace()
ctx.history.step_telemetry()
ctx.history.step_telemetry("plan")
ctx.history.step_telemetry("implement_phase", item_id="phase_1")
ctx.history.routes(step="ship_patch")
ctx.history.failures()
ctx.history.token_usage(step="implement")
```

* **History reader must be read-only**

  * It must not mutate:

    * `events.jsonl`
    * `trace.jsonl`
    * `run.json`
    * `checkpoint.json`
    * raw provider logs.

* **Steps that derive diagnostics should write declared artifacts**

```python
@python_step(
    writes=[Json("diagnostics", Diagnostics, required=True)],
)
def build_diagnostics(ctx):
    telemetry = ctx.history.step_telemetry()
    failures = ctx.history.failures()
    ctx.write_json("diagnostics", Diagnostics.from_history(telemetry, failures))
```

---

## Telemetry fields to derive

* **Derived per-step telemetry should include**

  * `status`
  * `completed`
  * `finished_once`
  * `accepted_once`
  * `retry_count`
  * `timestamps`
  * `durations`
  * `errors`
  * `artifact_validation_failures`
  * `token_usage`
  * `do_attempts`
  * `verify_attempts`

* **Define `completed` carefully**

  * Do not define `completed` as “route is accepted.”
  * A route such as `"rejected": FINISH` still means the step completed execution.
  * Define:

```text
completed = step has at least one step_finished trace event
```

* **Define `accepted_once` separately**

  * `accepted_once` is semantic.
  * Default accepted route tags:

```python
{"done", "accepted", "approved"}
```

* Allow caller override:

```python
ctx.history.step_telemetry(success_routes={"ready_to_publish", "approved"})
```

* **Define `status` as derived**

  * Example statuses:

    * `pending`
    * `running`
    * `completed`
    * `paused`
    * `failed`
    * `needs_rework`
    * `needs_replan`
    * `routed`

* **Key telemetry by step instance**

  * Do not key only by step name.
  * Use:

```python
StepInstanceKey(
    step_name: str,
    scope: str | None = None,
    item_id: str | None = None,
)
```

* **Expose aggregate and scoped telemetry**

  * `ctx.history.step_telemetry("legal_review")`
  * `ctx.history.step_telemetry("legal_review", item_id="article_17")`

---

## Trace instrumentation required for exact telemetry

* **Add stable step execution ids**

  * Step start and finish records should include:

```json
{
  "step_name": "legal_review",
  "visit": 3,
  "step_execution_id": "legal_review:3"
}
```

* **For scoped steps**

  * Include:

```json
{
  "scope": "articles",
  "item_id": "article_17"
}
```

* **Provider attempt events**

  * Add:

```json
{
  "event_type": "provider_attempt_started",
  "step_name": "ship_patch",
  "turn_kind": "producer",
  "attempt": 1
}
```

```json
{
  "event_type": "provider_attempt_finished",
  "step_name": "ship_patch",
  "turn_kind": "verifier",
  "attempt": 1
}
```

```json
{
  "event_type": "provider_attempt_failed",
  "step_name": "ship_patch",
  "turn_kind": "verifier",
  "attempt": 1,
  "failure_context": {}
}
```

* **Hook redirect events**

  * Add `hook_route_redirected` as described above.

* **Artifact validation events**

  * Add structured events for:

    * missing required artifact;
    * invalid artifact;
    * schema validation failure.

* **Token usage**

  * Ensure `step_finished` or provider attempt events include provider usage by phase:

    * producer;
    * verifier;
    * llm;
    * operation.

---

## History implementation behavior

* **History reader input files**

  * `trace.jsonl`
  * `events.jsonl`
  * checkpoint failure context, if available
  * optionally raw provider metadata if needed

* **Missing files**

  * If `trace.jsonl` does not exist, return partial telemetry from `events.jsonl`.
  * Do not fail simply because tracing is disabled.

* **Caching**

  * Avoid rereading the full trace repeatedly inside hot hook loops.
  * Cache by:

    * path;
    * file size;
    * modified time.
  * First implementation may read fully, but context history should not be called implicitly by runtime on every step.

---

## Prompt references for state

* **Workflow state**

```text
{state.field}
```

* **Workflow params**

```text
{params.field}
```

* **Step state**

```text
{step_name.state.field}
```

* **Current item state**

```text
{item.state.field}
```

* **Step-item state**

```text
{step_name.item_state.field}
```

* **Validation**

  * Validate against the Pydantic model fields.
  * Unknown fields should fail clearly:

```text
Unknown state field: legal_review.state.attemps
Did you mean: legal_review.state.attempts?
```

* Suggestions are optional but useful.

The pasted state architecture already describes prompt references resolving against Pydantic model instances and failing clearly on unknown fields. 

---

## Runtime update order

* **Normal step lifecycle**

  * Build context.
  * Load workflow state, step state, item state, and step-item state.
  * Increment built-in visit counters.
  * Validate `requires`.
  * Run `before`.
  * Execute provider/python/workflow operation.
  * Produce candidate `Event`.
  * Run `after`.
  * Resolve hook chain.
  * Update built-in state from final route.
  * Validate final route required writes.
  * Checkpoint state/session/artifacts.
  * Transition.

* **`produce_verify_step` lifecycle**

  * Build context.
  * Load state surfaces.
  * Increment built-in visit counters.
  * Validate `requires`.
  * Run `before_producer`.
  * Run producer.
  * Run `after_producer`.
  * Validate `verifier_requires`, if declared.
  * Run `before_verifier`.
  * Run verifier.
  * Produce candidate `Event`.
  * Run `after_verifier`.
  * Resolve hook chain.
  * Update built-in state from final route.
  * Validate final route required writes.
  * Checkpoint.
  * Transition.

---

## Testing requirements

* **Hook rerouting**

  * `after` hook returning a valid route string succeeds.
  * `after` hook returning an invalid route string fails.
  * `after` hook returning `Event("some_route")` succeeds if route exists.
  * `on_route` hook returning a valid route string reroutes.
  * `Route.to(..., on_taken=...)` hook returning a valid route string reroutes.
  * Hook redirect chain works across multiple valid routes.
  * Hook redirect cycle fails after `max_hook_redirects`.
  * Hook redirect emits `hook_route_redirected` events.
  * Final selected route is used for transition and required-write validation.

* **State built-ins**

  * Every step has `visits`, `last_route`, `last_reason`.
  * `produce_verify_step` has `rework_count`, `replan_count`.
  * Built-ins update on final route after hook chain.
  * Built-ins persist across checkpoint/resume.
  * Hook-mutated custom state persists across checkpoint/resume.

* **Reserved names**

  * Custom step state field `last_route` fails.
  * Custom step state field `visits` fails.
  * Custom `produce_verify_step` field `rework_count` fails.
  * Error message suggests using built-in fields directly.

* **StateVar sugar**

  * `state={"attempts": StateVar(0)}` compiles to Pydantic state.
  * `StateVar[str | None](None)` works.
  * `StateVar(None)` without explicit type fails.
  * `StateVar[list[str]](default_factory=list)` works.
  * Mutable defaults without factory fail or deep-copy safely.
  * StateVar sugar colliding with built-in names fails.

* **Item state**

  * `Worklist.from_param(..., item_state=ArticleItemState)` works.
  * `ctx.item_state` is available for scoped steps.
  * `{item.state.status}` resolves.
  * Item state checkpoints and restores.

* **Step-item state**

  * Scoped `produce_verify_step(..., item_state=PerItemLegalReviewState)` works.
  * `ctx.step_item_state` is available.
  * `{legal_review.item_state.attempts}` resolves.
  * Step-item state is isolated per item.
  * Aggregate step state and per-item step state do not collide.

* **Effective required writes**

  * Artifact-level `required=True` appears in effective route required writes.
  * `Route.to(..., required_writes=None)` inherits artifact requiredness.
  * `Route.to(..., required_writes=[])` requires no writes.
  * Provider contract renders effective required writes.
  * Runtime validates final selected route using effective required writes.

* **History**

  * `ctx.history.step_telemetry()` works with `trace.jsonl`.
  * Works without `trace.jsonl`, using partial `events.jsonl`.
  * Telemetry is keyed by step and scoped item.
  * `completed` is true for any `step_finished`, including rejected terminal routes.
  * `accepted_once` uses configurable accepted route set.
  * Retry/do/verify attempts are exact when provider attempt events exist.
  * Token usage is aggregated by phase.

* **Compatibility removal**

  * Importing `autoloop_v3.core` fails after bridge removal.
  * No production file imports `core._compat`.
  * `autoloop.simple` does not fallback to `autoloop_v3.core`.
  * Removed aliases fail to import.
  * Canonical imports still work.

---

## Migration order

* **Phase 1: compatibility bridge removal**

  * Update imports to one canonical path.
  * Remove `autoloop_v3.core` bridge.
  * Remove root bridge.
  * Remove `core/_compat.py`.
  * Update strictness tests.

* **Phase 2: hook rerouting**

  * Allow `str` / `Event` hook returns.
  * Implement hook-chain resolution loop.
  * Add max redirect depth.
  * Add hook redirect trace events.
  * Update old tests that expected redirect rejection.

* **Phase 3: state surfaces**

  * Add built-in step state.
  * Add `produce_verify_step` extra built-ins.
  * Add custom step state via Pydantic.
  * Add `StateVar` sugar.
  * Reserve built-in field names.
  * Persist state in checkpoints.

* **Phase 4: item and step-item state**

  * Add `Worklist.item_state`.
  * Add scoped `ctx.item_state`.
  * Add step scoped `item_state`.
  * Add `ctx.step_item_state`.
  * Add prompt references.

* **Phase 5: effective required writes**

  * Preserve `None` versus `[]`.
  * Render effective required writes.
  * Validate final route using effective required writes.

* **Phase 6: history/telemetry**

  * Add read-only `ctx.history`.
  * Add telemetry derivation.
  * Add provider attempt instrumentation.
  * Add hook redirect instrumentation.
  * Add scoped telemetry keys.

---

## Final target example

```python
from pydantic import BaseModel, Field

from autoloop import (
    Workflow,
    Worklist,
    Prompt,
    Md,
    Json,
    Route,
    StateVar,
    FINISH,
    SELF,
    step,
    produce_verify_step,
)

class ArticlePublicationParams(BaseModel):
    max_legal_attempts: int = 3

class ArticlePublicationState(BaseModel):
    approved: bool = False
    last_terminal_reason: str | None = None

class ArticleItemState(BaseModel):
    status: str = "pending"

class Decision(BaseModel):
    approved: bool
    reason: str

def cap_rework(ctx):
    if ctx.step_item_state.rework_count >= ctx.params.max_legal_attempts:
        return Event("rejected", reason="Legal review attempt budget exhausted.")
    return None

class ArticlePublication(Workflow):
    Params = ArticlePublicationParams
    State = ArticlePublicationState

    articles = Worklist.from_param(
        "articles",
        item_state=ArticleItemState,
    )

    prepare = step(
        prompt=Prompt.file("prompts/prepare_publication.md"),
        writes=[
            Md("publish_package", required=False),
            Md("legal_risk_notes", required=False),
            Md("rejection_reason", required=False),
        ],
        routes={
            "ready_to_publish": Route.to(
                FINISH,
                required_writes=["publish_package"],
            ),
            "needs_legal_review": Route.to(
                "legal_review",
                required_writes=["publish_package", "legal_risk_notes"],
            ),
            "rejected": Route.to(
                FINISH,
                required_writes=["rejection_reason"],
            ),
        },
    )

    legal_review = produce_verify_step(
        producer_prompt=Prompt.file("prompts/legal_producer.md"),
        verifier_prompt=Prompt.file("prompts/legal_verifier.md"),
        scope=articles,
        requires=[prepare.publish_package],
        producer_writes=[
            Md("legal_analysis", required=False),
        ],
        verifier_writes=[
            Md("legal_review_report", required=True),
            Json("decision", Decision, required=False),
        ],
        state={
            "selected_risk_level": StateVar[str | None](None),
        },
        item_state={
            "local_notes": StateVar[str | None](None),
        },
        routes={
            "approved": Route.to(
                FINISH,
                required_writes=[
                    "legal_analysis",
                    "legal_review_report",
                    "decision",
                ],
            ),
            "needs_rework": Route.to(
                SELF,
                required_writes=["legal_review_report"],
                on_taken=cap_rework,
            ),
            "rejected": Route.to(
                FINISH,
                required_writes=["legal_review_report", "decision"],
            ),
        },
    )
```

Key expected behavior in this example:

* `legal_review.state.visits`, `last_route`, `last_reason`, `rework_count`, and `replan_count` exist automatically.
* `selected_risk_level` is custom step state from `StateVar`.
* `last_route` cannot be declared as custom state because it is reserved.
* `ctx.step_item_state.rework_count` is per article, not shared across all articles.
* `cap_rework` may reroute from `"needs_rework"` to `"rejected"` by returning `Event("rejected", ...)`.
* The redirected route is legal because `"rejected"` is declared on the same step.
* Hook chaining is allowed if the redirected route has its own hooks.
* Final required writes are validated for the final route, not the initial candidate route.
