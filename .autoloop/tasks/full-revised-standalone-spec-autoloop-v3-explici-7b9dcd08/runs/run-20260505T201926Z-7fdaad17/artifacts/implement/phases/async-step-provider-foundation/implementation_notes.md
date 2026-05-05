# Implementation Notes

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: implement
- Phase ID: async-step-provider-foundation
- Phase Directory Key: async-step-provider-foundation
- Phase Title: Async Step Foundation
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/providers/protocols.py`
- `autoloop/core/providers/rendered.py`
- `autoloop/core/providers/fake.py`
- `autoloop/core/providers/__init__.py`
- `autoloop/runtime/providers/codex.py`
- `autoloop/runtime/providers/claude.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/branch_groups/context.py`
- `autoloop/core/branch_groups/runtime.py`
- `tests/unit/test_provider_boundary_core.py`
- `tests/runtime/test_runtime_providers.py`
- `tests/contract/test_branch_group_runtime.py`
- `tests/contract/test_async_step_dispatcher.py`

## Symbols touched
- `AsyncLLMProvider`, `AsyncProviderTransport`, `supports_async_llm_provider`, `supports_async_provider_transport`
- `RenderedLLMProvider.run_*_async`
- `ScriptedLLMProvider.run_*_async`
- `CodexTransport.run_turn_async`
- `ClaudeTransport.run_turn_async`
- `StepDispatcher.execute_async`
- `run_awaitable_sync`
- `RouteFinalizer.capture`
- `BranchGroupRuntime.run_async`
- `BranchGroupRuntime._ensure_async_provider_support`
- `StateCell.set`

## Checklist mapping
- Plan item `async provider protocol and adapter updates`: completed via async provider/transport protocols, fake provider async surface, and async Codex/Claude transports.
- Plan item `async step-execution collaborator path with capture/finalize modes`: completed via `StepDispatcher.execute_async(...)` and `RouteFinalizer.capture(...)`.
- Phase acceptance `AC-1`: covered by async branch-group provider execution tests and async transport/provider tests.
- Phase acceptance `AC-2`: covered by direct `execute_async(..., route_mode="capture")` contract coverage.
- Phase acceptance `AC-3`: covered by sync-only provider rejection in branch-group runtime tests.
- Reviewer finding `IMP-001`: resolved by routing async branch-group execution through `BranchGroupRuntime.run_async(...)` and adding active-loop regression coverage.

## Assumptions
- Keeping sync transport methods for outer callers is acceptable in this phase as long as branch-group capture paths use the new async provider surface.
- Sequential branch iteration is an acceptable temporary bridge for this phase because parallel branch scheduling is explicitly out of scope here.
- Keeping sync composite-step execution as a thin wrapper around the new async branch-group path is acceptable in this phase because top-level engine entrypoints remain sync.

## Preserved invariants
- Top-level engine entrypoints remain sync.
- Provider transport parsing, session binding, and metadata shapes remain unchanged for existing sync callers.
- Branch-group composite routing still finalizes at the composite boundary; nested branch and fan-in steps now capture routes instead of finalizing them directly.
- Branch-group scheduling remains sequential in this phase; only the nested step execution path became event-loop-safe for async callers.

## Intended behavior changes
- Provider-backed branch steps and provider-backed fan-in now require async provider methods at runtime.
- Branch-group nested step execution uses capture mode so route `on_taken` hooks and downstream route following are skipped inside branches and fan-in.
- Branch-group runtime no longer uses thread-backed execution or lock-wrapped shared values in this phase path.
- `StepDispatcher.execute_async(...)` now executes `branch_group` composite steps through an awaitable runtime path instead of falling back into the sync capture bridge.
- Sync capture wrappers now reject active-loop use before creating coroutine objects, avoiding unawaited-coroutine warnings on refusal.

## Known non-changes
- Branch-group scheduling is still sequential; no `asyncio.Task`/`Semaphore` scheduler is introduced in this phase.
- Branch session overlay semantics and workflow-folder evidence rooting are deferred to later phases.
- Sync top-level step execution still uses the existing sync provider path unless a caller opts into `execute_async(...)` or branch-group capture mode.

## Expected side effects
- Existing sync provider backend tests continue to exercise the unchanged sync transport methods.
- New async transport methods are available for branch-group runtime and future async engine work without changing current outer CLI invocation semantics.
- Async callers can now await provider-backed branch-group composite steps without degrading into recorded branch failures or leaking coroutine warnings.

## Validation performed
- `python3 -m py_compile autoloop/core/providers/protocols.py autoloop/core/providers/rendered.py autoloop/core/providers/fake.py autoloop/core/providers/__init__.py autoloop/runtime/providers/codex.py autoloop/runtime/providers/claude.py autoloop/core/engine_collaborators.py autoloop/core/branch_groups/context.py autoloop/core/branch_groups/runtime.py tests/unit/test_provider_boundary_core.py tests/runtime/test_runtime_providers.py tests/contract/test_branch_group_runtime.py tests/contract/test_async_step_dispatcher.py`
- `.venv/bin/pytest tests/unit/test_provider_boundary_core.py tests/runtime/test_runtime_providers.py tests/contract/test_branch_group_runtime.py tests/contract/test_async_step_dispatcher.py -q`
- `.venv/bin/pytest tests/contract/test_async_step_dispatcher.py tests/contract/test_branch_group_runtime.py -q`

## Deduplication / centralization
- Capture/finalize switching is centralized in `StepDispatcher._complete_route(...)` instead of duplicating route-mode branching across all nested call sites.
- Async provider capability checks are centralized through `supports_async_llm_provider(...)` and `StepDispatcher._require_async_provider(...)`.
- Sync branch-group execution now delegates to one async `BranchGroupRuntime.run_async(...)` implementation instead of maintaining separate nested-step execution behavior for sync and async composite callers.
