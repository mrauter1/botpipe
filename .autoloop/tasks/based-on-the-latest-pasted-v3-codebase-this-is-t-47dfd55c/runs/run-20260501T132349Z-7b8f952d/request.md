Based on the latest pasted v3 codebase, this is the **remaining-delta spec**: it does not restate features already implemented, and it assumes the current baseline still has `PAUSE`, public `on_route`, top-level `core/runtime/stdlib/extensions`, `autoloop_v3/core`, workflow-facing git/tracing extensions, underscore operation-surface classes, AST hook route analysis, and optimizer imports from top-level internals. 

## Public terminal and runtime-control surface

* **Replace `PAUSE` with `AWAIT_INPUT`**

  * Remove `PAUSE` entirely from public and internal terminal surfaces.
  * Add:

```python
AWAIT_INPUT = "AWAIT_INPUT"
```

* Final public terminal constants:

```python
FINISH
AWAIT_INPUT
FAIL
SELF
```

* Update all references in:

  * `core.primitives`;
  * `core.__init__`;
  * `autoloop.simple`;
  * `autoloop.__init__`;
  * provider-rendered contracts;
  * route validation;
  * topology/static graph generation;
  * run metadata;
  * checkpoint metadata;
  * trace/event payloads;
  * optimizer status logic;
  * tests;
  * docs/examples.

* **Add explicit runtime-control objects**

  * Add public classes:

```python
RequestInput
Goto
Fail
```

* Suggested definitions:

```python
@dataclass(frozen=True, slots=True)
class RequestInput:
    question: str
    reason: str | None = None
    best_supposition: str | None = None
    input_schema: type[BaseModel] | dict[str, object] | None = None
```

```python
@dataclass(frozen=True, slots=True)
class Goto:
    target: str | object
    reason: str | None = None
    handoff: str | None = None
```

```python
@dataclass(frozen=True, slots=True)
class Fail:
    reason: str
```

* `RequestInput(...)` suspends the run with terminal `AWAIT_INPUT`.

* `Goto(...)` transitions directly to a declared step.

* `Fail(...)` terminates with terminal `FAIL`.

* **Validate runtime-control objects**

  * `RequestInput.question` must be non-empty.
  * `RequestInput.input_schema`, when provided, must be a valid Pydantic model type or schema mapping.
  * `Goto.target` must resolve to a declared workflow step.
  * `Fail.reason` must be non-empty.
  * Invalid runtime-control returns are runtime errors and should preserve current state/session.

* **Expose resumed input through context**

  * Add a stable context surface for input supplied after `AWAIT_INPUT`, for example:

```python
ctx.input_response
```

* Resume behavior:

  * load pending input metadata from checkpoint;
  * validate supplied input against `input_schema` when present;
  * expose the validated answer through context;
  * clear pending input once consumed.

* **Use pending-input terminology**

  * Replace pending-question-only metadata with pending-input metadata.
  * Checkpoint should store:

    * terminal: `AWAIT_INPUT`;
    * source step;
    * source hook/control;
    * question;
    * reason;
    * best supposition;
    * input schema;
    * created timestamp;
    * pending input id.

---

## Hook API simplification

* **Remove public `on_route`**

  * Delete `on_route` from public declaration signatures:

    * `step(...)`;
    * `produce_verify_step(...)`;
    * `python_step(...)`;
    * `workflow_step(...)`.
  * Remove `on_route` from:

    * declaration objects;
    * capability snapshots;
    * docs/examples;
    * tests;
    * generated authoring surface reports.

* **Final public hook surface**

  * Plain steps:

    * `before`;
    * `after`.
  * `produce_verify_step`:

    * `before_producer`;
    * `after_producer`;
    * `before_verifier`;
    * `after_verifier`.
  * Route-local hook:

    * `Route.to(..., on_taken=...)`.

* **Define hook return normalization**

  * Hooks may return:

    * `None`;
    * route tag string;
    * `Event(...)`;
    * `RequestInput(...)`;
    * `Goto(...)`;
    * `Fail(...)`.

* **String hook returns**

  * A plain string always means a route tag.
  * A plain string must never be interpreted as a step target.
  * If the string is not a declared route tag on the current step, fail clearly.

* **Event hook returns**

  * `Event(tag=...)` must reference a declared route tag on the current step.
  * Preserve event metadata:

    * reason;
    * question;
    * handoff;
    * payload/control fields.

* **Runtime-control hook returns**

  * `RequestInput(...)`, `Goto(...)`, and `Fail(...)` are direct runtime controls.
  * They are not route tags.
  * They do not require a declared route.
  * They should be validated, traced, checkpointed, and executed directly.

* **Direct controls stop route-hook chaining**

  * If `after` or `on_taken` returns `RequestInput`, `Goto`, or `Fail`, stop the hook chain and execute that runtime control.
  * Route hook chaining continues only for route-tag or `Event` reroutes.

---

## Hidden/internal routes

* **Add provider visibility to routes**

  * Extend `Route.to(...)` with:

```python
provider_visible: bool = True
```

* **Hidden route semantics**

  * Hidden routes:

    * are declared routes;
    * are valid hook return route tags;
    * are included in compiled topology;
    * are included in route table artifacts;
    * may define `required_writes`;
    * may define `handoff`;
    * may define `on_taken`;
    * are excluded from provider-visible route choices.

* **Provider rendering**

  * Provider contracts must render only routes where `provider_visible=True`.

* **Topology rendering**

  * Topology artifacts must include both provider-visible and hidden routes.
  * Mark hidden routes explicitly:

```json
{
  "route": "human_escalation",
  "target": "human_escalation",
  "provider_visible": false
}
```

* **Usage guidance encoded in docs**

  * Use hidden routes for known SOP branches that should not be selected by the provider.
  * Use `Goto(...)` for exceptional or dynamic runtime jumps where route metadata is intentionally unnecessary.

---

## Runtime-control execution semantics

* **`RequestInput(...)` execution**

  * Set terminal to `AWAIT_INPUT`.
  * Write pending-input checkpoint payload.
  * Do not require provider-visible `"question"`.
  * Do not apply route-required-write validation.
  * Do not update built-in `last_route`.
  * Emit runtime-control trace/event records.

* **`Goto(...)` execution**

  * Validate the target step.
  * Set the next step cursor directly to the target.
  * Do not pretend a route was taken.
  * Do not update built-in `last_route`.
  * Do not apply route-required-write validation.
  * Emit runtime-control trace/event records.

* **`Fail(...)` execution**

  * Set terminal to `FAIL`.
  * Preserve current state/session.
  * Do not update built-in `last_route`.
  * Emit runtime-control trace/event records.

* **Provider-selected question route**

  * Provider may still select route tag `"question"` if the step declares it.
  * That route should target `AWAIT_INPUT`.
  * Provider-selected `"question"` remains provider-attributable and must include a valid question payload.
  * Hook-returned `RequestInput(...)` is runtime-attributable, not provider-attributable.

---

## Hook chaining and finalization

* **Route hook chaining**

  * If `Route.on_taken` returns a valid route tag or `Event(...)`, continue processing the new route’s `on_taken`.
  * Continue until:

    * no hook redirects;
    * a direct runtime control is returned;
    * the redirect cap is reached.

* **Redirect cap**

  * Add a generic redirect cap:

```python
max_hook_redirects = 16
```

* On cap exceedance:

  * fail with structured failure context;
  * preserve current state/session;
  * include redirect chain in trace/history.

* **Failure preservation**

  * On hook failure, step failure, route-finalization failure, provider failure, artifact validation failure, or runtime-control validation failure:

    * do not restore state snapshots automatically;
    * do not restore session snapshots automatically;
    * checkpoint current workflow state;
    * checkpoint current step state;
    * checkpoint current item state;
    * checkpoint current step-item state;
    * checkpoint current session bindings;
    * record failure context.

* **Artifact validation timing**

  * For route-based finalization:

    * execute `after`;
    * normalize hook result;
    * run route-local `on_taken` chain;
    * resolve final route;
    * validate final route’s effective required writes;
    * update runtime-owned built-in route fields;
    * checkpoint;
    * transition.
  * For direct runtime controls:

    * validate the control object;
    * checkpoint;
    * execute the control.
  * Direct runtime controls bypass route-required-write validation.

* **Built-in state update timing**

  * `visits` increments on step entry.
  * `last_route`, `last_reason`, `rework_count`, and `replan_count` update only after successful route-based finalization.
  * Candidate routes do not update built-in route fields.
  * Routes that fail required-write validation do not update built-in route fields.
  * Direct controls do not update built-in route fields.

---

## Runtime-control tracing and metadata

* **Add runtime-control event types**

  * For `RequestInput(...)`:

```json
{
  "event_type": "hook_runtime_control",
  "control": "request_input",
  "step_name": "...",
  "hook": "...",
  "question": "...",
  "reason": "...",
  "pending_input_id": "..."
}
```

* For `Goto(...)`:

```json
{
  "event_type": "hook_runtime_control",
  "control": "goto",
  "step_name": "...",
  "hook": "...",
  "target_step": "...",
  "reason": "..."
}
```

* For `Fail(...)`:

```json
{
  "event_type": "hook_runtime_control",
  "control": "fail",
  "step_name": "...",
  "hook": "...",
  "reason": "..."
}
```

* **Step finalization records should include**

  * candidate route;
  * final route when route-based;
  * runtime control when direct-control-based;
  * target step for `Goto`;
  * terminal for `RequestInput` and `Fail`;
  * hook redirect chain;
  * provider-attributable flag;
  * source hook;
  * source phase.

* **Hook redirect records**

  * Preserve the existing route-redirect trace concept.
  * Include:

    * from route;
    * to route;
    * hook name;
    * hook phase;
    * redirect index.

* **Provider attribution**

  * If provider-selected route and final route differ because of a hook, only obligations from the provider-selected route are provider-attributable.
  * Obligations introduced only by hook redirection are workflow/hook-attributable.
  * `RequestInput`, `Goto`, and `Fail` are runtime-attributable.

---

## Built-in state protection

* **Expose built-in and custom state through one user-facing surface**

  * Keep:

```python
ctx.step_state.visits
ctx.step_state.last_route
ctx.step_state.selected_risk_level
```

* **Implement as a state view internally**

  * Use an internal structure like:

```text
StepStateView
    runtime: StepRuntimeState
    custom: CustomStepState | None
```

* **Runtime-owned fields are read-only**

  * Authors can read:

    * `visits`;
    * `last_route`;
    * `last_reason`;
    * `rework_count`;
    * `replan_count`.
  * Authors cannot assign to them.

* **Custom fields remain mutable**

  * Authors can mutate declared custom state fields:

```python
ctx.step_state.selected_risk_level = "medium"
ctx.step_item_state.local_notes = "Needs follow-up."
```

* **Reserved built-in names**

  * Reject custom state fields named:

    * `visits`;
    * `last_route`;
    * `last_reason`;
    * `rework_count`;
    * `replan_count`.

* **Apply the same model to step-item state**

  * Runtime-owned step-item fields are read-only.
  * Custom step-item fields are mutable.

---

## Public API hard cut

* **Remove old public names**

  * Remove from public API:

    * `PAUSE`;
    * `on_route`;
    * `review_step`;
    * `do_review_step`;
    * `system_step`;
    * `SUCCESS`;
    * `StrictWorkflow`;
    * `RouteInfo`;
    * `chain`;
    * `out`;
    * `outputs`;
    * public `produces`.

* **Final public exports**

  * Public authoring exports should include:

    * `Workflow`;
    * `step`;
    * `produce_verify_step`;
    * `python_step`;
    * `workflow_step`;
    * `llm`;
    * `classify`;
    * `Prompt`;
    * `Md`;
    * `Json`;
    * `Text`;
    * `Raw`;
    * `Route`;
    * `Session`;
    * `Continuity`;
    * `Worklist`;
    * `StateVar`;
    * `Event`;
    * `Outcome`;
    * `RequestInput`;
    * `Goto`;
    * `Fail`;
    * `FINISH`;
    * `AWAIT_INPUT`;
    * `FAIL`;
    * `SELF`.

* **Remove compatibility package**

  * Delete `autoloop_v3/` entirely.
  * Remove the current `autoloop_v3/core/__init__.py` stub.

* **Remove compatibility imports**

  * Delete fallback import branches.
  * Delete compatibility bridges.
  * Use one canonical import path throughout.

---

## Package layout

* **Use one package namespace**

  * Move internal packages under `autoloop/`:

```text
autoloop/
  __init__.py
  simple.py
  core/
  runtime/
  stdlib/
  extensions/
```

* **Canonical imports only**

```python
from autoloop.core import ...
from autoloop.runtime import ...
from autoloop.stdlib import ...
from autoloop.extensions import ...
```

* **Remove top-level internal imports**

  * Remove production imports from top-level:

    * `core`;
    * `runtime`;
    * `stdlib`;
    * `extensions`.

* **Public package root**

  * `autoloop.__init__` must export the final public authoring API.
  * It must not be empty.

---

## Optimizer boundary

* **Update optimizer imports**

  * Replace direct imports from top-level `core`, `runtime`, and `stdlib` with stable `autoloop.*` imports.

* **Expose a stable inspection/query API**

  * Add stable read-only APIs for:

    * listing runs;
    * loading run records;
    * loading topology artifacts;
    * loading history;
    * inspecting workflow capabilities;
    * resolving workflow references.

* **Optimizer should consume stable APIs**

  * Optimizer modules should not reach into arbitrary runtime/core internals.
  * Use stable inspection/query functions for observability and workflow introspection.

* **Update optimizer status/terminal logic**

  * Replace old terminal/status references to `PAUSE`.
  * Distinguish:

    * terminal: `AWAIT_INPUT`;
    * provider route tag: `"question"`;
    * status: `"awaiting_input"`.
  * Update static graph centrality terminal filters.
  * Update route exclusion sets.
  * Update optional optimization artifact finalization logic.
  * Update run history normalization.

---

## Git/tracing extension cleanup

* **Delete workflow-facing git/tracing declarations**

  * Delete:

    * `extensions/git/declaration.py`;
    * `extensions/tracing.py`.

* **Remove public exports**

  * Remove:

    * `GitTracking`;
    * `GitTrackingConfig`;
    * `Tracing`;
    * `TracingConfig`.

* **Keep runtime-owned infrastructure**

  * Keep runtime git/tracing infrastructure used by the runtime.
  * Runtime tracing and git tracking are not workflow extensions.

* **Keep extension protocol for user-defined extensions**

  * Runtime extension observers remain separate from workflow authoring hooks.

---

## Remove AST hook analysis

* **Delete static hook route inference**

  * Remove AST parsing used to infer hook-returned route strings.
  * Remove compile-time hook-route inference functions.
  * Remove tests that expect compile-time AST detection of hook route strings.

* **Keep simple hook validation**

  * Validate:

    * callable;
    * arity/signature;
    * supported placement.

* **Runtime validation handles returns**

  * String return: validate as route tag.
  * `Event`: validate event tag.
  * `RequestInput`: validate question.
  * `Goto`: validate target step.
  * `Fail`: validate reason.

---

## Structured errors

* **Remove private exception annotation**

  * Remove patterns such as:

    * `exc._checkpoint_state`;
    * `exc._failure_context`;
    * `exc._provider_retry_kind`.

* **Add structured failure context**

```python
@dataclass(frozen=True, slots=True)
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

* **Add structured execution error**

```python
class StepExecutionError(WorkflowExecutionError):
    checkpoint_state: BaseModel | None
    failure_context: FailureContext
    retry_kind: RetryKind | None
```

* **Use structured errors in**

  * provider retry;
  * hook failure;
  * route validation;
  * runtime-control validation;
  * artifact validation;
  * checkpoint failure persistence;
  * trace/history records.

---

## Replay behavior

* **Change replay fingerprint**

  * Remove source hash from per-operation replay fingerprint.
  * Remove full topology hash from per-operation replay fingerprint.

* **Per-operation fingerprint should include**

  * operation kind;
  * prompt content hash;
  * resolved prompt reference values;
  * return schema hash;
  * choices hash;
  * callsite identity;
  * occurrence index;
  * scope/item coordinate;
  * provider operation configuration.

* **Mismatch behavior**

  * Add:

```python
replay_mismatch_behavior: Literal["warn", "fail"] = "warn"
```

* Default:

  * emit warning event;
  * return cached value.

* Strict mode:

  * fail.

* **Update replay tests**

  * Default mismatch should warn and replay.
  * Strict mismatch should fail.

---

## Provider contract and route rendering

* **Provider-visible route filtering**

  * Provider route table renders only routes with `provider_visible=True`.

* **Hidden routes in non-provider artifacts**

  * Topology, route table, compile report, static graph, and capability snapshots include hidden routes.

* **Effective required writes**

  * Preserve distinction:

    * `required_writes is None`: inherit artifact-level `required=True`;
    * `required_writes == []`: no required writes.
  * Render both:

    * explicit required writes;
    * effective required writes.

* **Runtime validation**

  * Route-based finalization validates effective required writes.
  * Runtime controls do not apply route-required-write validation.

---

## Topology and generated artifacts

* **Write static artifacts at run creation**

  * Generate before the first step starts:

    * `topology.json`;
    * `topology.mmd`;
    * `route_table.md`;
    * `artifact_contracts.json`;
    * `prompt_refs.json`;
    * `state_contracts.json`;
    * `session_contracts.json`;
    * `compile_report.md`;
    * `static_step_graph.json`.

* **Topology artifacts should include**

  * provider-visible routes;
  * hidden/internal routes;
  * route-local `on_taken` hooks;
  * effective required writes;
  * explicit required writes;
  * terminal constants;
  * state surfaces;
  * item-state surfaces;
  * step-item-state surfaces;
  * runtime-control hook locations.

* **Mermaid/static graph**

  * Mark hidden routes differently from provider-visible routes.
  * Do not infer possible `Goto(...)` targets from hook source.
  * Runtime `Goto(...)` transitions appear in trace/history.

---

## Prompt registry

* **Inject prompt registry from resolved paths**

  * Build registry from:

    * workflow parent;
    * compiled prompt paths;
    * workflow capability prompt paths;
    * configured prompt roots.

* **Runtime services receive registry**

  * Do not reconstruct registry from only one parent directory.
  * Prompt resolution failures should be explicit.

---

## Operation surfaces

* **Rename operation-surface classes**

  * Replace `_LLMOperationSurface` with `LLMOperation`.
  * Replace `_ClassifyOperationSurface` with `ClassifyOperation`.

* **Public singleton objects**

```python
llm = LLMOperation()
classify = ClassifyOperation()
```

* **Add**

  * docstrings;
  * `__repr__`;
  * public type stubs;
  * public exports.

---

## Engine decomposition

* **Split engine collaborators**

  * Extract:

    * `StepDispatcher`;
    * `RouteFinalizer`;
    * `HookRunner`;
    * `ArtifactGuard`;
    * `StateRuntime`;
    * `SessionRuntime`;
    * `CheckpointManager`;
    * `OperationRecorder`;
    * `WorkflowInvoker`.

* **Engine role**

  * `Engine` owns the FSM orchestration loop.
  * Collaborators own finalization, dispatch, validation, sessions, checkpoints, operation replay, and child workflow invocation.

---

## Validation/compiler decomposition

* **Split validation/compiler modules**

  * Create:

    * `autoloop/core/discovery.py`;
    * `autoloop/core/lowering.py`;
    * `autoloop/core/inventory.py`;
    * `autoloop/core/topology.py`;
    * `autoloop/core/hook_validation.py`;
    * `autoloop/core/prompt_validation.py`;
    * `autoloop/core/state_validation.py`.

* **Hook validation module**

  * Validate callable and signature only.
  * Do not infer route returns.

---

## Session store cleanup

* **Unify session store logic**

  * Replace parallel implementations with backend composition:

```python
class SessionStore:
    def __init__(self, backend: SessionBackend): ...
```

```python
class InMemorySessionBackend(SessionBackend): ...
class FilesystemSessionBackend(SessionBackend): ...
```

* **Responsibility split**

  * Store owns session semantics.
  * Backend owns persistence.

---

## Worklist loading

* **Cache worklist item loading per step execution**

  * Cache key:

    * run id;
    * step execution id;
    * worklist name.
  * Invalidate between steps.
  * Avoid repeated artifact-backed worklist reads during selection/restore for the same step execution.

---

## Child workflow results

* **Make child workflow result typed**

```python
class ChildWorkflowResult(Generic[OutputT]):
    output: OutputT | None
    artifacts: Mapping[str, Path]
    terminal: str
    last_event: Event | None
```

* **Typed output behavior**

  * If the child workflow declares an output model, expose typed `output`.
  * Preserve artifact paths and child run metadata.

---

## Mapping/dict normalization

* **Boundary normalization**

  * Public APIs may accept `Mapping[str, Any]`.
  * Convert to `dict[str, Any]` once at the boundary.
  * Internal code should use `dict[str, Any]`.

* **Remove scattered conversions**

  * Remove repeated internal `dict(payload)` defensive conversions where the boundary already normalized the value.

---

## Schema registry

* **Centralize generated artifact schemas**

  * Every generated artifact should use a schema id from schema registry:

    * run metadata;
    * checkpoint;
    * topology;
    * static graph;
    * trace records;
    * event records;
    * history summaries;
    * operation replay records.

* **Reader behavior**

  * Known older schemas should either be tolerated or fail with clear migration errors.

---

## Runtime state and checkpointing

* **Checkpoint current state on failure**

  * On step failure, hook failure, artifact failure, provider failure, runtime-control failure, or route-finalization failure:

    * persist current workflow state;
    * persist current step state;
    * persist current item state;
    * persist current step-item state;
    * persist current session bindings;
    * persist failure context.

* **Built-in route state truthfulness**

  * Runtime-owned route fields reflect finalized route transitions only.
  * Candidate routes and runtime controls live in trace/history.
  * Custom state/session mutations may persist even if finalization fails.

---

## Documentation and examples

* **Canonical docs should use**

  * `FINISH`;
  * `AWAIT_INPUT`;
  * `RequestInput`;
  * `Goto`;
  * `Fail`;
  * `produce_verify_step`;
  * `before`;
  * `after`;
  * `Route.to(..., on_taken=...)`;
  * `State`;
  * `Params`;
  * `StateVar` only as inline sugar.

* **Canonical docs should not use**

  * `PAUSE`;
  * `on_route`;
  * `on_outcome`;
  * `review_step`;
  * `do_review_step`;
  * `system_step`;
  * `SUCCESS`;
  * `chain`;
  * route effect DSL;
  * direct raw string step-target reroutes;
  * top-level `core` / `runtime` / `stdlib` imports.

---

## Testing requirements

* **Runtime controls**

  * Hook returns `RequestInput`; run terminal is `AWAIT_INPUT`.
  * Pending input metadata is checkpointed.
  * Resume supplies input.
  * Input validates against schema.
  * Resumed answer is available through context.
  * Hook returns `Goto`; runtime jumps to declared step.
  * Hook returns `Fail`; run terminates with `FAIL`.
  * Hook returns `Goto` to unknown step; failure preserves current state/session.
  * Hook returns raw string matching no route; failure preserves current state/session.

* **Hidden routes**

  * Hidden route appears in topology.
  * Hidden route does not appear in provider route choices.
  * Hook can return hidden route tag.
  * Hidden route `on_taken` executes.
  * Provider prompt excludes hidden route.

* **Hook chains**

  * Route A `on_taken` redirects to route B.
  * Route B `on_taken` redirects to route C.
  * Route C finalizes.
  * Trace contains full redirect chain.
  * Redirect cycle fails after max redirects and preserves current state/session.
  * Direct control returned from `on_taken` stops route chaining.

* **State preservation**

  * Hook mutates custom state, then artifact validation fails.
  * Checkpoint preserves custom state mutation.
  * Session changes made by hook are preserved.
  * Built-in `last_route` does not record unfinalized route.

* **Read-only built-ins**

  * Assigning to `ctx.step_state.visits` fails.
  * Assigning to `ctx.step_state.last_route` fails.
  * Assigning to custom state field succeeds.

* **AWAIT_INPUT**

  * Provider-selected `"question"` routes to `AWAIT_INPUT`.
  * Hook-returned `RequestInput` routes to `AWAIT_INPUT` without provider-visible `"question"`.
  * Checkpoint stores pending input payload.

* **Public API hard cut**

  * `PAUSE` cannot be imported.
  * `on_route` is not accepted as a declaration argument.
  * `autoloop_v3` cannot be imported.
  * top-level `core`, `runtime`, and `stdlib` imports are absent from production code.
  * removed public names cannot be imported.

* **Replay mismatch**

  * Fingerprint mismatch warns and returns cached value by default.
  * Strict mode fails.

* **Prompt registry**

  * Prompt outside workflow parent but inside declared prompt paths resolves.
  * Missing prompt fails clearly.

* **Topology artifacts**

  * Artifacts are written at run creation.
  * Hidden routes are included.
  * Effective required writes are included.
  * Artifacts exist even if first step fails.

* **Optimizer boundary**

  * Optimizer imports only through stable `autoloop.*` paths or inspection APIs.
  * Optimizer status logic recognizes `AWAIT_INPUT`.

* **Golden workflow**

  * Add one end-to-end workflow exercising:

    * `State`;
    * `Params`;
    * `StateVar` sugar;
    * `step`;
    * `produce_verify_step`;
    * worklist scope;
    * item state;
    * step-item state;
    * hidden route;
    * `on_taken` redirect chain;
    * `RequestInput`;
    * `Goto`;
    * `Fail`;
    * effective required writes;
    * `llm()` in `python_step`;
    * `classify.step()`;
    * checkpoint/resume;
    * topology artifacts;
    * history/telemetry.

---

## Final implementation order

* **Phase 1: Public surface and terminal cleanup**

  * Replace `PAUSE` with `AWAIT_INPUT`.
  * Add `RequestInput`, `Goto`, `Fail`.
  * Remove public `on_route`.
  * Remove old public names.

* **Phase 2: Runtime-control semantics**

  * Normalize hook returns.
  * Implement runtime controls.
  * Implement hidden route visibility.
  * Update finalization logic.
  * Preserve state/session on failure.
  * Keep built-in route state finalized-only.

* **Phase 3: Metadata and observability**

  * Add pending-input checkpoint model.
  * Add runtime-control events.
  * Add candidate/final route/runtime-control records.
  * Update provider attribution.

* **Phase 4: Validation cleanup**

  * Remove AST hook analysis.
  * Keep callable/signature validation.
  * Runtime-validate hook returns and controls.

* **Phase 5: Rendering and topology**

  * Filter provider-visible routes.
  * Include hidden routes in topology.
  * Preserve effective required-write rendering.
  * Write topology artifacts at run creation.

* **Phase 6: Package cleanup**

  * Move internals under `autoloop/`.
  * Delete `autoloop_v3/`.
  * Remove top-level internal imports.
  * Update optimizer imports.

* **Phase 7: Maintainability refactors**

  * Split engine.
  * Split validation/compiler modules.
  * Add structured errors.
  * Unify session stores.
  * Rename operation-surface classes.

* **Phase 8: Tests and docs**

  * Add runtime-control tests.
  * Add hidden-route tests.
  * Add pending-input resume tests.
  * Add public API removal tests.
  * Add golden workflow.
  * Update canonical docs/examples.
