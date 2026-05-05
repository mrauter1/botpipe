# Branch Groups Plan

## Scope And Invariants
- Implement explicit `parallel(...)` and `fan_out(...)` branch groups as composite workflow steps only.
- Keep `engine.py` as the top-level sequential cursor; branch scheduling, settlement, manifest writing, fan-in orchestration, and outcome routing live in a dedicated `autoloop/core/branch_groups` subsystem.
- Keep ordinary workflow semantics unchanged outside branch groups.
- Enforce stricter branch-only provider session rules: provider-backed branch steps must declare explicit `Session.fresh()`, and child workflow branch steps remain unsupported in v1.
- Preserve the requested fan-in step-kind matrix: fan-in may be LLM, produce/verify, Python, or operation based, but child workflow fan-in remains unsupported in v1 unless explicit mapping is designed later.
- Preserve v1 non-goals: no inferred parallelism, no automatic merge/conflict handling, no branch-local workspace overlays, no partial branch resume.

## Codebase Fit
- `autoloop/simple.py` and `autoloop/__init__.py` own the public authoring surface and exports.
- `autoloop/core/steps.py`, `discovery.py`, `validation.py`, `compiler.py`, and `lowering.py` already own declaration lowering and route/session validation, so branch-group authoring and compile-time checks should plug in there.
- `StepDispatcher.execute()` already executes one compiled step and returns `StepExecutionResult` without advancing the workflow cursor, so it is the correct nested execution service for branch steps and fan-in.
- `Context` currently stores `_state`, `_values`, and `_session_store` directly; branch sharing and branch-local session isolation therefore require explicit context/session plumbing rather than only a new scheduler.
- `artifacts.py`, `engine.py`, and `operations.py` split prompt/artifact placeholder rendering today, so branch/fan-in placeholders and templated artifact rooting must be updated in both compile-time and runtime paths.

## Milestones
### 1. Authoring And Compile Model
- Add public `parallel(...)`, `fan_out(...)`, and `FanIn` declarations on the simple surface, plus matching exports from `autoloop/__init__.py`.
- Introduce `autoloop/core/branch_groups/{models,declarations,validation,lowering}.py`.
- Lower simple branch-group declarations into a composite step shape (`BranchGroupStep` or equivalent) that appears as one workflow step externally and carries ordered internal branch specs plus optional fan-in metadata.
- Validate group/branch names, supported branch step kinds, supported fan-in step kinds, serializable fan-out inputs, helper placement, placeholder legality, exposed routes, and branch-only provider session requirements before compiler default-session lowering runs.
- Explicitly reject child workflow branch steps and child workflow fan-in steps in v1 while still allowing prompt/LLM, produce/verify, Python, and operation fan-in steps.

### 2. Shared Context And Session Scaffolding
- Add a shared `StateCell` and optional branch/fan-in metadata surface to `Context`.
- Make `Context.state`, the state setter, and `context_runtime(...).set_state(...)` update the shared cell when present so branch assignment reaches the parent state cell.
- Introduce a branch-scoped session-store view that implements the existing `SessionStore` protocol, persists branch-created sessions, and prevents nondeterministic parent active-slot takeover.
- Route step session selection and persistence through the context-bound session store/view rather than relying only on `Engine.session_store`.
- Keep branch bookkeeping branch-scoped by keying visits/last-route/retry counters with group and branch identity instead of reusing the parent step store directly.

### 3. Composite Runtime, Evidence, And Routing
- Add `autoloop/core/branch_groups/{context,sessions,manifest,outcomes,runtime}.py`.
- Dispatch compiled branch-group steps from `StepDispatcher` into `BranchGroupRuntime`, with only minimal wiring in `engine.py`.
- Use a bounded thread executor for v1 branch concurrency because provider and step execution are currently synchronous; protect shared state/value replacement writes with runtime locks while leaving in-place mutation author-owned.
- Reuse `StepDispatcher.execute()` for each branch step and optional fan-in step, capture `StepExecutionResult`, and never follow branch destinations inside the parent graph.
- Write `_branch_groups/<group>/results.json` and `_branch_groups/<group>/context.md` in declaration order using the requested persisted contract:
  - `results.json` uses schema id `autoloop.branch_results/v1` and includes the requested top-level fields, branch result fields, status vocabulary, ordering guarantees, and raw output/session/usage/error metadata.
  - `context.md` includes the requested deterministic branch summary sections, bounded excerpts only when safe, and per-branch input/status/route/reason/question/artifact/error/raw-output references.
- Implement the no-fan-in outcome contract explicitly:
  - `success_routes` defaults to `("done", "accepted")` and only marks a branch successful when `status="completed"` and the route tag is in that set.
  - Built-in `outcome` values `all_done`, `all_settled`, and `any_done` map to the requested composite `done` / `partial` / `question` / `failed` routes.
  - Custom aggregators must accept the manifest plus current context and return a legal composite event.
- Fail the composite before fan-in or mechanical outcome routing if manifest/context writing fails, and keep checkpoints at the composite boundary only; branch `RequestInput` becomes recorded branch result data until composite routing resolves.

### 4. Surface Hardening And Regression Suite
- Extend runtime placeholder resolution and simple prompt validation to support `{branch.*}` and `{fan_in.*}` only in legal contexts.
- Fix relative templated artifact rooting so rendered relative paths still resolve under the owning step directory after placeholder expansion.
- Extend runtime events and static graph/topology payloads with additive branch-group metadata while preserving existing flat top-level step ordering for unchanged workflows.
- Add compile-time, unit, contract, and runtime coverage for the acceptance matrix, plus regressions around default sessions outside branch groups, pending-input handling, checkpoint boundaries, and deterministic manifests/context markdown.

## Interface Definitions
- Public declarations:
  - `parallel(branches=..., concurrency=None, settle="all", fan_in=None, outcome="all_done", success_routes=("done", "accepted"), routes=None)`
  - `fan_out(step=..., branches=..., concurrency=None, settle="all", fan_in=None, outcome="all_done", success_routes=("done", "accepted"), routes=None)`
  - `FanIn.results()` and `FanIn.context()` should return dedicated helper tokens, not raw strings, so the compiler can reject use outside fan-in steps precisely.
- Step-kind matrix:
  - Branch steps may be prompt/LLM, produce/verify, Python, or operation based; child workflow branch steps are rejected in v1.
  - Fan-in steps may be prompt/LLM, produce/verify, Python, or operation based; child workflow fan-in is rejected in v1 until explicit input/message mapping exists.
- Runtime context:
  - `ctx.branch` is available only during branch execution and exposes `name`, `index`, `group`, `input`, and `count`.
  - `ctx.fan_in` is available only during fan-in and exposes parsed results, evidence paths/text, and aggregate counts.
- Compiled/runtime internals:
  - `CompiledStep` gains branch-group payload metadata or an equivalent composite-step field; `StepDispatcher` dispatches on that field/kind.
  - `BranchGroupRuntime.run(...) -> StepExecutionResult` returns a normal step result to the engine.
  - `StepDispatcher.execute()` remains the single-step nested executor; cursor advancement stays only in `Engine.run()`.
- Persisted/runtime-owned outputs:
  - `results.json` is a new runtime-owned persisted contract and must be deterministic in branch declaration order.
  - `context.md` is a deterministic LLM-readable companion document, not a raw-log dump.
  - `_branch_groups` evidence remains runtime-owned and is not added to the ordinary declared artifact inventory in v1.

## Compatibility Notes
- Existing non-branch workflows keep current compilation, routing, checkpoint, and default-session behavior.
- The only intentional behavior tightening is inside branch groups: provider-backed branch steps cannot rely on implicit default sessions or non-fresh continuity.
- Child workflow fan-in remains intentionally unsupported in v1, matching the request rather than broadening support silently.
- `topology.json`, `static_step_graph.json`, and runtime trace streams gain additive branch-group metadata and new runtime event types; unchanged workflows keep their existing flat shape.
- No checkpoint schema migration is required for v1 because branch groups checkpoint only as one composite stage, and `results.json` / `context.md` are new runtime-owned artifacts rather than replacements for existing persisted payloads.
- `_branch_groups` becomes runtime-owned evidence space, but v1 still does not forbid user writes there.

## Regression Risks And Controls
- Session bleed across branches or into the parent:
  - Control with branch session-store views and explicit tests that parent active bindings remain deterministic after branch completion.
- Shared state/value replacement races under threaded execution:
  - Control with locks around shared-cell and shared-mapping replacement only; document that in-place mutation remains author responsibility.
- Templated artifact path regressions:
  - Control with one shared fix in `resolve_artifact_template()` and tests for both ordinary templated artifacts and branch placeholders.
- Pending-input semantics drifting into parent checkpoints mid-branch:
  - Control by consuming `StepExecutionResult` inside branch runtime and treating `pending_input` as branch result data until composite routing resolves.
- Static graph/hash instability:
  - Control with additive nested metadata and deterministic declaration-order serialization.

## Validation, Rollout, And Rollback
- Validation:
  - Unit tests for compile-time errors, helper legality, placeholder legality, artifact-path rooting, allowed/disallowed fan-in step kinds, and branch-only session validation before default-session lowering.
  - Contract/runtime tests for branch execution, fan-in routing, mechanical outcomes, shared state/value effects, session isolation, overlapping writes, manifest schema/ordering/status coverage, context markdown contents, and composite checkpoint behavior.
- Rollout:
  - Land slices in milestone order so compile-time structure exists before runtime wiring and runtime wiring exists before observability/test hardening.
- Rollback:
  - First remove dispatcher support for the composite kind and public exports; the dedicated `branch_groups` package should remain isolated enough to revert without disturbing ordinary step execution.
