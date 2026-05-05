# Branch-Group v1 Plan

## Intent
- Implement the supplied explicit branch-group contract as the source of truth.
- Treat the current branch-group code as a partial prototype to refactor, not a compatibility target.
- Preserve existing top-level workflow execution where feasible, but do not preserve thread-backed, sync-provider, or synthetic-session behavior inside branch groups.

## Current divergence to correct
- `autoloop/core/branch_groups/runtime.py` still uses `ThreadPoolExecutor`, `Future`, `wait`, and a lock-backed shared-values wrapper.
- `autoloop/core/branch_groups/context.py` still uses `RLock` in `StateCell`.
- `autoloop/core/branch_groups/sessions.py` fabricates branch session ids and falls back to parent active session lookup.
- Provider execution is sync-only today; branch groups cannot satisfy the asyncio-only concurrency contract yet.
- Branch evidence is rooted at `context.root / "_branch_groups"` instead of `{workflow_folder}/_branch_groups/...`.
- Placeholder validation still uses `startswith("branch")` / `startswith("fan_in")`.
- Compile cache fingerprinting does not safely cover all branch-group internals; relying on the current cache path is risky.

## Delivery milestones
1. Contract hardening and compile-time guardrails.
   - Split authored declaration models from compiled branch-group specs.
   - Tighten validation for path-safe names, exact placeholder roots, explicit fresh provider sessions, and rejection of scoped, child-workflow, and operation branch steps.
   - Expose composite routes strictly from `fan_in` or mechanical outcomes, never both.
   - Bypass compile cache for workflows containing branch groups unless internal-topology coverage is proven complete.
2. Async step/provider execution foundation.
   - Add explicit async provider protocol methods for LLM, producer, and verifier turns.
   - Add async fake/test providers first, then adapt rendered providers to native async transport.
   - Add `StepDispatcher.execute_async(..., route_mode="capture" | "finalize")` and keep sync `execute(...)` as a thin compatibility entrypoint where possible.
3. Async branch-group runtime and scheduler.
   - Move branch scheduling to `asyncio.Task` plus `asyncio.Semaphore`.
   - Implement `settle="all"` and `settle="fail_fast"` with branch result capture, best-effort cancellation, and deterministic declaration-order manifests.
   - Keep branch-group orchestration in the dedicated subsystem; `engine.py` only wires the collaborator.
4. Shared-context, session, and evidence correctness.
   - Use one shared lock-free `StateCell` and one shared mutable values mapping within each branch group.
   - Make branch bookkeeping branch-scoped and deterministic by execution id.
   - Rework `BranchSessionStoreView` so fresh branch keys are branch-execution-local, `session_id` starts as `None`, and provider-backed branch lookups do not inherit parent active sessions.
   - Move runtime-owned evidence to `{workflow_folder}/_branch_groups/<group>/...`.
5. Fan-in, outcomes, and manifest/context completion.
   - Capture branch routes without following destinations or running route `on_taken` hooks.
   - Finalize fan-in exactly once through the composite step route table.
   - Complete manifest/context schema, summaries, helper reads, and downstream-readable evidence paths.
6. Strictness, regression coverage, and cleanup.
   - Add compile-time, runtime, and strictness tests for every explicit spec requirement.
   - Remove leftover thread imports, lock wrappers, synthetic-session behavior, and sync-provider compatibility branches from the branch-group path.

## Interface and module changes
- `autoloop/simple.py`
  - Keep `parallel`, `fan_out`, and `FanIn` public.
  - Reject branch-group session ownership options; sessions stay step-owned.
- `autoloop/core/branch_groups/models.py`
  - Introduce separate authored and compiled branch-group/branch-step spec types instead of reusing `Step`-typed fields ambiguously.
- `autoloop/core/discovery.py`
  - Lower branch groups into one composite step with internal compiled branch specs and optional compiled fan-in spec.
- `autoloop/core/compiler.py`
  - Compile internal branch/fan-in steps explicitly.
  - Either extend the cache key to include all branch-group internals or bypass cache when branch groups are present.
- `autoloop/core/engine_collaborators.py`
  - Add async one-step execution and capture/finalize route modes.
  - Keep route finalization centralized so branch capture and fan-in finalization share one implementation.
- `autoloop/core/providers/protocols.py`
  - Add an async provider protocol; branch-group concurrency must require it.
- `autoloop/core/branch_groups/runtime.py`
  - Replace thread-backed runtime with async scheduler/orchestrator.
- `autoloop/core/branch_groups/sessions.py`
  - Stop fabricating provider session ids and stop parent-session fallback for provider-backed fresh branches.
- `autoloop/core/artifacts.py`
  - Keep templated relative artifact paths rooted under the owning step, including `{branch.*}` and `{fan_in.*}` templates.

## Compatibility and intentional breaks
- Provider-backed branch groups intentionally stop supporting sync-only providers; they must fail clearly until async provider support is available.
- Branch-group evidence path intentionally changes from root-level `_branch_groups` to workflow-folder `_branch_groups`; tests and any readers must migrate in the same change set.
- Unsupported branch step kinds become hard compile errors instead of running accidentally through existing step machinery.
- Branch-local provider sessions stop surfacing synthetic ids; manifests only record real provider ids returned by the provider.

## Regression controls
- Keep branch-group code behind the existing composite step boundary; avoid spreading branch scheduling logic into `Engine.run()`.
- Land the async provider path before enabling provider-backed concurrent branch execution.
- Keep manifest order declaration-stable even when execution order is concurrent.
- Preserve ordinary non-branch step semantics and route finalization behavior outside branch-group capture mode.
- Update tests and fixtures that currently assert root-level evidence paths or synthetic branch session ids in the same phase that changes those behaviors.

## Validation plan
- Compile-time coverage:
  - name safety, exact placeholder roots, helper placement, fresh-session enforcement, unsupported branch-step kinds, and cache-key/caching behavior.
- Runtime coverage:
  - async concurrency, fail-fast cancellation, capture-only branch routing, shared state/values semantics, workflow-folder evidence writes, branch-local sessions, and deterministic manifests/context docs.
- Strictness coverage:
  - fail if branch-group code imports or uses `concurrent.futures`, `ThreadPoolExecutor`, `Future`, `FIRST_COMPLETED`, `threading.RLock`, or `asyncio.to_thread`.

## Risk register
- Async foundation risk: sync-only provider architecture touches core engine paths.
  - Control: phase async provider protocol and async fake-provider tests before enabling concurrent provider-backed branches.
- Session correctness risk: branch-local fresh sessions can accidentally leak into parent activation.
  - Control: isolate branch session overlay semantics and add explicit parent-store non-activation tests.
- Evidence-path migration risk: existing tests and downstream readers currently assume root-level `_branch_groups`.
  - Control: migrate readers and tests in the same phase as the path change.
- Route-finalization risk: fan-in and capture-mode changes can double-run `on_taken` or finalize twice.
  - Control: centralize capture/finalize routing in `StepDispatcher` and add explicit single-finalization tests.
- Compile-cache risk: partial cache-key coverage can compile stale branch-group internals.
  - Control: bypass cache for branch-group workflows until full coverage is verified.
