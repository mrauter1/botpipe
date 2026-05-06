## Full revised standalone spec: Autoloop v3 async-native providers and explicit branch groups

* **Spec status**

  * This is the implementation contract for the next pass.
  * This spec supersedes the mixed sync/async transition model in the uploaded implementation. 
  * The implementation should be treated as greenfield internally.
  * Public workflow authoring APIs for ordinary non-parallel execution must remain stable.

---

## 1. Project stance

* Treat provider execution and branch-group execution as greenfield internals.
* Do not preserve legacy sync-provider internals.
* Do not add compatibility shims for old sync provider implementations.
* Do not add thread-backed fallback behavior.
* Do not keep partially compatible sync/async execution paths that conflict with the clean async-native model.
* Prefer a smaller, correct async-native v1 over a broad compatibility layer.
* If an internal implementation detail conflicts with this spec, change the implementation rather than adding adapters around it.
* Public non-parallel workflow authoring should not change.
* Ordinary sequential workflows should continue to feel exactly the same to authors.
* New parallel capabilities should be additive.

---

## 2. Public API compatibility requirement

* The public authoring API for non-parallel workflows must remain unchanged.
* Existing workflow authors should not need to change:

  * `Workflow`
  * `step(...)`
  * `llm(...)`
  * `produce_verify_step(...)`
  * `python_step(...)`
  * `workflow_step(...)`
  * `Session`
  * `Session.fresh()`
  * `Session.run()`
  * `Continuity`
  * `Route`
  * `Event`
  * `Outcome`
  * artifact helpers such as `Md`, `Json`, `Text`, `Raw`
  * route declarations
  * hook declarations
  * worklist declarations
  * CLI invocation shape
  * normal runtime runner usage
* Existing non-parallel workflows should continue to run through the same public entrypoints.
* A public synchronous runtime entrypoint may remain:

  * `Engine.run(...)`
  * existing CLI runner calls
  * existing package runner calls
* Any public sync runtime entrypoint must be only an outer shell around async internals.
* Public sync runtime entrypoints must not preserve sync provider execution internally.
* Public sync runtime entrypoints must not introduce threads.
* Public sync runtime entrypoints should fail clearly if called from an already running event loop, unless a dedicated async entrypoint is used.
* Additive public APIs:

  * `parallel(...)`
  * `fan_out(...)`
  * `FanIn.results()`
  * `FanIn.context()`

---

## 3. Internal architecture requirement

* Provider execution is async-native internally.
* Provider transports are async-native internally.
* Step execution is async-first internally.
* Branch-group execution is async-native.
* `engine.py` remains the top-level workflow cursor.
* Branch scheduling, branch context construction, session overlays, manifest generation, fan-in orchestration, and outcome aggregation must live outside `engine.py`.
* `engine.py` may wire collaborators together.
* `engine.py` must not become the implementation home for branch-group runtime logic.

---

## 4. Async-native provider architecture

* Define one provider protocol.
* Provider protocol methods are async.
* Do not keep separate sync and async provider protocols.
* Do not use `_async` suffixes for provider methods; async is the only provider contract.
* Required provider shape:

```python
class LLMProvider(Protocol):
    async def run_llm(self, request: LLMRequest) -> OutcomeResponse: ...
    async def run_producer(self, request: ProducerRequest) -> ProducerResponse: ...
    async def run_verifier(self, request: VerifierRequest) -> OutcomeResponse: ...
```

* Remove sync provider methods:

  * sync `run_llm(...)`
  * sync `run_producer(...)`
  * sync `run_verifier(...)`
* Remove compatibility async methods:

  * `run_llm_async(...)`
  * `run_producer_async(...)`
  * `run_verifier_async(...)`
* Branch groups should not ask whether a provider supports async.
* Any provider object that does not satisfy the async provider contract is invalid.
* Provider construction may validate that the provider methods are coroutine functions.
* Provider construction validation is allowed.
* Branch-group runtime capability probing is not allowed.

---

## 5. Async-native transport architecture

* Define one provider transport protocol.
* Transport method is async.
* Do not keep separate sync and async transport protocols.
* Do not use `_async` suffixes for transport methods.
* Required transport shape:

```python
class ProviderTransport(Protocol):
    async def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult: ...
```

* Remove sync transport method:

  * sync `run_turn(...)`
* Remove compatibility async method:

  * `run_turn_async(...)`
* Built-in transports must be async-native.
* Transport construction may validate that `run_turn` is coroutine-callable.
* Do not keep a sync transport and reject it later.
* Invalid transports should fail during provider construction.

---

## 6. Rendered provider wrapper

* `RenderedLLMProvider` should be async-only.
* It should expose:

  * `async def run_llm(...)`
  * `async def run_producer(...)`
  * `async def run_verifier(...)`
* It should call:

  * `await transport.run_turn(...)`
* It should not expose:

  * sync `run_llm(...)`
  * sync `run_producer(...)`
  * sync `run_verifier(...)`
  * `run_llm_async(...)`
  * `run_producer_async(...)`
  * `run_verifier_async(...)`
* It should not contain sync transport fallback logic.
* It should not contain provider async-support probing logic.
* It may still own provider-contract behavior:

  * prompt rendering
  * outcome parsing
  * malformed output validation
  * missing session id validation where applicable
  * route validation support
  * usage metadata normalization
  * retry-related metadata

---

## 7. Built-in provider transports

* Codex transport must be async-native.
* Claude transport must be async-native.
* Built-in CLI transports must use:

  * `asyncio.create_subprocess_exec(...)`
  * async stdin handling
  * async stdout handling
  * async stderr handling
  * native task cancellation behavior
* Built-in CLI transports must not use:

  * `subprocess.run(...)`
  * blocking `subprocess.Popen(...)`
  * `ThreadPoolExecutor`
  * `asyncio.to_thread(...)`
  * `concurrent.futures`
* Provider subprocess cancellation should:

  * request process termination where possible
  * kill the process if needed
  * report cancellation/failure clearly
* Transport parsing semantics should remain equivalent to current Codex/Claude parsing behavior, but implemented over async I/O.

---

## 8. Provider backend builders

* Provider backend builders must return async-native providers.
* Provider backend builders must not expose sync-vs-async configuration.
* Provider backend builders must not wrap sync transports in async facades.
* Provider backend builders must not create branch-group-specific compatibility behavior.
* If a backend cannot be represented as an async-native provider, construction should fail.
* Runtime should not discover that a provider is invalid only after branches have started.

---

## 9. Fake provider

* Fake providers must implement the async provider contract directly.
* Fake providers must not wrap sync provider methods.
* Fake providers may be in-memory.
* Fake providers may complete immediately.
* Fake providers may use `await asyncio.sleep(...)` in tests to prove real scheduling.
* Fake providers should support deterministic scripted responses for:

  * LLM steps
  * producer turns
  * verifier turns
  * question routes
  * failures
  * cancellation tests
* Fake providers should record request session bindings so tests can assert:

  * first branch turn receives `session_id=None`
  * branch executions using the same `Session.fresh()` declaration receive distinct provider contexts
  * provider-returned session ids are persisted into branch results

---

## 10. Allowed sync behavior

* Sync behavior is allowed only where structurally useful and not part of provider execution.
* Allowed sync surfaces:

  * CLI entrypoint calling `asyncio.run(...)`
  * temporary public `Engine.run(...)` wrapper around `Engine.run_async(...)`
  * synchronous Python step functions
  * synchronous hooks
  * local artifact reads/writes
  * manifest/context document file writes
* Disallowed sync surfaces:

  * provider execution
  * provider transport execution
  * provider subprocess execution
  * branch scheduling
  * branch concurrency
  * branch provider cancellation
* Python steps and hooks may block the event loop in v1.
* Blocking Python steps/hooks are acceptable as an explicit v1 limitation.
* Do not offload Python steps or hooks to threads in v1.

---

## 11. Engine execution model

* Add or complete an async-first engine path:

```python
async def run_async(...) -> RunResult: ...
```

* Public sync `run(...)` may remain:

```python
def run(...):
    return asyncio.run(self.run_async(...))
```

* `run(...)` must fail clearly if called from an active event loop unless an appropriate async path is used.
* `run(...)` must not:

  * call sync providers
  * use thread pools
  * hide async execution failures
  * add provider compatibility behavior
* The top-level engine loop remains responsible for:

  * workflow cursor
  * checkpointing
  * extension notifications
  * terminal handling
  * normal step transitions
* Branch groups remain delegated to a branch-group runtime subsystem.

---

## 12. Step dispatcher

* Step dispatcher should be async-first internally.
* Preferred API:

```python
async def execute(
    step: CompiledStep,
    context: Context,
    state: BaseModel,
    pending_handoffs: tuple[PendingHandoff, ...],
    *,
    route_mode: RouteMode = "finalize",
) -> StepExecutionResult: ...
```

* Supported route modes:

  * `route_mode="finalize"` for normal top-level execution
  * `route_mode="capture"` for branch execution
* Step dispatcher should await provider-backed steps directly.
* Step dispatcher should execute Python steps directly inside the event loop.
* Step dispatcher should not use thread offloading.
* Step dispatcher should not contain sync-provider fallback logic.
* A temporary sync wrapper around `execute(...)` is acceptable only as an outer boundary, not for branch-group internals.

---

## 13. Explicit branch groups

* Add two explicit branch-group primitives:

  * `parallel(...)`
  * `fan_out(...)`
* `parallel(...)` runs multiple distinct authored branch steps concurrently.
* `fan_out(...)` runs the same authored branch step multiple times over different branch inputs.
* Branch groups are explicit only.
* No parallelism is inferred from:

  * `reads`
  * `requires`
  * `writes`
  * prompt placeholders
  * artifact declarations
  * route topology
  * worklist topology

---

## 14. Branch group core semantics

* A branch group is a composite barrier step.
* A branch group externally behaves like one workflow step.
* A branch group internally schedules multiple branch executions.
* A branch executes exactly one branch step.
* A branch records the branch step route/result.
* A branch does not follow its route destination in the parent workflow graph.
* Parent workflow cursor remains on the composite branch-group step until the branch group resolves.
* If `fan_in` exists:

  * branch group resolves through the fan-in route.
* If `fan_in` does not exist:

  * branch group resolves through a mechanical outcome policy.
* Branches share parent workflow state by default.
* Branches share workspace by default.
* Branches share `ctx.values` by default.
* Branches may mutate parent workflow state.
* Branches may write any workspace path.
* Branches may intentionally write overlapping files.
* The framework does not:

  * infer workspace conflicts
  * fail on workspace conflicts
  * merge files
  * auto-merge state
  * require state ownership declarations

---

## 15. `parallel(...)`

* Required input:

  * `branches`: non-empty mapping from branch name to step declaration
* Optional inputs:

  * `concurrency`
  * `settle`
  * `fan_in`
  * `outcome`, only when `fan_in` is absent
  * `success_routes`, only when mechanical outcome needs route interpretation
  * `routes`, only when `fan_in` is absent and outcome routes need explicit destinations
* Each branch executes its branch step exactly once.
* Each branch gets:

  * branch name
  * branch index
  * branch group name
  * branch count
  * branch input `{}` in v1
* Branch route destinations are captured, not followed.
* Composite route comes from fan-in or outcome policy.

---

## 16. `fan_out(...)`

* Required input:

  * `step`: one authored step declaration
  * `branches`: non-empty mapping from branch name to branch input
* Optional inputs:

  * `concurrency`
  * `settle`
  * `fan_in`
  * `outcome`, only when `fan_in` is absent
  * `success_routes`, only when mechanical outcome needs route interpretation
  * `routes`, only when `fan_in` is absent and outcome routes need explicit destinations
* Each branch executes the same branch step exactly once.
* Each branch receives its own branch input.
* Branch input should be JSON-serializable in v1.
* Branch route destinations are captured, not followed.
* Composite route comes from fan-in or outcome policy.

---

## 17. `fan_in`

* `fan_in` is optional.
* `fan_in` is available on both:

  * `parallel(...)`
  * `fan_out(...)`
* `fan_in` is a normal authored step.
* `fan_in` may be:

  * provider-backed LLM step
  * produce/verify step
  * Python step
* Child workflow fan-in is vFuture unless explicitly redesigned.
* `fan_in` runs after branch settlement.
* `fan_in` receives:

  * branch manifest
  * branch group context document
  * parent workflow state
  * shared values
  * normal workspace access
* `fan_in` may use normal parent session semantics.
* `fan_in` is not required to use `Session.fresh()`.
* `fan_in` is not:

  * a merge policy
  * a state reconciler
  * a workspace conflict resolver
* `fan_in` route becomes the composite branch-group route.
* `fan_in` route must finalize exactly once.

---

## 18. Branch scheduling

* BranchGroupRuntime is async-native.
* Branch scheduling uses:

  * `asyncio.create_task(...)`
  * `asyncio.Semaphore`
* Branch cancellation uses:

  * `task.cancel()`
* No branch work may use:

  * threads
  * `ThreadPoolExecutor`
  * `asyncio.to_thread(...)`
  * `concurrent.futures`
* Branch result order in the manifest follows declaration order.
* Branch completion order must not affect manifest order.
* `concurrency` must be positive when provided.
* If `concurrency` is omitted, all branches may be scheduled concurrently subject to runtime limits.
* `concurrency=1` is valid and still uses branch-group semantics.

---

## 19. Settlement policy

* Supported v1 settlement policies:

  * `settle="all"`
  * `settle="fail_fast"`
* Default:

  * `settle="all"`
* `settle="all"`:

  * schedules all branches subject to concurrency
  * waits for every branch to produce a result
  * records completed, failed, needs-input, cancelled, and skipped branches
* `settle="fail_fast"`:

  * cancels active/pending tasks after first hard branch failure
  * records cancelled branches
  * records not-yet-started branches as skipped
  * still writes branch manifest/context when possible
* `quorum` is vFuture.

---

## 20. Branch provider sessions

* Provider-backed branch steps must explicitly declare `Session.fresh()`.
* Missing session is a compile-time error.
* Non-fresh session is a compile-time error.
* Fresh branch sessions are fresh per branch execution.
* Two branches using the same `Session.fresh()` declaration must not share provider context.
* Two `fan_out(...)` executions of the same step must not share provider context.
* Branch-local session overlay must not activate branch sessions in the parent store.
* Branch-local session overlay must not fall back to parent active provider sessions for provider-backed branch execution.
* A fresh branch session binding starts with `session_id=None`.
* Provider receives `session_id=None` on first turn of a fresh branch session.
* Branch result records provider session ids only after the provider returns real session ids.
* No synthetic provider session ids.

---

## 21. Branch session keys

* Branch-local fresh session keys must include branch execution identity.
* Conceptual key:

```text
slot=<session slot>
domain="fresh"
value=<group>:<branch>:<index>:<unique-token>
```

* Do not use `domain="run"` for branch fresh sessions.
* Provider-backed branch lookups should not fall back to parent active sessions.
* Diagnostic snapshots may include parent data only if clearly separated from provider lookup behavior.

---

## 22. Shared state cell

* Branch contexts share one state cell.
* Conceptual structure:

```python
@dataclass(slots=True)
class StateCell:
    value: BaseModel
    version: int = 0

    def set(self, value: BaseModel) -> BaseModel:
        self.value = value
        self.version += 1
        return value
```

* `Context.state` getter reads from `StateCell.value`.
* `Context.state` setter writes to `StateCell.value`.
* `context_runtime(...).set_state(...)` updates the same state cell.
* State cell version is diagnostic only.
* State cell version does not imply conflict detection.
* No thread locks in `StateCell`.

---

## 23. Shared values

* `ctx.values` is shared within a branch group.
* Branches may mutate shared values.
* The framework does not merge values.
* The framework does not detect values conflicts.
* Last actual mutation wins unless the author synchronizes.
* Shared values mutation is intentionally nondeterministic under cooperative interleaving.
* Authors needing deterministic aggregation should prefer branch artifacts plus fan-in.
* No `SynchronizedValuesDict`.
* No thread locks around values.

---

## 24. Branch metadata

* Branch contexts expose `ctx.branch`.
* `ctx.branch` is available only during branch execution.
* Fields:

  * `ctx.branch.name`
  * `ctx.branch.index`
  * `ctx.branch.group`
  * `ctx.branch.input`
  * `ctx.branch.count`
* For `parallel(...)`:

  * `ctx.branch.input == {}`
* For `fan_out(...)`:

  * `ctx.branch.input` is the branch payload.

---

## 25. Fan-in metadata

* Fan-in contexts expose `ctx.fan_in`.
* `ctx.fan_in` is available only during fan-in execution.
* Fields:

  * `ctx.fan_in.results`
  * `ctx.fan_in.results_path`
  * `ctx.fan_in.context_path`
  * `ctx.fan_in.context_text`
  * `ctx.fan_in.branch_count`
  * `ctx.fan_in.completed_count`
  * `ctx.fan_in.failed_count`
  * `ctx.fan_in.needs_input_count`
  * `ctx.fan_in.cancelled_count`
* Fan-in context does not expose a single active `ctx.branch`.

---

## 26. Placeholder rules

* Branch placeholders valid in branch prompts and branch artifact templates:

  * `{branch.name}`
  * `{branch.index}`
  * `{branch.group}`
  * `{branch.count}`
  * `{branch.input.<field>}`
* Fan-in placeholders valid in fan-in prompts and fan-in artifact templates:

  * `{fan_in.results_path}`
  * `{fan_in.context_path}`
  * `{fan_in.context_text}`
  * `{fan_in.branch_count}`
  * `{fan_in.completed_count}`
  * `{fan_in.failed_count}`
  * `{fan_in.needs_input_count}`
  * `{fan_in.cancelled_count}`
* Branch placeholders are invalid outside branch steps.
* Fan-in placeholders are invalid outside fan-in steps.
* Placeholder validation must compare the root token exactly.
* Do not use:

  * `startswith("branch")`
  * `startswith("fan_in")`

---

## 27. Templated artifact path rooting

* Templated relative artifact paths remain rooted like normal step-owned artifacts.
* Example:

```text
assessments/{branch.name}.json
```

* This should resolve under the normal owner step/workflow artifact root.
* Templated paths must not resolve relative to process working directory.
* Templated and non-templated step artifacts must use consistent rooting semantics.

---

## 28. Branch evidence paths

* Every branch group writes:

```text
{workflow_folder}/_branch_groups/<group_name>/results.json
{workflow_folder}/_branch_groups/<group_name>/context.md
```

* Per-branch raw output should be stored or referenced under:

```text
{workflow_folder}/_branch_groups/<group_name>/branches/<branch_name>/...
```

* Do not write branch evidence directly under repository root.
* `FanIn.results()` resolves to `results.json`.
* `FanIn.context()` resolves to `context.md`.
* Helper resolution must not be ambiguous about root.

---

## 29. Runtime-owned namespace

* `_branch_groups` is runtime-owned.
* User artifacts may technically write under `_branch_groups` because writes are unrestricted.
* User writes under `_branch_groups` are discouraged.
* Diagnostics may warn when declared artifacts target `_branch_groups`.
* V1 should not reject such writes.

---

## 30. Branch manifest

* Schema id:

```text
autoloop.branch_results/v1
```

* Top-level fields:

  * `schema`
  * `kind`
  * `name`
  * `started_at`
  * `finished_at`
  * `duration_ms`
  * `concurrency`
  * `settle`
  * `success_routes`
  * `branches`
* `kind` values:

  * `parallel`
  * `fan_out`
* Branch result fields:

  * `name`
  * `index`
  * `input`
  * `step_name`
  * `status`
  * `route`
  * `destination`
  * `runtime_control`
  * `reason`
  * `question`
  * `artifacts`
  * `raw_output_path`
  * `raw_output_paths`
  * `provider_session`
  * `provider_sessions`
  * `error`
  * `started_at`
  * `finished_at`
  * `duration_ms`
  * `usage`
* Branch status values:

  * `completed`
  * `failed`
  * `needs_input`
  * `cancelled`
  * `skipped`

---

## 31. Branch group context document

* Branch group context document is markdown.
* It is deterministic.
* It is optimized for LLM fan-in review.
* It includes:

  * branch group name
  * branch group kind
  * branch count
  * settlement policy
  * success route policy
  * completion summary
  * route summary
  * failure summary
  * needs-input summary
  * cancellation summary
  * per-branch input
  * per-branch status
  * per-branch route
  * per-branch destination
  * per-branch runtime control
  * per-branch reason
  * per-branch question
  * per-branch artifact paths
  * per-branch error summary
  * raw output paths
* It should not embed full raw logs by default.
* It should not embed huge artifacts by default.
* It should reference large content by path.

---

## 32. Branch success semantics

* Branch completion is not the same as branch success.
* Branch steps can have arbitrary route tags.
* Mechanical outcome policies need a success predicate.
* Branch groups without fan-in must define or inherit `success_routes`.
* Recommended default:

```python
success_routes=("done", "accepted")
```

* Authors may override:

```python
success_routes=("approved", "ready")
```

* A branch is successful when:

  * `status == "completed"`
  * `route in success_routes`
* A completed branch with a route outside `success_routes` is not successful for mechanical outcome purposes.
* When fan-in exists, `success_routes` may be used for summaries but does not determine the composite route.

---

## 33. Outcome policy without fan-in

* If fan-in is absent, outcome policy chooses the composite route.
* Supported built-ins:

  * `all_done`
  * `all_settled`
  * `any_done`
  * custom aggregator
* Default:

  * `outcome="all_done"`
* Built-in external route tags:

  * `done`
  * `partial`
  * `failed`
  * `question`
* If any branch needs input and no fan-in exists:

  * default composite route is `question`
  * composite question is a deterministic summary of branch questions
* Custom aggregator:

  * receives manifest and current context
  * returns an `Event`
  * must return a legal composite route

---

## 34. Branch-level questions

* With fan-in:

  * branch question becomes `status="needs_input"`
  * branch question text is recorded in the manifest
  * branch question text is included in context markdown
  * fan-in decides whether to ask the user
* Without fan-in:

  * branch question contributes to mechanical outcome
  * default composite route is `question`
* V1 does not resume an individual branch from its own question.
* V1 does not pause the parent workflow directly from a branch question when fan-in exists.

---

## 35. Direct runtime controls inside branches

* Branch route event:

  * record route
  * record reason/question/handoff when present
  * do not follow destination
* Branch `RequestInput`:

  * record `status="needs_input"`
  * record question/reason
  * do not directly pause parent when fan-in exists
* Branch `Goto`:

  * record `status="completed"`
  * record target destination
  * do not follow target
* Branch `Fail`:

  * record `status="failed"`
  * record failure context
* Branch result must distinguish:

  * route tag
  * route destination
  * runtime control kind
  * branch status

---

## 36. Capture-only route mode

* Branch execution uses `route_mode="capture"`.
* Capture mode:

  * runs before hooks
  * runs provider/system body
  * runs after hooks
  * validates artifacts
  * validates route legality
  * computes route destination
  * records route/destination
  * does not run route `on_taken`
  * does not schedule handoffs
  * does not follow destination
* Normal top-level execution uses `route_mode="finalize"`.
* Fan-in should capture its event and finalize exactly once through the composite branch-group route.

---

## 37. Hooks

* Branch steps run before hooks.
* Branch steps run after hooks.
* Branch steps do not run route `on_taken` hooks in v1.
* Fan-in runs normal before/after hooks.
* Fan-in route finalization runs exactly once at the composite level.
* Composite step emits outer lifecycle events.
* Branch hook events should be nested under the branch group.
* Git/checkpoint-like extensions should checkpoint at composite boundary by default.

---

## 38. Compile-time validation

* Validate branch group name:

  * non-empty
  * unique
  * path-safe
* Validate branch names:

  * non-empty
  * unique within group
  * path-safe
* Validate `parallel(...)`:

  * non-empty branch mapping
  * supported branch declarations
  * no child workflow branch step in v1
  * no scoped branch step in v1
  * no operation branch step unless explicitly async-safe
* Validate `fan_out(...)`:

  * one supported branch step
  * non-empty branch mapping
  * JSON-serializable branch inputs
  * no child workflow branch step in v1
  * no scoped branch step in v1
  * no operation branch step unless explicitly async-safe
* Validate provider-backed branch sessions:

  * explicit session exists
  * session continuity is fresh
  * explicit verifier session is fresh
* Validate fan-in:

  * supported fan-in step kind
  * no ambiguous external route declarations
  * helper reads only used in fan-in
  * no scoped fan-in step in v1 unless explicitly supported
* Do not validate provider async support at branch-group runtime; async support is the provider contract.

---

## 39. Worklist and scoped-step boundary

* V1 does not support worklist-derived fan-out.
* V1 does not support scoped branch steps.
* Existing scoped worklist execution remains non-parallel.
* Future worklist fan-out may:

  * snapshot selected worklist items
  * derive branch names from item ids
  * pass item payload as branch input
  * avoid implicit cursor advancement

---

## 40. Child workflow boundary

* V1 disallows child workflow steps as branch steps.
* Child workflow fan-in is vFuture unless explicitly redesigned.
* Reasons:

  * nested checkpointing complexity
  * recursive session validation complexity
  * child terminal mapping complexity
  * branch-specific resume complexity

---

## 41. Operation branch boundary

* V1 should reject operation branch steps unless async-safe operation runtime binding is explicitly implemented.
* If operation branches are later allowed:

  * branch operation runtime must be active inside each async branch task
  * branch operation runtime must include branch execution id
  * no thread-local assumptions are allowed
* Plain Python branch steps may be allowed.
* Python branch steps with `scope` remain rejected.

---

## 42. Compile cache

* Compile cache key must include branch-group internals:

  * group name
  * kind
  * concurrency
  * settle
  * success routes
  * outcome policy identifier
  * branch names
  * branch inputs
  * branch step topology
  * fan-in step topology
  * exposed route tags
* If comprehensive support is too risky for v1:

  * bypass compile cache for workflows containing branch groups

---

## 43. Required module boundaries

* Recommended branch-group modules:

  * `autoloop/core/branch_groups/models.py`
  * `autoloop/core/branch_groups/declarations.py`
  * `autoloop/core/branch_groups/validation.py`
  * `autoloop/core/branch_groups/lowering.py`
  * `autoloop/core/branch_groups/runtime.py`
  * `autoloop/core/branch_groups/context.py`
  * `autoloop/core/branch_groups/sessions.py`
  * `autoloop/core/branch_groups/manifest.py`
  * `autoloop/core/branch_groups/outcomes.py`
  * `autoloop/core/branch_groups/static_graph.py`
  * `autoloop/core/branch_groups/scheduler.py`
* Minimal edits to existing modules:

  * `simple.py`: export `parallel`, `fan_out`, `FanIn`
  * `steps.py`: add branch-group/composite step declaration
  * `discovery.py`: discover/lower branch groups
  * `compiler.py`: compile branch-group metadata
  * `context.py`: add state cell and branch/fan-in metadata
  * `artifacts.py`: support branch/fan-in placeholders and correct templated rooting
  * `engine_collaborators.py`: async step dispatch and capture mode
  * `engine.py`: minimal collaborator wiring

---

## 44. Observability events

* Runtime should emit:

  * `branch_group_started`
  * `branch_scheduled`
  * `branch_started`
  * `branch_completed`
  * `branch_failed`
  * `branch_needs_input`
  * `branch_cancelled`
  * `branch_skipped`
  * `branch_manifest_written`
  * `fan_in_started`
  * `fan_in_completed`
  * `branch_group_completed`
* Event payload should include:

  * group name
  * group kind
  * branch name when applicable
  * branch index when applicable
  * step name
  * execution id
  * status
  * route
  * destination
  * error summary
  * artifact paths

---

## 45. Static graph

* Branch group appears as one composite node.
* Composite node includes nested metadata:

  * group name
  * kind
  * branch names
  * branch step names
  * fan-in step name, if present
  * exposed routes
* Branch internals are inspectable.
* Branch internals are not top-level workflow cursor nodes.

---

## 46. Checkpoint and resume

* V1 checkpoints at composite boundary.
* V1 may rerun full branch group if interrupted during branch execution.
* V1 does not require partial branch resume.
* V1 does not require branch-specific pending-input resume.
* If fan-in asks a question:

  * normal checkpoint/resume applies at fan-in/composite level.
* If branch asks a question with fan-in:

  * it is captured in the manifest.
  * fan-in may ask a consolidated question.
* If branch asks a question without fan-in:

  * composite may route to `question`.
  * normal checkpoint applies at the composite route.
* vFuture may add:

  * partial branch replay
  * branch-level checkpointing
  * branch-specific interactive resume

---

## 47. Strictness tests

* Tests must fail if provider or branch-group runtime paths import/use:

  * `concurrent.futures`
  * `ThreadPoolExecutor`
  * `Future`
  * `FIRST_COMPLETED`
  * `threading.RLock`
  * `asyncio.to_thread`
  * `subprocess.run` in provider transports
* Tests must fail if provider protocols expose sync provider methods.
* Tests must fail if provider transports expose sync transport methods.
* Tests must fail if provider wrappers implement async methods by calling sync methods.
* Tests must fail if branch groups contain async support probing helpers.
* Tests must fail if provider-backed branch execution can reach a sync provider path.

---

## 48. Runtime tests

* Async fake provider with `parallel(..., concurrency>1)` runs branches concurrently.
* Async fake provider with `fan_out(..., concurrency>1)` runs branches concurrently.
* Branch result order follows declaration order.
* Branch route destination is not followed.
* Branch `on_taken` hook is not run in capture mode.
* Fan-in route finalizes exactly once.
* Branch `RequestInput` becomes `needs_input` when fan-in exists.
* Branch `RequestInput` routes composite to `question` when fan-in is absent.
* Branch `Goto` is captured and not followed.
* Branch `Fail` is captured as failed.
* Same-file writes from multiple branches are not rejected.
* Branch state assignment updates shared state cell.
* Branch values mutation updates shared values mapping.
* Branch sessions do not activate parent session slots.
* Two branches using the same `Session.fresh()` declaration get distinct provider contexts.
* Provider receives `session_id=None` on first branch turn.
* Provider-returned session id appears in branch result.
* Manifest is deterministic.
* Context markdown is deterministic.
* Fan-in does not run if `results.json` write fails.
* Fan-in does not run if `context.md` write fails.
* Branch evidence path is under `workflow_folder`.

---

## 49. Compile-time tests

* Missing provider branch session fails.
* Non-fresh provider branch session fails.
* Explicit fresh provider branch session passes.
* Produce/verify branch with non-fresh verifier session fails.
* Child workflow branch step fails.
* Scoped branch step fails.
* Operation branch step fails unless explicitly async-safe.
* Branch placeholder outside branch fails.
* Fan-in placeholder outside fan-in fails.
* `FanIn.results()` outside fan-in fails.
* `FanIn.context()` outside fan-in fails.
* Unsafe group name fails.
* Unsafe branch name fails.
* Branch-group internals affect compile cache key or compile cache is bypassed.

---

## 50. Provider tests

* Codex transport uses `asyncio.create_subprocess_exec`.
* Claude transport uses `asyncio.create_subprocess_exec`.
* Provider transport cancellation terminates subprocesses where possible.
* Provider transport does not call `subprocess.run`.
* Provider transport does not use threads.
* Rendered provider awaits transport.
* Rendered provider has no sync provider methods.
* Fake provider is async-native.
* Fake provider does not wrap sync provider methods.

---

## 51. Recommended implementation order

* **Phase 1**

  * Preserve public workflow authoring API.
  * Add `Engine.run_async(...)`.
  * Keep public `Engine.run(...)` as outer wrapper only.
* **Phase 2**

  * Remove sync provider protocols.
  * Remove sync transport protocols.
  * Remove async capability probing helpers.
  * Remove dual sync/async provider method families.
* **Phase 3**

  * Introduce async-only provider and transport protocols with clean method names.
* **Phase 4**

  * Convert fake provider to async-native.
* **Phase 5**

  * Convert Codex transport to async subprocess execution.
* **Phase 6**

  * Convert Claude transport to async subprocess execution.
* **Phase 7**

  * Make step dispatcher async-first.
  * Add capture route mode.
* **Phase 8**

  * Simplify BranchGroupRuntime so it simply awaits provider-backed branch execution.
  * Remove async-support checks.
* **Phase 9**

  * Complete branch-local session behavior.
  * Remove synthetic session ids.
* **Phase 10**

  * Complete manifest/context/fan-in behavior.
* **Phase 11**

  * Add strictness, provider, compile-time, and runtime test suites.

---

## 52. Final merge gate

* Public non-parallel authoring API remains stable.
* Public ordinary runtime entrypoint remains available, if currently public.
* Provider protocol is async-only.
* Transport protocol is async-only.
* Rendered provider is async-only.
* Built-in provider transports are async-native.
* Branch groups do not check whether providers support async.
* Branch groups simply await the async provider contract.
* No sync provider compatibility exists in branch-group execution.
* No thread-backed fallback exists.
* No fake async wrappers around sync provider methods exist.
* No synthetic provider session ids exist.
* Fresh sessions are branch-execution-local.
* Branch route destinations are captured, not followed.
* Branch route `on_taken` hooks do not run in v1.
* Fan-in route finalizes exactly once.
* Branch evidence is written under `workflow_folder`.
* Full strictness, compile-time, runtime, and provider test suites pass.
