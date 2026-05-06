# Async-Native Branch-Group Cleanup Plan

## Objective
Make the current async-native branch-group implementation merge-ready with small, local correctness and technical-debt fixes only. Preserve the async engine spine, async step dispatcher, async provider boundary, `asyncio` branch scheduling, branch evidence layout, compile-time rejection rules, and public non-parallel authoring/runtime APIs.

## Scope Boundaries
- In scope: duplicate branch final-state mutation removal, branch-local session isolation, unreachable scoped/worklist runtime removal or assertion, operation-bridge containment, async provider-turn strictness, single-read provider session snapshot cleanup, capture-only branch semantics, single-finalization fan-in behavior, and evidence-write failure gating.
- Out of scope: provider/runtime redesign, sync-provider fallbacks, thread-backed fallbacks, fan-in redesign, worklist fan-out, child-workflow branches/fan-in, branch state merge policy, workspace isolation, async filesystem conversion, and compile-cache redesign beyond the existing safe bypass for branch-group workflows.

## Implementation Slice
This should ship as one coherent implementation phase with small edits concentrated in the existing branch-group runtime, session overlay, provider boundary comments, and targeted tests.

### Workstream 1: Branch Runtime Correctness
- File focus: `autoloop/core/branch_groups/runtime.py`, `autoloop/core/engine_collaborators.py`, `autoloop/core/engine.py`.
- Remove the manual final-state mutations from `BranchGroupRuntime._branch_result_from_step_result(...)`; `RouteFinalizer.capture(...)` remains the sole owner of capture-mode final-state updates.
- Keep branch result construction observational only: derive status/route/destination/question/error, collect artifacts, collect provider-session metadata, write raw-output evidence, and return the branch payload.
- In `_failed_branch_result(...)`, compute `provider_session, provider_sessions = self._provider_session_snapshot(...)` once and reuse both values in the payload.
- Replace the current branch scoped/worklist setup with an internal assertion if `compiled_step.scope_name is not None`; do not initialize branch-local worklist selections, item-state stores, or step-item-state stores for branch execution.
- Preserve `route_mode="capture"` for branch and fan-in execution, and preserve evidence-write-before-fan-in/outcome ordering.

### Workstream 2: Branch-Local Session Isolation
- File focus: `autoloop/core/branch_groups/sessions.py`, `tests/unit/test_branch_group_context_sessions.py`, `tests/contract/test_branch_group_runtime.py`.
- Make `BranchSessionStoreView` branch-local only:
  - `get(...)` must not fall back to parent active keys or parent bindings.
  - `open(...)` must only reuse branch-local bindings/active keys and otherwise create a branch-local binding.
  - `snapshot(...)` must expose branch-local bindings and branch-local active keys only.
- Preserve branch fresh-session key namespacing, but keep new bindings at `session_id=None` until the provider returns a real session id.
- Keep parent session-store active slots and parent bindings unchanged after branch execution and after branch hook snapshot/restore flows.

### Workstream 3: Operation Bridge Containment And Provider Strictness
- File focus: `autoloop/core/providers/rendered.py`, `autoloop/runtime/providers/codex.py`, `autoloop/runtime/providers/claude.py`, `tests/strictness/test_no_compat.py`, `tests/runtime/test_runtime_providers.py`, `tests/unit/test_provider_boundary_core.py`.
- Keep `Engine.run(...)` and `BranchGroupRuntime.run(...)` as outer sync wrappers only; branch/provider execution must continue through async paths without threads.
- Keep the sync operation bridge only for existing non-parallel compatibility. Add or tighten comments so it is explicit that the bridge is not a fallback for branch execution, prompt/produce-verify branches, or provider-backed fan-in.
- Preserve `asyncio.create_subprocess_exec(...)` in provider turn execution paths and keep `subprocess.run(...)` allowed only in explicit CLI capability probing functions such as `--help` checks.
- Keep strictness coverage targeted to provider turn execution and branch-group runtime surfaces so probe-time `subprocess.run(...)` calls do not cause false failures.

### Workstream 4: Regression Test Matrix
- Compile-time coverage:
  - missing provider branch session fails;
  - non-fresh provider branch session fails;
  - explicit fresh provider branch session passes;
  - non-fresh verifier session fails;
  - scoped branch/fan-in, child workflow branch/fan-in, and operation branch/fan-in fail;
  - invalid branch/fan-in placeholder usage and unsafe names fail.
- Runtime coverage:
  - branch result construction does not double-update final step/item state;
  - produce/verify branch `needs_rework` increments `rework_count` exactly once;
  - branch provider lookup never reuses parent active sessions;
  - fresh branch provider requests start with `session_id=None`;
  - parent active sessions remain unchanged after branch execution;
  - distinct branches using the same authored `Session.fresh()` declaration get distinct branch-local session contexts;
  - capture mode records `Goto`, `RequestInput`, and `Fail` without following destinations or running `on_taken`;
  - fan-in finalizes exactly once at the composite boundary;
  - evidence write failures prevent fan-in and mechanical outcomes.
- Strictness/provider coverage:
  - branch-group runtime avoids forbidden thread-backed primitives;
  - provider turn execution avoids `subprocess.run`, `ThreadPoolExecutor`, and `asyncio.to_thread`;
  - async-only provider/transport validation remains enforced;
  - provider-backed branch execution cannot reach `run_operation(...)`.

## Interface And Behavior Invariants
- `BranchGroupRuntime._branch_result_from_step_result(...)` remains a private payload builder, not a runtime-state mutator.
- `BranchSessionStoreView` is a branch overlay, not a parent-session diagnostic view.
- `RouteFinalizer.capture(...)` owns capture-mode final-state updates; composite finalization owns outer fan-in transition finalization.
- Branch and fan-in execution continue to use `StepDispatcher.execute_async(..., route_mode="capture")`.
- Public authoring/runtime entrypoints remain unchanged for ordinary workflows; only internal async-native execution paths are tightened.
- Existing branch evidence paths stay under `{workflow_folder}/_branch_groups/<group_name>/`.

## Regression Risks And Controls
- Duplicate final-state mutation currently risks double-counting `rework_count`/`replan_count`.
  - Control: remove the duplicate writes and add targeted produce/verify branch coverage.
- Session overlay tightening can regress branch/provider session continuity if parent fallback is still relied on implicitly.
  - Control: cover branch-local lookup, hook snapshot/restore, parent-active preservation, and manifest session metadata.
- Fan-in exact-once behavior can regress if nested capture finalization and composite finalization both trigger observable side effects.
  - Control: assert single `on_taken`, single transition recording, single artifact enforcement, and single `RequestInput` mapping at the composite boundary.
- Strictness scans can become noisy if they treat construction-time probing the same as provider turn execution.
  - Control: keep AST/static checks targeted to branch-group runtime and runtime transport turn execution surfaces.

## Validation Order
1. Run branch-group unit/contract coverage around session overlays, capture semantics, fan-in, evidence failures, and shared-state behavior.
2. Run provider boundary and runtime provider suites covering async transport execution and operation-bridge containment.
3. Run strictness scans to confirm no forbidden branch-group/provider execution primitives are reintroduced.
4. If any public non-parallel behavior changes are detected, treat that as a regression unless explicitly required by the authoritative request.

## Rollback
- Revert the branch runtime/session overlay changes as one slice if they disturb parent-session semantics or composite finalization behavior.
- Keep any newly added regression tests; they should remain as guards even if the implementation approach needs to be revised locally.
