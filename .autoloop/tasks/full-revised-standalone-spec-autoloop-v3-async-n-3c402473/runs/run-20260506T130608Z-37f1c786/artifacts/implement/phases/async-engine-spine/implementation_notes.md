# Implementation Notes

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: implement
- Phase ID: async-engine-spine
- Phase Directory Key: async-engine-spine
- Phase Title: Async engine spine
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/providers/rendered.py`
- `tests/contract/test_async_engine_spine.py`

## Symbols touched
- `Engine.run`
- `Engine.run_async`
- `Engine.resume`
- `Engine.resume_async`
- `StepDispatcher.execute`
- `StepDispatcher._call_provider`
- `RenderedLLMProvider._run_turn_async`

## Checklist mapping
- AC-1: `Engine.run(...)` and `Engine.resume(...)` now shell into async cores; the main engine loop awaits `StepDispatcher.execute_async(...)` for provider-backed sequential execution.
- AC-1: sequential sync-only providers remain valid for ordinary `route_mode="finalize"` execution through dispatcher-owned compatibility at the provider call boundary.
- AC-2: Sync runtime wrappers now fail clearly from an active event loop through the shared `run_awaitable_sync(...)` guard.

## Assumptions
- Provider/transport protocol removal is deferred to later phases, so sequential rendered-provider compatibility should be preserved during this spine change.

## Preserved invariants
- Public sequential workflow authoring and runner entrypoints remain unchanged.
- Current sync `LLMProvider` implementations remain valid for ordinary sequential workflows in this phase.
- Python steps and hooks still execute synchronously inside the event loop.
- Branch-group execution remains delegated outside `engine.py`.

## Intended behavior changes
- `Engine.run_async(...)` and `Engine.resume_async(...)` are the authoritative top-level execution cores.
- `StepDispatcher.execute(...)` is now only a sync shell over `execute_async(...)`; provider-backed step execution no longer has a second sync implementation path.
- Async-only enforcement now stays scoped to branch/capture execution; sequential finalize-mode execution preserves current sync-provider compatibility from within the dispatcher path.

## Known non-changes
- Provider protocol/transport protocol cleanup and async-surface renaming are not part of this phase.
- Built-in transport subprocess conversion is unchanged in this phase.

## Expected side effects
- Sequential runs now exercise async provider methods even when called through sync runtime entrypoints.
- Sequential runs with sync-only providers continue to work without restoring sync engine internals.
- Rendered-provider async calls keep temporary sync-transport fallback so existing sync transport stubs still work until the later transport phase lands.

## Validation performed
- `./.venv/bin/python -m pytest tests/contract/test_async_engine_spine.py tests/contract/test_async_step_dispatcher.py tests/contract/test_branch_group_runtime.py::test_parallel_branch_group_rejects_sync_only_provider_for_provider_backed_steps tests/contract/test_engine_contracts.py::test_runtime_extensions_bind_before_workflow_extensions tests/contract/test_engine_contracts.py::test_low_level_engine_resolves_relative_file_prompts_with_filesystem_registry tests/unit/test_simple_surface.py::test_runtime_step_state_restores_built_ins_and_custom_fields_on_resume tests/unit/test_simple_surface.py::test_simple_scoped_item_state_and_step_item_state_restore_on_resume tests/unit/test_provider_boundary_core.py::test_rendered_llm_provider_supports_async_turn_methods tests/unit/test_provider_boundary_core.py::test_rendered_llm_provider_returns_producer_response -q`
- `python3 -m py_compile autoloop/core/engine.py autoloop/core/engine_collaborators.py autoloop/core/providers/rendered.py tests/contract/test_async_engine_spine.py`

## Deduplication / centralization
- Consolidated sync runtime shell behavior onto `run_awaitable_sync(...)` instead of maintaining separate sync engine and sync dispatcher provider execution flows.
- Removed the dead sync provider helper stack from `engine.py` and centralized temporary sequential sync-provider compatibility in `StepDispatcher._call_provider(...)`.
