## Full revised standalone spec: Autoloop v3 explicit branch groups, asyncio-only v1

* **Project stance**

  * Treat this as a greenfield implementation.
  * Do not add complexity to preserve legacy compatibility.
  * Do not add compatibility shims for old sync execution paths.
  * Do not keep sync provider support inside branch groups.
  * Do not support thread-backed fallback behavior.
  * Do not preserve old behavior if it conflicts with the clean branch-group design.
  * Prefer a smaller, correct, async-native implementation over a broader compatibility layer.
  * If an existing API shape makes branch groups harder or less correct, change the API rather than adding adapters around it.
  * Sync-only providers are not branch-group-compatible in v1.
  * Legacy top-level synchronous execution may exist elsewhere, but branch groups should not contort around it.

* **Purpose**

  * Add explicit concurrent execution to Autoloop v3.
  * Preserve Autoloop’s author-responsibility model.
  * Support concurrent branch execution without automatic dependency scheduling.
  * Support two branch-group primitives:

    * `parallel(...)`: run different authored steps concurrently.
    * `fan_out(...)`: run the same authored step multiple times concurrently with different branch inputs.
  * Support optional authored `fan_in` on both `parallel(...)` and `fan_out(...)`.
  * Treat `fan_in` as a normal authored step, usually LLM-capable, that interprets branch results.
  * Avoid framework-owned state merge semantics.
  * Avoid framework-owned workspace conflict semantics.
  * Avoid provider-session sharing inside branch execution until provider session forking is reliable.
  * Keep `engine.py` focused on the top-level workflow cursor by implementing branch groups in a dedicated subsystem.
  * This spec supersedes the reviewed implementation direction in the uploaded patch. 

* **Core model**

  * A branch group is a composite barrier step.
  * A branch group is explicit in the workflow definition.
  * A branch group externally behaves like one workflow step.
  * A branch group internally schedules multiple branch executions.
  * A branch executes exactly one branch step.
  * A branch records the branch step’s route/result.
  * A branch does not follow its route destination in the parent workflow graph.
  * The parent workflow cursor remains on the composite branch-group step until the branch group resolves.
  * If `fan_in` exists, the branch group resolves through the `fan_in` route.
  * If `fan_in` does not exist, the branch group resolves through a mechanical outcome policy.
  * Branches share parent workflow state by default.
  * Branches share the workspace by default.
  * Branches share `ctx.values` by default.
  * Branches may mutate parent workflow state.
  * Branches may write any workspace path.
  * Branches may intentionally write overlapping paths.
  * The framework does not infer, restrict, or merge shared state/workspace effects.

* **Non-goals for v1**

  * No automatic DAG scheduler.
  * No inferred parallelism from `reads`, `requires`, `writes`, prompt placeholders, routes, or artifact declarations.
  * No dependency-graph-based parallel execution.
  * No mandatory workspace isolation.
  * No branch-local workspace overlays.
  * No workspace conflict detection.
  * No workspace conflict failure.
  * No automatic artifact merge.
  * No state ownership declarations.
  * No automatic state merge.
  * No implicit fresh provider sessions.
  * No shared provider sessions inside branch execution.
  * No provider session forking.
  * No child workflow branch steps.
  * No child workflow fan-in in v1 unless explicitly redesigned later.
  * No worklist-derived fan-out.
  * No branch-specific interactive resume.
  * No implicit concurrent execution for existing scoped worklist steps.
  * No large branch-group implementation inside `engine.py`.
  * No sync provider fallback.
  * No thread-backed fallback.
  * No compatibility shims for legacy sync branch execution.

* **Asyncio-only execution invariant**

  * Branch-group v1 is asyncio-only.
  * Branch scheduling must use `asyncio.Task`.
  * Branch concurrency must use `asyncio.Semaphore`.
  * Branch cancellation must use task cancellation.
  * No branch work may be offloaded to OS threads.
  * Forbidden imports/usages in branch-group implementation:

    * `ThreadPoolExecutor`
    * `Future`
    * `concurrent.futures.wait`
    * `FIRST_COMPLETED`
    * `threading.RLock`
    * `asyncio.to_thread`
  * Sync providers are not supported for concurrent branch groups.
  * Since this is greenfield, do not support sync-only provider compatibility inside branch groups.
  * Provider-backed branch execution requires native async provider methods.
  * If an async provider is unavailable, branch-group compilation or runtime initialization must fail clearly.
  * Do not silently degrade to sync execution.
  * Do not silently degrade to sequential execution unless the branch group is explicitly configured as non-provider Python-only and the runtime remains async-native.

* **Phase-zero compatibility rule**

  * Until async step execution and async provider methods exist, branch groups may be implemented only as a compile-time/lowering/static-graph feature or as explicitly sequential non-provider execution.
  * Provider-backed branch groups must fail if async provider execution is unavailable.
  * Do not implement fake async behavior by blocking the event loop.
  * Do not implement fake async behavior with threads.
  * If real async branch execution is not ready, fail early rather than adding legacy compatibility.

* **Terminology**

  * **Branch group**

    * Composite execution unit created by `parallel(...)` or `fan_out(...)`.
    * Has a deterministic group name.
    * Has one or more named branches.
    * Produces a branch manifest.
    * Produces a branch group context document.
  * **Branch**

    * One named execution inside a branch group.
    * Has a branch name, branch index, branch input, and branch result.
  * **Branch step**

    * The authored step executed by a branch.
    * In `parallel(...)`, different branches may use different branch steps.
    * In `fan_out(...)`, all branches use the same branch step.
  * **Branch result**

    * Structured record of one branch execution.
  * **Branch manifest**

    * Machine-readable JSON artifact containing all branch results.
  * **Branch group context document**

    * LLM-readable markdown artifact summarizing branch results.
    * Distinct from `ctx.branch`.
  * **Fan-in**

    * Optional authored post-barrier step.
    * Consumes branch manifest/context.
    * Produces synthesis, decision artifacts, and route.
  * **Composite route**

    * Parent-visible route of the branch group.
    * Comes from fan-in when fan-in exists.
    * Comes from outcome policy when fan-in is absent.

* **Branch group naming**

  * Branch group name must be deterministic.
  * Branch group name must be unique within the workflow.
  * Branch group name must be non-empty.
  * Branch group name must be path-safe in v1.
  * Branch names must be unique within the group.
  * Branch names must be non-empty.
  * Branch names must be path-safe in v1.
  * V1 should reject unsafe group or branch names rather than silently slugifying them.
  * Suggested allowed name policy:

    * alphanumerics are allowed;
    * `_`, `-`, and `.` are allowed;
    * path separators are not allowed;
    * empty names are not allowed;
    * names resolving to `.` or `..` are not allowed.

* **Primitive: `parallel(...)`**

  * Purpose:

    * Run multiple distinct authored steps concurrently.
  * Required input:

    * `branches`: non-empty mapping from branch name to step declaration.
  * Optional inputs:

    * `concurrency`
    * `settle`
    * `fan_in`
    * `outcome`, only when `fan_in` is absent
    * `success_routes`, only when mechanical outcome needs route interpretation
    * `routes`, only when `fan_in` is absent and outcome routes need explicit destinations
  * Branch behavior:

    * Each branch executes its branch step exactly once.
    * Each branch records its route/result.
    * Branch route destinations are not followed.
  * Composite behavior:

    * Writes branch manifest.
    * Writes branch group context document.
    * Runs optional fan-in.
    * Resolves through fan-in route or mechanical outcome route.

* **Primitive: `fan_out(...)`**

  * Purpose:

    * Execute the same authored step multiple times concurrently under different branch inputs.
  * Required input:

    * `step`: one authored step declaration.
    * `branches`: non-empty mapping from branch name to branch input.
  * Optional inputs:

    * `concurrency`
    * `settle`
    * `fan_in`
    * `outcome`, only when `fan_in` is absent
    * `success_routes`, only when mechanical outcome needs route interpretation
    * `routes`, only when `fan_in` is absent and outcome routes need explicit destinations
  * Branch behavior:

    * Each branch executes the same branch step exactly once.
    * Each branch receives branch metadata.
    * Each branch receives branch input.
    * Each branch records its route/result.
    * Branch route destinations are not followed.
  * Branch input:

    * Must be serializable into the branch manifest.
    * Should be JSON-serializable in v1.
  * Composite behavior:

    * Writes branch manifest.
    * Writes branch group context document.
    * Runs optional fan-in.
    * Resolves through fan-in route or mechanical outcome route.

* **Primitive: `fan_in`**

  * `fan_in` is optional.
  * `fan_in` is available on `parallel(...)`.
  * `fan_in` is available on `fan_out(...)`.
  * `fan_in` is a normal authored step.
  * `fan_in` may be LLM-based.
  * `fan_in` may be produce/verify-based.
  * `fan_in` may be Python-based.
  * Child workflow `fan_in` is vFuture unless explicitly redesigned.
  * `fan_in` runs after branch settlement.
  * `fan_in` receives branch manifest and branch group context document.
  * `fan_in` may read any workspace path.
  * `fan_in` may write any artifacts.
  * `fan_in` may mutate parent workflow state.
  * `fan_in` may use any session declared by the author.
  * `fan_in` does not require `Session.fresh()` merely because it is a fan-in step.
  * `fan_in` is not a framework merge policy.
  * `fan_in` is not a state reconciler.
  * `fan_in` is not a workspace conflict resolver.
  * `fan_in` is authored interpretation.

* **When `fan_in` exists**

  * Branches settle according to `settle`.
  * Runtime writes branch manifest.
  * Runtime writes branch group context document.
  * Runtime executes the fan-in step.
  * Composite branch-group route equals the fan-in route.
  * Composite branch-group external routes are exactly the fan-in step’s authored routes.
  * Branch failures are recorded and passed to fan-in.
  * Branch questions are recorded and passed to fan-in.
  * Branch cancellations are recorded and passed to fan-in.
  * Fan-in decides whether to continue, fail, rework, recover, or ask the user.
  * Branch group must not separately declare conflicting external routes.
  * If branch manifest writing fails, fan-in must not run.
  * If branch group context document writing fails, fan-in must not run.
  * Manifest/context write failure fails the branch group with a runtime error before fan-in.

* **When `fan_in` is absent**

  * Branches settle according to `settle`.
  * Runtime writes branch manifest.
  * Runtime writes branch group context document.
  * Runtime applies mechanical outcome policy.
  * Composite branch-group route equals the outcome-policy route.
  * External routes are the outcome-policy routes.
  * Downstream ordinary steps may read branch manifest/context and branch artifacts.
  * If branch manifest writing fails, the branch group fails before outcome routing.
  * If branch group context document writing fails, the branch group fails before outcome routing.

* **Valid reasons to omit `fan_in`**

  * Branches write independent artifacts.
  * A later ordinary step will synthesize results.
  * Branches directly mutate shared parent state.
  * Branches perform side effects only.
  * The branch group is only a barrier.
  * A mechanical route is sufficient.
  * The author wants branch traces without immediate synthesis.

* **Session ownership**

  * Steps own sessions.
  * Branch groups do not own sessions.
  * `parallel(...)` must not accept `session=...`.
  * `parallel(...)` must not accept `session_mode=...`.
  * `parallel(...)` must not accept `shared_session=...`.
  * `parallel(...)` must not accept `fork_session=...`.
  * `fan_out(...)` must not accept `session=...`.
  * `fan_out(...)` must not accept `session_mode=...`.
  * `fan_out(...)` must not accept `shared_session=...`.
  * `fan_out(...)` must not accept `fork_session=...`.
  * Future provider forking must be modeled through `Session` / `Continuity`, not through branch-group options.

* **Provider-backed branch session rule**

  * Provider-backed branch steps must explicitly declare fresh sessions in v1.
  * Missing session is invalid.
  * Non-fresh session is invalid.
  * Compiler must not inject fresh sessions.
  * Compiler must not treat omitted session as fresh.
  * Compiler must validate authored declarations before default-session lowering.
  * A compiled `session_name` is not enough to prove explicit freshness.
  * Fresh branch sessions are fresh per branch execution, not merely fresh per session slot.
  * Two branches using the same `Session.fresh()` declaration must not share provider context.
  * Two executions of the same `fan_out(...)` step using the same `Session.fresh()` declaration must not share provider context.

* **Provider-backed step classification**

  * Provider-backed branch steps:

    * LLM/prompt steps.
    * produce/verify steps.
  * Non-provider branch steps:

    * Python steps.
  * Disallowed as branch steps in v1:

    * child workflow steps.
    * scoped/worklist steps.
    * provider-backed operation steps without async-safe operation runtime.
  * Allowed as fan-in steps in v1:

    * LLM/prompt steps.
    * produce/verify steps.
    * Python steps.
  * Child workflow fan-in is vFuture unless explicitly redesigned.

* **Prompt/LLM branch session rule**

  * A prompt/LLM branch step must declare:

    * `session=Session.fresh()`
  * A prompt/LLM branch step with no explicit session is a compiler error.
  * A prompt/LLM branch step with `Session.run()`, `Session.task()`, `Session.work_item()`, or custom non-fresh continuity is a compiler error.
  * A prompt/LLM branch step requires an async provider execution path.

* **Produce/verify branch session rule**

  * Producer session must be explicitly fresh.
  * If `verifier_session` is omitted:

    * verifier uses the fresh producer session selected for that branch execution.
  * If `verifier_session` is explicit:

    * it must also be explicitly fresh.
  * Producer and verifier may share the same explicit fresh session.
  * Producer and verifier may use separate explicit fresh sessions.
  * If producer and verifier share a fresh session declaration, that session is still branch-execution-local.
  * Produce/verify branch execution requires async producer/verifier provider methods.

* **Branch-local provider session activation**

  * Fresh provider sessions created inside branches are branch-local bindings.
  * Branch-local provider sessions must not nondeterministically replace the parent active session for the same slot.
  * Branch-local provider sessions must be recorded in branch traces and branch results only when real provider session ids exist.
  * Fan-in starts from normal parent session semantics.
  * Fan-in must not accidentally inherit “last completed branch session wins.”
  * Branch-local session overlay must not activate branch sessions in the parent store.
  * Parent session store activation must remain deterministic after branch group completion.

* **No synthetic provider session IDs**

  * `BranchSessionStoreView.open(...)` must not fabricate `session_id`.
  * A fresh branch session binding may have:

    * a fresh branch-local `SessionKey`;
    * `session_id=None` until the provider returns a real provider session id.
  * Provider adapters must interpret `session_id=None` as “start fresh.”
  * Branch-local session overlay must persist real returned provider bindings.
  * A test provider must receive `session_id=None` on the first turn for a fresh branch session.
  * Branch result may record a provider session only after the provider returns one.

* **BranchSessionStoreView key semantics**

  * Branch-local fresh session keys must include branch execution identity.
  * Conceptual fresh branch key:

    * `slot=<session slot>`
    * `domain="fresh"`
    * `value=<group>:<branch>:<index>:<unique-token>`
  * Do not use `domain="run"` for branch fresh session creation.
  * `get(...)` should prefer branch-local bindings.
  * Parent binding lookup should be avoided for provider-backed fresh branch sessions.
  * Since provider-backed branch steps are required to be fresh in v1, branch provider session lookup should not fall back to parent active sessions.

* **Compiler errors for session violations**

  * Missing branch session:

    * `branch group '<group>' includes provider-backed branch step '<step>' without explicit session=Session.fresh().`
  * Non-fresh branch session:

    * `branch group '<group>' includes provider-backed branch step '<step>' with non-fresh session continuity '<kind>'.`
  * Non-fresh verifier session:

    * `branch group '<group>' includes produce/verify branch step '<step>' with non-fresh verifier_session continuity '<kind>'.`
  * Sync-only provider for concurrency:

    * `branch group '<group>' requires async provider execution for concurrency=<n>, but provider '<provider>' is sync-only.`
  * Child workflow branch step:

    * `branch group '<group>' includes child workflow branch step '<step>', which is unsupported in v1.`
  * Scoped branch step:

    * `branch group '<group>' includes scoped branch step '<step>', which is unsupported in v1.`

* **Future provider session forking**

  * Future support may add:

    * `Session.fork(parent_session)`
    * `Continuity.fork_parent(parent_session)`
    * `Continuity.branch()`
  * Provider adapter must decide whether requested continuity is supported.
  * If unsupported:

    * fail clearly; or
    * use explicit author-declared fallback.
  * No hidden fallback from forked session to shared session.
  * No hidden fallback from forked session to fresh session.
  * No hidden fallback from omitted session to fresh session.

* **Workspace semantics**

  * Branches share the parent workspace by default.
  * Branches may read any path normal step execution could read.
  * Branches may write any path normal step execution could write.
  * Branches may write overlapping files.
  * Branches may intentionally append to the same file.
  * Branches may intentionally overwrite the same file.
  * The framework does not block writes.
  * The framework does not sandbox writes.
  * The framework does not infer workspace conflicts.
  * The framework does not fail on workspace conflicts.
  * The framework does not choose file winners.
  * The framework does not merge files.
  * Filesystem synchronization is author responsibility.
  * Optional future diagnostics may trace declared artifact writes.
  * Optional future diagnostics may warn on declared write overlap.
  * Optional future workspace overlays may exist only as explicit opt-in features.

* **Runtime-owned branch group namespace**

  * `_branch_groups` is runtime-owned.
  * Runtime writes branch evidence under:

    * `{workflow_folder}/_branch_groups/<group_name>/...`
  * User-declared artifacts may technically write under `_branch_groups`, because v1 does not restrict writes.
  * User writes under `_branch_groups` are discouraged.
  * User writes under `_branch_groups` may overwrite runtime evidence.
  * V1 should not prevent such writes.
  * Diagnostics may warn when declared user artifacts target `_branch_groups`.

* **Parent workflow state semantics**

  * Branches share parent workflow state by default.
  * Branches may read `ctx.state`.
  * Branches may assign `ctx.state`.
  * Branches may mutate fields on `ctx.state`.
  * Branches may perform read-modify-write state updates.
  * The framework does not block parent state mutation.
  * The framework does not isolate branch state by default.
  * The framework does not merge branch state.
  * The framework does not detect state conflicts.
  * The framework does not require state ownership declarations.
  * Final parent state after branch group completion is the final value in the shared state cell.
  * Last actual write wins unless the author synchronizes.
  * Shared state mutation is intentionally nondeterministic under cooperative interleaving.
  * Authors needing deterministic aggregation should prefer branch artifacts plus fan-in.

* **Shared state cell**

  * Branch contexts must share one state cell.
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
  * `Context.state` setter increments `StateCell.version`.
  * `context_runtime(...).set_state(...)` must update the same state cell.
  * Hook state updates must update the same state cell.
  * Provider execution state updates must update the same state cell.
  * State cell version is diagnostic only.
  * State cell version does not imply conflict detection.
  * No thread locks in `StateCell`.

* **Shared values semantics**

  * `ctx.values` is shared within a branch group in v1.
  * Branch contexts receive the same mutable values mapping.
  * Branches may mutate shared values.
  * The framework does not merge values.
  * The framework does not detect values conflicts.
  * Last actual mutation wins unless the author synchronizes.
  * Shared values mutation is intentionally nondeterministic under cooperative interleaving.
  * Authors needing deterministic aggregation should prefer branch artifacts plus fan-in.
  * No `SynchronizedValuesDict`.
  * No thread locks around values.

* **Runtime bookkeeping semantics**

  * Workflow state is shared.
  * Workspace is shared.
  * Values are shared.
  * Runtime-owned step bookkeeping is branch-scoped.
  * Branch-scoped bookkeeping includes:

    * visits;
    * last route;
    * last reason;
    * retry counters;
    * rework counters;
    * replan counters;
    * branch execution id;
    * item-state bookkeeping, where applicable.
  * Runtime bookkeeping key should include:

    * branch group name;
    * branch name;
    * step name;
    * visit.
  * Suggested execution id:

    * `<group_name>:<branch_name>:<step_name>:<visit>`
  * Runtime bookkeeping must not race through a single shared per-step store during `fan_out(...)`.

* **Branch metadata**

  * Branch contexts expose `ctx.branch`.
  * `ctx.branch` is available only during branch execution.
  * `ctx.branch` fields:

    * `name`
    * `index`
    * `group`
    * `input`
    * `count`
  * For `parallel(...)`:

    * `ctx.branch.input` defaults to `{}` in v1.
  * For `fan_out(...)`:

    * `ctx.branch.input` is the branch payload.
  * Branch metadata is read-only from the framework’s perspective.
  * Authors may copy branch metadata into state or artifacts.

* **Fan-in metadata**

  * Fan-in contexts expose `ctx.fan_in`.
  * `ctx.fan_in` is available only during fan-in execution.
  * Exact fields:

    * `ctx.fan_in.results`: parsed branch manifest object.
    * `ctx.fan_in.results_path`: path to `results.json`.
    * `ctx.fan_in.context_path`: path to `context.md`.
    * `ctx.fan_in.context_text`: markdown text from `context.md`.
    * `ctx.fan_in.branch_count`: number of branches.
    * `ctx.fan_in.completed_count`: number of completed branches.
    * `ctx.fan_in.failed_count`: number of failed branches.
    * `ctx.fan_in.needs_input_count`: number of branches needing input.
    * `ctx.fan_in.cancelled_count`: number of cancelled branches.
  * Avoid ambiguous names such as `results_json` unless they have one exact meaning.
  * Fan-in context does not expose a single active `ctx.branch`.

* **Branch placeholders**

  * Valid in branch step prompts and branch step artifact templates:

    * `{branch.name}`
    * `{branch.index}`
    * `{branch.group}`
    * `{branch.count}`
    * `{branch.input.<field>}`
  * Invalid outside branch steps.
  * Compiler must reject invalid branch placeholder usage.
  * Placeholder validation must compare root token exactly:

    * valid root is exactly `branch`.
  * Do not use `startswith("branch")`.

* **Fan-in placeholders**

  * Valid in fan-in step prompts and fan-in step artifact templates:

    * `{fan_in.results_path}`
    * `{fan_in.context_path}`
    * `{fan_in.context_text}`
    * `{fan_in.branch_count}`
    * `{fan_in.completed_count}`
    * `{fan_in.failed_count}`
    * `{fan_in.needs_input_count}`
    * `{fan_in.cancelled_count}`
  * Invalid outside fan-in steps.
  * Compiler must reject invalid fan-in placeholder usage.
  * Placeholder validation must compare root token exactly:

    * valid root is exactly `fan_in`.
  * Do not use `startswith("fan_in")`.

* **Placeholder implementation requirements**

  * Branch and fan-in roots must be supported in:

    * simple prompt reference validation;
    * runtime template resolution;
    * artifact template rendering;
    * prompt rendering;
    * context namespace access.
  * Compile-time validation and runtime rendering must agree.
  * Invalid placeholders should fail early with actionable errors.

* **Templated artifact path rooting**

  * Templated relative artifact paths must remain rooted like normal step-owned artifacts.
  * A branch artifact template such as `assessments/{branch.name}.json` must not accidentally resolve relative to process working directory.
  * If the artifact has an owning step, relative templated paths should resolve under the normal step/workflow artifact root for that owner.
  * Implementation must ensure templated and non-templated step artifacts use consistent rooting semantics.
  * This may require updating artifact template resolution.

* **Branch group artifact paths**

  * Every branch group writes:

    * `{workflow_folder}/_branch_groups/<group_name>/results.json`
    * `{workflow_folder}/_branch_groups/<group_name>/context.md`
  * Per-branch raw output should be stored or referenced under:

    * `{workflow_folder}/_branch_groups/<group_name>/branches/<branch_name>/...`
  * Exact raw output file names may vary by step/provider kind.
  * Manifest must record raw output paths when available.
  * Branch group artifacts are written whether or not fan-in exists.
  * Branch group artifacts are available to fan-in.
  * Branch group artifacts are available to downstream steps.

* **Branch manifest schema**

  * Schema id:

    * `autoloop.branch_results/v1`
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
    * `reason`
    * `question`
    * `artifacts`
    * `raw_output_path`
    * `provider_session`
    * `provider_sessions`
    * `error`
    * `started_at`
    * `finished_at`
    * `duration_ms`
    * `usage`
  * Branch `status` values:

    * `completed`
    * `failed`
    * `needs_input`
    * `cancelled`
    * `skipped`
  * Branch artifact fields:

    * `name`
    * `path`
    * `kind`
    * `exists`
    * `validation`
    * `validation_errors`
  * Branch error fields:

    * `type`
    * `message`
    * `failure_context`
    * `retry_kind`
    * `retry_exhausted`
  * `route` may be `null` if no route was produced.
  * `destination` records a route destination or direct-control target when available, but it is not followed.
  * `question` may be `null`.
  * `provider_session` may be `null`.
  * `provider_sessions` may be empty.
  * `usage` may be empty.

* **Branch group context markdown**

  * File:

    * `{workflow_folder}/_branch_groups/<group_name>/context.md`
  * Purpose:

    * provide deterministic LLM-readable summary for fan-in and downstream review.
  * Must include:

    * branch group name;
    * branch group kind;
    * branch count;
    * settlement policy;
    * success route policy;
    * completion summary;
    * route summary;
    * failure summary;
    * needs-input summary;
    * cancellation summary;
    * per-branch input;
    * per-branch status;
    * per-branch route;
    * per-branch reason;
    * per-branch question;
    * per-branch artifact paths;
    * per-branch error summary;
    * raw output paths.
  * Should include bounded artifact excerpts when safe and useful.
  * Should not include full raw logs by default.
  * Should not embed huge artifacts by default.
  * Should reference large content by path.
  * Branch order must follow declaration order.

* **Fan-in helper reads**

  * Provide:

    * `FanIn.results()`
    * `FanIn.context()`
  * `FanIn.results()` resolves to:

    * `{workflow_folder}/_branch_groups/<group_name>/results.json`
  * `FanIn.context()` resolves to:

    * `{workflow_folder}/_branch_groups/<group_name>/context.md`
  * Helpers are valid only in fan-in steps.
  * Compiler rejects helper usage outside fan-in steps.
  * V1 does not need `FanIn.artifacts()`.
  * Fan-in can discover artifact paths from the manifest.
  * Helper references should resolve through runtime-owned reference handling or absolute paths to avoid rooting ambiguity.

* **Settlement policy**

  * `settle` controls branch scheduling/settlement.
  * Supported v1 values:

    * `all`
    * `fail_fast`
  * Default:

    * `settle="all"`
  * `settle="all"`:

    * schedules all branches subject to concurrency;
    * waits for every branch to produce a branch result;
    * records completed, failed, needs-input, cancelled, and skipped branches.
  * `settle="fail_fast"`:

    * stops scheduling new branches after first hard failure;
    * cancels already-created pending/running tasks when possible;
    * records cancelled/skipped branches;
    * then proceeds according to fan-in or outcome policy.
  * `quorum` is vFuture.
  * Cancellation is best-effort.
  * Async provider adapters should terminate subprocesses on cancellation where possible.
  * If provider subprocess cancellation is unsupported:

    * record `cancellation_supported=False`;
    * still produce a valid manifest.

* **Concurrency**

  * `concurrency` limits simultaneous branch executions.
  * `concurrency` must be positive if provided.
  * If omitted, recommended behavior is to schedule all branches concurrently.
  * Runtime may enforce a global maximum concurrency.
  * `concurrency=1` is valid.
  * With `concurrency=1`, branch group still uses branch-group semantics.
  * Branch result order in manifest must follow declaration order, not completion order.
  * Scheduling should be deterministic where practical.
  * Provider-backed `concurrency>1` requires native async provider support.

* **Branch success semantics**

  * Branch completion is not the same as branch success.
  * Branch steps can have arbitrary route tags.
  * Mechanical outcome policies need a success predicate.
  * Branch groups without fan-in must define or inherit `success_routes`.
  * Recommended default:

    * `success_routes=("done", "accepted")`
  * Authors may override:

    * `success_routes=("approved", "ready")`
  * A branch with `status="completed"` and route in `success_routes` is successful.
  * A branch with `status="completed"` but route outside `success_routes` is completed but not successful for mechanical outcome purposes.
  * Custom outcome aggregators may define their own success semantics.
  * When fan-in exists, `success_routes` is useful for manifest/context summaries but does not determine the composite route.

* **Outcome policy without fan-in**

  * If fan-in is absent, outcome policy chooses composite route.
  * Supported v1 built-ins:

    * `all_done`
    * `all_settled`
    * `any_done`
    * custom aggregator
  * Recommended default:

    * `outcome="all_done"`
  * Built-in external route tags:

    * `done`
    * `partial`
    * `failed`
    * `question`
  * `all_done`:

    * route `done` if every branch is successful;
    * route `question` if any branch needs input;
    * route `partial` if some branches settled but not all are successful;
    * route `failed` only for hard group failure.
  * `all_settled`:

    * route `done` if all branches reached any terminal branch result and none need input or failed hard;
    * route `question` if any branch needs input;
    * route `partial` if any branch failed/cancelled/non-success.
  * `any_done`:

    * route `done` if at least one branch is successful;
    * route `question` if no branch is successful and any branch needs input;
    * route `partial` or `failed` according to failures.
  * Custom aggregator:

    * receives manifest and current context;
    * returns an `Event`;
    * must return a legal composite route.

* **Outcome behavior with fan-in**

  * If fan-in exists:

    * built-in outcome policy is not used for external route selection.
    * fan-in route is the composite route.
    * fan-in sees all branch results.
    * fan-in decides how to handle failures, questions, cancellations, and non-success routes.
  * Fan-in may route to:

    * success path;
    * rework path;
    * recovery path;
    * question path;
    * fail path.

* **Branch-level questions**

  * With fan-in:

    * branch question becomes `status="needs_input"`;
    * branch question text is recorded in manifest;
    * branch question text is included in context markdown;
    * fan-in decides whether to ask the user.
  * Without fan-in:

    * if any branch needs input, default composite route is `question`;
    * composite question is a deterministic summary of branch questions.
  * V1 does not resume an individual branch from its own question.
  * V1 does not pause the parent workflow directly from a branch question when fan-in exists.

* **Branch failures**

  * Branch failures are recorded when settlement policy permits.
  * Branch failure result includes:

    * error type;
    * message;
    * failure context;
    * retry metadata;
    * artifact validation errors when relevant.
  * With fan-in:

    * branch failure does not automatically fail the composite;
    * fan-in decides how to handle it.
  * Without fan-in:

    * outcome policy maps failures to `partial` or `failed`.

* **Direct runtime controls inside branch execution**

  * Branch execution may produce route events or direct runtime controls.
  * Branch route event:

    * record route;
    * record reason/question/handoff when present;
    * do not follow destination.
  * Branch `RequestInput`:

    * record `status="needs_input"`;
    * record question/reason;
    * do not directly pause parent if fan-in exists.
  * Branch `Goto`:

    * record `status="completed"`;
    * record direct control kind;
    * record target destination;
    * do not follow target inside parent graph.
  * Branch `Fail`:

    * record `status="failed"`;
    * record reason/error context.
  * Branch result must distinguish:

    * route tag;
    * route destination;
    * direct runtime control kind;
    * branch status.

* **Branch route semantics**

  * A branch executes:

    * branch before hooks;
    * provider/system body;
    * branch after hooks;
    * artifact validation;
    * route validation/capture sufficient to produce branch result.
  * A branch does not:

    * update the parent workflow cursor;
    * follow route destination;
    * execute downstream workflow steps.
  * Branch route destinations are captured, not followed.
  * Branch route `on_taken` hooks do not run in v1.
  * Branch result records route and destination.
  * Composite branch group decides parent workflow route.

* **Capture-only one-step execution mode**

  * Add execution mode:

    * `route_mode="capture"`
  * Used for branch steps.
  * Capture mode:

    * validates provider/system outcome;
    * runs before/after hooks;
    * validates artifacts;
    * computes route destination;
    * does not call route `on_taken`;
    * does not schedule route handoffs;
    * does not follow destination.
  * Normal top-level execution keeps:

    * `route_mode="finalize"`
  * Fan-in should capture its event and finalize once through the composite route table.

* **Fan-in route semantics**

  * When fan-in exists:

    * downstream routes are declared on fan-in step.
    * composite branch group exposes fan-in routes.
    * branch group must not declare conflicting external routes.
  * Fan-in route becomes composite route.
  * Fan-in route must not be finalized twice.
  * Recommended v1 model:

    * execute fan-in body/provider;
    * capture fan-in event/outcome;
    * finalize captured event once against composite branch-group step.
  * When fan-in is absent:

    * downstream routes are declared on branch group outcome routes.
    * composite branch group exposes outcome-policy routes.
  * Compiler validates external route source accordingly.

* **Cancellation**

  * Cancellation is best-effort.
  * `settle="fail_fast"` may cancel running/pending tasks.
  * Cancelled branches must be recorded as `status="cancelled"`.
  * Skipped branches must be recorded as `status="skipped"`.
  * Manifest should indicate:

    * cancellation requested;
    * cancellation completed;
    * cancellation unsupported, if known.
  * Runtime must still produce a valid manifest after partial cancellation.

* **Synchronization helpers**

  * Optional future helper:

    * `ctx.parallel.lock(name)`
  * Optional future helper:

    * `ctx.parallel.semaphore(name, value)`
  * Helpers are not required in v1.
  * If provided, helpers are author tools only.
  * Framework does not infer lock usage.
  * Framework does not enforce lock discipline.
  * Do not implement thread locks for this v1.

* **Compiler validation**

  * Validate branch group name:

    * non-empty;
    * unique;
    * path-safe.
  * Validate branch names:

    * non-empty;
    * unique within group;
    * path-safe.
  * Validate `parallel(...)`:

    * non-empty branch mapping;
    * supported branch declarations;
    * no child workflow branch step in v1;
    * no scoped branch step in v1.
  * Validate `fan_out(...)`:

    * one supported branch step;
    * non-empty branch mapping;
    * serializable branch inputs;
    * no child workflow branch step in v1;
    * no scoped branch step in v1.
  * Validate provider-backed branch sessions:

    * explicit session exists;
    * session continuity is fresh;
    * explicit verifier session is fresh.
  * Validate fan-in:

    * supported fan-in step kind;
    * no ambiguous external route declarations;
    * helper reads only used in fan-in;
    * no scoped fan-in step in v1 unless explicitly supported.
  * Validate placeholders:

    * branch placeholders only in branch steps;
    * fan-in placeholders only in fan-in steps.
  * Validate mechanical outcomes:

    * success routes present or defaulted;
    * outcome routes legal;
    * custom aggregator callable shape.
  * Validate artifact path templates:

    * branch/fan-in roots used only where legal.
  * Validate static route exposure:

    * fan-in routes if fan-in exists;
    * outcome routes if fan-in absent.
  * Validate provider async support:

    * provider-backed branch groups require async provider methods.

* **Lowering model**

  * Lower each `parallel(...)` or `fan_out(...)` into one composite compiled step.
  * Composite step stores:

    * group name;
    * kind;
    * branch specs;
    * settlement policy;
    * concurrency;
    * success routes;
    * optional fan-in spec;
    * optional outcome policy.
  * Branch specs store:

    * branch name;
    * branch index;
    * branch input;
    * branch step spec.
  * Branch specs are internal.
  * Branch steps are not top-level workflow cursor nodes in v1.
  * Fan-in step is internal to composite execution but supplies external routes.
  * Static graph may show nested internals.

* **Compiled model separation**

  * Do not reuse the same dataclass field type for both authored `Step` and compiled `CompiledStep`.
  * Add separate models:

    * `BranchStepDeclarationSpec`
    * `CompiledBranchStepSpec`
    * `BranchGroupDeclarationSpec`
    * `CompiledBranchGroupSpec`
  * Or explicitly type compiled branch specs as compiled models.
  * Avoid field names where `step: Step` later becomes `step: CompiledStep`.

* **Compile cache key**

  * Compile cache key must include branch-group internals:

    * branch group name;
    * branch group kind;
    * concurrency;
    * settle;
    * success routes;
    * outcome policy identifier;
    * branch names;
    * branch inputs;
    * branch step declaration identity/topology;
    * fan-in step declaration identity/topology;
    * composite exposed route tags.
  * If comprehensive cache-key support is too risky:

    * bypass compile cache for workflows containing branch groups in v1.

* **Runtime execution model**

  * Parent engine reaches composite branch-group step.
  * Runtime initializes branch group execution record.
  * Runtime creates shared state cell.
  * Runtime shares values mapping.
  * Runtime prepares branch contexts.
  * Runtime schedules branches with `asyncio.Task`.
  * Runtime enforces concurrency with `asyncio.Semaphore`.
  * Runtime executes each branch step exactly once.
  * Runtime captures each branch result.
  * Runtime writes `results.json`.
  * Runtime writes `context.md`.
  * If fan-in exists:

    * runtime executes fan-in as ordinary authored interpretation;
    * fan-in receives fan-in metadata;
    * composite result is fan-in result.
  * If no fan-in exists:

    * runtime applies outcome policy;
    * composite result is aggregate event.
  * Parent workflow cursor advances only after composite result is known.

* **Required modular implementation boundary**

  * `engine.py` remains the top-level sequential workflow cursor.
  * Branch-group execution must not be implemented as a large branch inside `Engine.run()`.
  * Branch-group execution must live in a dedicated runtime subsystem.
  * Existing step execution machinery should be reused rather than duplicated.
  * `StepDispatcher` dispatches a compiled branch-group step to the branch-group subsystem.
  * Branch group runtime returns a normal `StepExecutionResult` to the engine.
  * `engine.py` should need only minimal wiring.
  * `engine.py` must not own:

    * branch scheduling;
    * branch context construction;
    * branch manifest serialization;
    * branch markdown rendering;
    * branch-local provider session activation;
    * fan-in orchestration;
    * mechanical outcome policy logic.

* **Recommended module layout**

  * `autoloop/core/branch_groups/__init__.py`
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
  * `autoloop/core/branch_groups/async_execution.py`

* **Minimal edits to existing modules**

  * `simple.py`

    * Export `parallel`, `fan_out`, and `FanIn`.
  * `steps.py`

    * Add branch-group/composite step declaration type.
  * `discovery.py` / lowering path

    * Discover and lower branch-group declarations.
  * `compiler.py`

    * Compile branch-group metadata.
    * Include branch-group internals in cache key.
  * `context.py`

    * Add state-cell support.
    * Add optional branch/fan-in metadata.
  * `artifacts.py`

    * Support branch/fan-in placeholders.
    * Fix templated artifact path rooting.
  * `engine_collaborators.py`

    * Add async one-step execution path.
    * Add capture route mode.
  * `engine.py`

    * Minimal collaborator construction/wiring only.

* **Async one-step execution service**

  * Branch-group runtime needs async one-step execution.
  * Preferred API:

    * `await StepDispatcher.execute_async(step, context, state, pending_handoffs, route_mode="capture")`
  * Async one-step execution must:

    * execute one compiled step;
    * run hooks;
    * resolve artifacts;
    * enforce required artifacts;
    * run provider/system body;
    * validate artifacts;
    * capture or finalize route according to route mode;
    * not advance parent workflow cursor.
  * Top-level engine uses finalize mode.
  * Branch-group runtime uses capture mode for branch steps.
  * Fan-in uses capture body/event plus composite finalization.

* **Async provider protocol**

  * Add explicit async provider protocol support:

    ```python
    class AsyncLLMProvider(Protocol):
        async def run_llm_async(self, request: LLMRequest) -> LLMResponse: ...
        async def run_producer_async(self, request: ProducerRequest) -> ProducerResponse: ...
        async def run_verifier_async(self, request: VerifierRequest) -> VerifierResponse: ...
    ```
  * Provider-backed branch steps require async methods.
  * Sync-only providers are not accepted for branch groups in this greenfield design.
  * Runtime adapters for Codex/Claude should use:

    * `asyncio.create_subprocess_exec`;
    * async stdin/stdout handling;
    * native async cancellation;
    * no thread offloading.

* **Branch context behavior**

  * Branch context shares:

    * root;
    * task folder;
    * workflow folder;
    * run folder;
    * package folder;
    * workspace;
    * state cell;
    * values mapping.
  * Branch context has branch-scoped:

    * runtime bookkeeping;
    * execution id;
    * branch metadata;
    * provider session binding view.
  * Branch context exposes:

    * `ctx.branch`
  * Branch context does not expose:

    * `ctx.fan_in`

* **Fan-in context behavior**

  * Fan-in context shares:

    * root;
    * task folder;
    * workflow folder;
    * run folder;
    * package folder;
    * workspace;
    * final state cell after branch settlement;
    * shared values mapping;
    * normal parent session semantics.
  * Fan-in context exposes:

    * `ctx.fan_in`
  * Fan-in context does not expose a single active branch through `ctx.branch`.
  * Fan-in executes under normal step semantics, except that route finalization must happen exactly once through the composite.

* **Artifacts**

  * Branch steps may declare normal writes.
  * Branch steps may use branch placeholders in artifact templates.
  * Branch steps may write shared paths.
  * Branch steps may write overlapping paths.
  * Declared branch artifacts are captured in branch manifest.
  * Artifact validation runs per branch.
  * Missing required branch artifact is branch validation failure or branch failure.
  * Fan-in reads branch artifacts by consulting manifest or explicit paths.
  * No automatic branch artifact namespacing is required.
  * No automatic artifact conflict failure exists.

* **Hooks**

  * Branch steps run before hooks.
  * Branch steps run after hooks.
  * Branch steps do not run route `on_taken` hooks in v1 capture mode.
  * Fan-in step runs normal before/after hooks.
  * Fan-in route finalization runs exactly once at composite level.
  * Composite step emits outer lifecycle events.
  * Branch hook events should be nested under the composite branch group.
  * Git/checkpoint-like extensions should checkpoint at composite boundary by default.

* **Checkpoint and resume**

  * V1 checkpoints at composite boundary.
  * V1 may rerun full branch group if interrupted during branch execution.
  * V1 does not require partial branch resume.
  * V1 does not require branch-specific pending-input resume.
  * If fan-in asks a question:

    * normal workflow checkpoint/resume applies at fan-in/composite level.
  * If branch asks a question with fan-in:

    * it is captured in manifest.
    * fan-in may ask consolidated question.
  * If branch asks a question without fan-in:

    * composite may route to `question`.
    * normal checkpoint can apply at composite route.
  * vFuture may add:

    * partial branch replay;
    * branch-level checkpointing;
    * branch-specific interactive resume.

* **Observability events**

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

    * group name;
    * group kind;
    * branch name, when applicable;
    * branch index, when applicable;
    * step name;
    * execution id;
    * status;
    * route;
    * destination;
    * error summary;
    * artifact paths.

* **Static graph representation**

  * Branch group appears as one composite node.
  * Composite node includes nested metadata:

    * group name;
    * kind;
    * branch names;
    * branch step names;
    * fan-in step name, if present;
    * exposed routes.
  * Branch internals are inspectable.
  * Branch internals are not top-level workflow cursor nodes.

* **Child workflow branch rule**

  * V1 disallows child workflow steps as branch steps.
  * Child workflow fan-in is vFuture unless explicitly redesigned.
  * Reason:

    * nested checkpointing complexity;
    * recursive session validation complexity;
    * child terminal mapping complexity;
    * branch-specific resume complexity.

* **Worklist fan-out rule**

  * V1 does not support worklist-derived fan-out.
  * V1 `fan_out(...)` accepts explicit branch mappings only.
  * Existing scoped worklist execution remains sequential.
  * Future worklist fan-out may:

    * snapshot selected worklist items;
    * derive branch names from item ids;
    * pass item payload as branch input;
    * avoid implicit cursor advancement.

* **Operation branch rule**

  * V1 should reject operation branch steps unless async-safe operation runtime binding is implemented.
  * If operation branches are later allowed:

    * branch operation runtime must be active inside each async branch task;
    * branch operation runtime must include branch execution id;
    * no thread-local assumptions are allowed.
  * Plain Python branch steps may be allowed.
  * CPU-heavy Python branch steps can block the event loop; document as v1 limitation.
  * Python branch steps with `scope` remain rejected.

* **Strictness tests**

  * Add tests that fail if branch-group implementation imports or uses:

    * `concurrent.futures`
    * `ThreadPoolExecutor`
    * `Future`
    * `FIRST_COMPLETED`
    * `threading.RLock`
    * `asyncio.to_thread`
  * Add tests that ensure no fabricated provider session id is passed to providers.
  * Add tests that ensure async provider is required for provider-backed branch execution.

* **Required runtime tests**

  * `parallel(...)` with async fake provider and `concurrency>1` runs branches concurrently.
  * `parallel(...)` with sync-only provider fails.
  * `parallel(..., concurrency=1)` works for async provider.
  * `fan_out(...)` renders `{branch.input.*}`.
  * Branch artifact path renders `{branch.name}`.
  * Branch route destination is not followed.
  * Branch route `on_taken` is not run in capture mode.
  * Fan-in route finalizes exactly once.
  * Branch `RequestInput` becomes `needs_input` with fan-in.
  * Branch `RequestInput` routes composite to `question` without fan-in.
  * Branch `Goto` is captured and not followed.
  * Branch `Fail` is captured as failed.
  * Same file writes are not rejected.
  * Branch state assignment updates shared state cell.
  * Branch values mutation updates shared values mapping.
  * Branch sessions do not activate parent session slot.
  * Two branches using same `Session.fresh()` declaration get distinct provider contexts.
  * Provider receives `session_id=None` on first branch turn.
  * Provider-returned session id appears in branch result.
  * Manifest branch order follows declaration order.
  * Context markdown is deterministic.
  * Fan-in does not run if `results.json` write fails.
  * Fan-in does not run if `context.md` write fails.
  * Branch evidence path is under `workflow_folder`.

* **Required compile-time tests**

  * Missing provider branch session fails.
  * Non-fresh provider branch session fails.
  * Explicit fresh provider branch session passes.
  * Produce/verify branch with non-fresh verifier session fails.
  * Child workflow branch step fails.
  * Scoped branch step fails.
  * Operation branch step fails unless async-safe operation runtime exists.
  * Branch placeholder outside branch fails.
  * Fan-in placeholder outside fan-in fails.
  * `FanIn.results()` outside fan-in fails.
  * `FanIn.context()` outside fan-in fails.
  * Unsafe group name fails.
  * Unsafe branch name fails.
  * Branch-group internals affect compile cache key or compile cache is bypassed.

* **Recommended implementation order**

  * Phase 1:

    * remove threads;
    * remove locks;
    * keep branch group behavior sequential only for non-provider-safe development paths;
    * fail provider-backed branch groups until async provider path exists.
  * Phase 2:

    * add async provider protocol;
    * add async fake provider tests;
    * add async step execution path.
  * Phase 3:

    * enable real `concurrency>1` for async-capable providers.
  * Phase 4:

    * implement capture-only route mode.
  * Phase 5:

    * fix branch-local sessions and evidence root.
  * Phase 6:

    * complete compile/runtime/strictness test matrix.
  * Phase 7:

    * remove any leftover compatibility code introduced during transition.

* **Final merge gate**

  * No thread execution.
  * No thread imports in branch-group subsystem.
  * No `asyncio.to_thread`.
  * No sync-provider compatibility inside branch groups.
  * Native async provider path exists for provider-backed branch execution.
  * Provider-backed branch groups fail if async provider support is missing.
  * No synthetic provider session ids.
  * Fresh sessions are branch-execution-local.
  * Scoped branch steps are rejected.
  * Child workflow branch steps are rejected.
  * Operation branch steps are rejected unless async-safe.
  * Branch route destinations are captured, not followed.
  * Branch route `on_taken` hooks do not run in v1.
  * Fan-in route finalizes exactly once.
  * Branch evidence is written under `workflow_folder`.
  * Branch-group internals are included in compile cache key or cache is bypassed.
  * Full test matrix passes.
  * Implementation contains no legacy compatibility complexity for sync branch-group execution.
