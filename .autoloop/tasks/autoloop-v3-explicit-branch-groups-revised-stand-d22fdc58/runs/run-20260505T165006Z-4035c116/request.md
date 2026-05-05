## Autoloop v3 explicit branch groups: revised standalone spec

* **Purpose**

  * Add explicit concurrent execution to Autoloop v3.
  * Preserve Autoloop’s author-responsibility model.
  * Support concurrent execution without introducing automatic dependency scheduling.
  * Support two branch-group primitives:

    * `parallel(...)`: run different authored steps concurrently.
    * `fan_out(...)`: run the same authored step multiple times concurrently with different branch inputs.
  * Support optional authored `fan_in` on both `parallel(...)` and `fan_out(...)`.
  * Treat `fan_in` as a normal authored step, usually LLM-capable, that interprets branch results.
  * Avoid framework-owned state merge semantics.
  * Avoid framework-owned workspace conflict semantics.
  * Avoid provider session sharing inside branch execution until provider session forking is reliable.

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
  * No worklist-derived fan-out.
  * No branch-specific interactive resume.
  * No implicit concurrent execution for existing scoped worklist steps.

* **Terminology**

  * **Branch group**

    * Composite execution unit created by `parallel(...)` or `fan_out(...)`.
    * Has a deterministic group name.
    * Has one or more named branches.
    * Produces a branch manifest.
    * Produces an LLM-readable branch context document.
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
  * **Branch context**

    * LLM-readable markdown artifact summarizing branch results.
  * **Fan-in**

    * Optional authored post-barrier step.
    * Consumes branch manifest/context.
    * Produces synthesis, decision artifacts, and route.

* **Branch group naming**

  * Branch group name must be deterministic.
  * Branch group name must be unique within the workflow.
  * Branch group name must be non-empty.
  * Branch group name must be path-safe in v1.
  * Branch names must be unique within the group.
  * Branch names must be non-empty.
  * Branch names must be path-safe in v1.
  * V1 should reject unsafe group or branch names rather than silently slugifying them.
  * Suggested allowed name pattern:

    * lowercase or mixed-case alphanumerics are allowed.
    * `_`, `-`, and `.` are allowed.
    * path separators are not allowed.
    * empty names are not allowed.
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
    * Writes branch context markdown.
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
    * Writes branch context markdown.
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
  * `fan_in` may be operation-based.
  * Child workflow `fan_in` is vFuture unless explicit input/message mapping is added.
  * `fan_in` runs after branch settlement.
  * `fan_in` receives branch manifest and branch context.
  * `fan_in` may read any workspace path.
  * `fan_in` may write any artifacts.
  * `fan_in` may mutate parent workflow state.
  * `fan_in` may use any session declared by the author.
  * `fan_in` does not require `Session.fresh()` unless it is itself also used as a branch step elsewhere.
  * `fan_in` is not a framework merge policy.
  * `fan_in` is not a state reconciler.
  * `fan_in` is not a workspace conflict resolver.
  * `fan_in` is authored interpretation.

* **When `fan_in` exists**

  * Branches settle according to `settle`.
  * Runtime writes branch manifest.
  * Runtime writes branch context markdown.
  * Runtime executes the fan-in step.
  * Composite branch-group route equals the fan-in route.
  * Composite branch-group external routes are exactly the fan-in step’s authored routes.
  * Branch failures are recorded and passed to fan-in.
  * Branch questions are recorded and passed to fan-in.
  * Branch cancellations are recorded and passed to fan-in.
  * Fan-in decides whether to continue, fail, rework, or ask the user.

* **When `fan_in` is absent**

  * Branches settle according to `settle`.
  * Runtime writes branch manifest.
  * Runtime writes branch context markdown.
  * Runtime applies mechanical outcome policy.
  * Composite branch-group route equals the outcome-policy route.
  * External routes are the outcome-policy routes.
  * Downstream ordinary steps may read branch manifest/context and branch artifacts.

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

* **Provider-backed step classification**

  * Provider-backed branch steps:

    * LLM/prompt steps.
    * produce/verify steps.
  * Non-provider branch steps:

    * Python steps.
    * pure operation steps.
  * Disallowed as branch steps in v1:

    * child workflow steps.
  * Allowed as fan-in steps in v1:

    * LLM/prompt steps.
    * produce/verify steps.
    * Python steps.
    * operation steps.
  * Child workflow fan-in is vFuture unless explicit mapping is added.

* **Prompt/LLM branch session rule**

  * A prompt/LLM branch step must declare:

    * `session=Session.fresh()`
  * A prompt/LLM branch step with no explicit session is a compiler error.
  * A prompt/LLM branch step with `Session.run()`, `Session.task()`, `Session.work_item()`, or custom non-fresh continuity is a compiler error.

* **Produce/verify branch session rule**

  * Producer session must be explicitly fresh.
  * If `verifier_session` is omitted:

    * verifier uses the fresh producer session selected for that branch execution.
  * If `verifier_session` is explicit:

    * it must also be explicitly fresh.
  * Producer and verifier may share the same explicit fresh session.
  * Producer and verifier may use separate explicit fresh sessions.

* **Branch-local provider session activation**

  * Fresh provider sessions created inside branches are branch-local bindings.
  * Branch-local provider sessions must not nondeterministically replace the parent active session for the same slot.
  * Branch-local provider sessions must be recorded in branch traces and branch results when useful.
  * Fan-in starts from normal parent session semantics.
  * Fan-in must not accidentally inherit “last completed branch session wins.”
  * Implementation may use:

    * branch-scoped session-store views;
    * branch-local active session maps;
    * persist-without-parent-activation semantics.
  * Parent session store activation must remain deterministic after branch group completion.

* **Compiler errors for session violations**

  * Missing branch session:

    * `branch group '<group>' includes provider-backed branch step '<step>' without explicit session=Session.fresh().`
  * Non-fresh branch session:

    * `branch group '<group>' includes provider-backed branch step '<step>' with non-fresh session continuity '<kind>'.`
  * Non-fresh verifier session:

    * `branch group '<group>' includes produce/verify branch step '<step>' with non-fresh verifier_session continuity '<kind>'.`
  * Child workflow branch step:

    * `branch group '<group>' includes child workflow branch step '<step>', which is unsupported in v1.`

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
  * Shared state mutation is intentionally nondeterministic under concurrent writes.
  * Authors needing deterministic aggregation should prefer branch artifacts plus fan-in.

* **Shared state cell**

  * Branch contexts must share one state cell.
  * Conceptual structure:

    ```python
    @dataclass
    class StateCell:
        value: BaseModel
        version: int = 0
    ```
  * `Context.state` getter reads from `StateCell.value`.
  * `Context.state` setter writes to `StateCell.value`.
  * `Context.state` setter increments `StateCell.version`.
  * `context_runtime(...).set_state(...)` must update the same state cell.
  * Hook state updates must update the same state cell.
  * Provider execution state updates must update the same state cell.
  * State cell version is diagnostic only.
  * State cell version does not imply conflict detection.

* **Shared values semantics**

  * `ctx.values` is shared within a branch group in v1.
  * Branch contexts receive the same mutable values mapping.
  * Branches may mutate shared values.
  * The framework does not merge values.
  * The framework does not detect values conflicts.
  * Last actual mutation wins unless the author synchronizes.
  * Shared values mutation is intentionally nondeterministic under concurrent writes.
  * Authors needing deterministic aggregation should prefer branch artifacts plus fan-in.

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
  * A branch artifact template such as:

    * `assessments/{branch.name}.json`
  * must not accidentally resolve relative to process working directory.
  * If the artifact has an owning step, relative templated paths should resolve under the normal step/workflow artifact root for that owner.
  * Implementation must ensure templated and non-templated step artifacts use consistent rooting semantics.
  * This may require updating artifact template resolution.

* **Branch group artifact paths**

  * Every branch group writes:

    * `_branch_groups/<group_name>/results.json`
    * `_branch_groups/<group_name>/context.md`
  * Per-branch raw output should be stored or referenced under:

    * `_branch_groups/<group_name>/branches/<branch_name>/...`
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
  * `destination` records a route destination or direct control target when available, but it is not followed.
  * `question` may be `null`.
  * `provider_session` may be `null`.
  * `usage` may be empty.

* **Branch context markdown**

  * File:

    * `_branch_groups/<group_name>/context.md`
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

    * `_branch_groups/<group_name>/results.json`
  * `FanIn.context()` resolves to:

    * `_branch_groups/<group_name>/context.md`
  * Helpers are valid only in fan-in steps.
  * Compiler rejects helper usage outside fan-in steps.
  * V1 does not need `FanIn.artifacts()`.
  * Fan-in can discover artifact paths from the manifest.

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
    * requests cancellation of running branches when supported;
    * records cancelled/skipped branches;
    * then proceeds according to fan-in or outcome policy.
  * `quorum` is vFuture.
  * Cancellation is best-effort.
  * Providers may not support hard cancellation.

* **Concurrency**

  * `concurrency` limits simultaneous branch executions.
  * `concurrency` must be positive if provided.
  * If omitted, recommended behavior is to schedule all branches concurrently.
  * Runtime may enforce a global maximum concurrency.
  * `concurrency=1` is valid.
  * With `concurrency=1`, branch group still uses branch-group semantics.
  * Branch result order in manifest must follow declaration order, not completion order.
  * Scheduling should be deterministic where practical.

* **Branch success semantics**

  * Branch completion is not the same as branch success.
  * Branch steps can have arbitrary route tags.
  * Mechanical outcome policies need a success predicate.
  * Branch groups without fan-in must define or inherit `success_routes`.
  * Recommended API:

    * `success_routes=("done", "accepted")` by default.
  * Authors may override:

    * `success_routes=("approved", "ready")`
  * A branch with `status="completed"` and route in `success_routes` is successful.
  * A branch with `status="completed"` but route outside `success_routes` is completed but not successful for mechanical outcome purposes.
  * Custom outcome aggregators may define their own success semantics.
  * When fan-in exists, `success_routes` is still useful for manifest/context summaries but does not determine the composite route.

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

    * route `done` if every branch is successful.
    * route `question` if any branch needs input.
    * route `partial` if some branches settled but not all are successful.
    * route `failed` only for hard group failure.
  * `all_settled`:

    * route `done` if all branches reached any terminal branch result and none need input or failed hard.
    * route `question` if any branch needs input.
    * route `partial` if any branch failed/cancelled/non-success.
  * `any_done`:

    * route `done` if at least one branch is successful.
    * route `question` if no branch is successful and any branch needs input.
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

    * branch failure does not automatically fail the composite.
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

* **Cancellation**

  * Cancellation is best-effort.
  * `settle="fail_fast"` may request cancellation.
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

* **Branch route semantics**

  * A branch executes:

    * branch before hooks;
    * provider/system body;
    * branch after hooks;
    * artifact validation;
    * route validation/finalization sufficient to produce branch result.
  * A branch does not:

    * update the parent workflow cursor;
    * follow route destination;
    * execute downstream workflow steps.
  * Branch result records route and destination.
  * Composite branch group decides parent workflow route.

* **Fan-in route semantics**

  * When fan-in exists:

    * downstream routes are declared on fan-in step.
    * composite branch group exposes fan-in routes.
    * branch group must not declare conflicting external routes.
  * When fan-in is absent:

    * downstream routes are declared on branch group outcome routes.
    * composite branch group exposes outcome-policy routes.
  * Compiler validates external route source accordingly.

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
    * no child workflow branch step in v1.
  * Validate `fan_out(...)`:

    * one supported branch step;
    * non-empty branch mapping;
    * serializable branch inputs;
    * no child workflow branch step in v1.
  * Validate provider-backed branch sessions:

    * explicit session exists;
    * session continuity is fresh;
    * explicit verifier session is fresh.
  * Validate fan-in:

    * supported fan-in step kind;
    * no ambiguous external route declarations;
    * helper reads only used in fan-in.
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

* **Runtime execution model**

  * Parent engine reaches composite branch-group step.
  * Runtime initializes branch group execution record.
  * Runtime creates shared state cell.
  * Runtime creates or passes shared values mapping.
  * Runtime prepares branch contexts.
  * Runtime schedules branches subject to concurrency.
  * Runtime executes each branch step exactly once.
  * Runtime captures each branch result.
  * Runtime writes `results.json`.
  * Runtime writes `context.md`.
  * If fan-in exists:

    * runtime executes fan-in as ordinary step;
    * fan-in receives fan-in metadata;
    * composite result is fan-in result.
  * If no fan-in exists:

    * runtime applies outcome policy;
    * composite result is aggregate event.
  * Parent workflow cursor advances only after composite result is known.

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
  * Fan-in executes under normal step semantics.

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

  * Branch steps run normal hooks.
  * Fan-in step runs normal hooks.
  * Composite step emits outer lifecycle events.
  * Branch hook events should be nested under the composite branch group.
  * Git/checkpoint-like extensions should checkpoint at composite boundary by default.
  * V1 should avoid top-level commit/checkpoint behavior per branch unless explicitly implemented.

* **Checkpoint and resume**

  * V1 checkpoints at composite boundary.
  * V1 may rerun full branch group if interrupted during branch execution.
  * V1 does not require partial branch resume.
  * V1 does not require branch-specific pending input resume.
  * If fan-in asks a question:

    * normal workflow checkpoint/resume applies at fan-in.
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
  * Reason:

    * nested checkpointing complexity;
    * recursive session validation complexity;
    * child terminal mapping complexity;
    * branch-specific resume complexity.
  * Child workflow fan-in is vFuture unless explicit input/message mapping is designed.
  * In v1, prefer normal LLM, produce/verify, Python, or operation fan-in steps.

* **Worklist fan-out rule**

  * V1 does not support worklist-derived fan-out.
  * V1 `fan_out(...)` accepts explicit branch mappings only.
  * Existing scoped worklist execution remains sequential.
  * Future worklist fan-out may:

    * snapshot selected worklist items;
    * derive branch names from item ids;
    * pass item payload as branch input;
    * avoid implicit cursor advancement.

* **Example: `parallel(...)` with fan-in**

  * Branch steps:

    * `security_review`, `cost_review`, `ux_review`
  * Each branch step:

    * declares `Session.fresh()`
    * writes its own review artifact
  * Fan-in step:

    * uses normal manager session
    * reads `FanIn.context()`
    * reads `FanIn.results()`
    * writes final review artifacts
    * routes to `approved` or `needs_revision`
  * Composite:

    * exposes `approved` and `needs_revision`

* **Example: `parallel(...)` without fan-in**

  * Branch steps:

    * `history_research`, `current_research`, `risk_research`
  * Each branch step:

    * declares `Session.fresh()`
  * Composite:

    * uses `outcome="all_done"`
    * uses `success_routes=("done",)`
    * exposes `done`, `partial`, `question`, `failed`
  * Downstream synthesis is a normal later step.

* **Example: `fan_out(...)` with fan-in**

  * Branch step:

    * `assess_one`
    * prompt uses `{branch.input.area}`
    * artifact path uses `{branch.name}`
    * declares `Session.fresh()`
  * Branch inputs:

    * security
    * performance
    * reliability
  * Fan-in:

    * prompt uses `{fan_in.context_text}`
    * reads `FanIn.context()`
    * reads `FanIn.results()`
    * routes to `ready` or `needs_more_work`

* **Example: `fan_out(...)` without fan-in**

  * Branch step:

    * `generate_one_report`
    * prompt uses `{branch.input.customer}`
    * writes `reports/{branch.name}.md`
    * declares `Session.fresh()`
  * Composite:

    * uses mechanical outcome policy
    * writes branch manifest and context
    * routes to packaging or recovery.

* **V1 acceptance criteria**

  * `parallel(...)` supports multiple distinct branch steps.
  * `fan_out(...)` supports repeated execution of one branch step over explicit branch mappings.
  * `fan_in` is available on both primitives.
  * `fan_in` is optional on both primitives.
  * Provider-backed branch steps without explicit `Session.fresh()` fail compilation.
  * Provider-backed branch steps with non-fresh sessions fail compilation.
  * Produce/verify branch steps enforce fresh producer and verifier session rules.
  * Branch-local provider sessions do not overwrite parent active session slots nondeterministically.
  * Python branch steps do not require sessions.
  * Child workflow branch steps fail compilation.
  * Branches may mutate shared parent state.
  * Branches may mutate shared values.
  * Branches may write overlapping workspace paths.
  * Framework does not reject overlapping writes.
  * Branch placeholders render correctly in branch prompts and branch artifact paths.
  * Fan-in placeholders render correctly in fan-in prompts.
  * Templated branch artifact paths are rooted consistently with normal step artifacts.
  * `FanIn.results()` resolves correctly.
  * `FanIn.context()` resolves correctly.
  * Branch result manifest is deterministic.
  * Branch context markdown is deterministic.
  * Branch result order follows declaration order.
  * Branch route destinations are not followed.
  * Direct runtime controls inside branches are captured, not followed.
  * Composite route equals fan-in route when fan-in exists.
  * Composite route equals outcome-policy route when fan-in is absent.
  * Mechanical outcome policies use explicit/default success routes.
  * Branch-level questions are captured as branch results when fan-in exists.
  * Without fan-in, branch-level questions route composite to `question` by default.
  * Runtime traces show nested branch execution.
  * Static graph shows branch group structure.
  * Checkpointing works at composite boundary.
  * Fan-in pending input uses normal workflow resume behavior.
