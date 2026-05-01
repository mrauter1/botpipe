# Implementation Notes

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: implement
- Phase ID: runtime-controls-and-hidden-routes
- Phase Directory Key: runtime-controls-and-hidden-routes
- Phase Title: Runtime Controls And Hidden Routes
- Scope: phase-local producer artifact

## Files changed
- `core/routes.py`
- `core/compiler.py`
- `core/extensions.py`
- `core/context.py`
- `core/stores/protocols.py`
- `core/stores/__init__.py`
- `core/engine.py`
- `core/workflow_capabilities.py`
- `runtime/stores/filesystem.py`
- `runtime/tracing.py`
- `runtime/static_graph.py`
- `runtime/cli.py`
- `runtime/workspace.py`
- `runtime/runner.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_runtime_static_graph.py`
- `tests/runtime/test_runtime_tracing.py`
- `tests/unit/test_primitives_and_stores.py`

## Symbols touched
- `Route.provider_visible`
- `CompiledRoute.provider_visible`
- `PendingInput`
- `Context.input_response`
- `ChildWorkflowResult.checkpoint`
- `HookRouteRedirect.redirect_index`
- `StepFinish.runtime_control`
- `StepFinish.target_step`
- `StepFinish.terminal`
- `StepFinish.provider_attributable`
- `StepFinish.source_hook`
- `StepFinish.source_phase`
- `_DirectRuntimeControl.handoff`
- `Engine._normalize_hook_result`
- `Engine._run_after_hook`
- `Engine._run_route_hook`
- `Engine._finalize_step_result`
- `Engine._schedule_direct_control_handoffs`
- `Engine._resume_input_response`
- `Engine._provider_available_routes_for_step`

## Checklist mapping
- Phase 2 / hidden routes: compiled route visibility added and provider-facing route rendering now filters hidden step routes while topology/capability/static-graph outputs keep them.
- Phase 2 / runtime controls: hook normalization accepts `RequestInput`, `Goto`, and `Fail`, validates them, checkpoints them, and executes them without mutating built-in route-finalization fields.
- Reviewer follow-up / `IMP-001`: candidate-free `after_producer` hooks can now emit direct runtime controls and short-circuit verifier dispatch without pretending a route was taken.
- Reviewer follow-up / `IMP-002`: direct `Goto` now preserves `handoff` for the target provider step and persists a checkpoint at the destination cursor before the next step dispatch starts.
- Phase 2 / redirect chaining: route-tag and `Event` redirects continue through `on_taken`; direct controls stop chaining and record hook source metadata.
- Phase 2 / truthful built-ins: `last_route` and related runtime-owned route fields now update only after successful route-based finalization.
- Phase 3 dependency slice needed for AC-1: pending-input checkpoint/read-path and resume exposure on `ctx.input_response` landed here because direct `RequestInput` execution is incomplete without it.

## Assumptions
- Global runtime control routes such as `"question"`, `"blocked"`, and `"failed"` remain provider-visible unless a later phase explicitly changes that contract; this phase filters only hidden declared step/global routes, not the runtime-injected provider control surface.
- Legacy persisted `pending_question` data remains readable for compatibility, but canonical runtime writes use `pending_input`.

## Preserved invariants
- Direct runtime controls do not pretend a route was finalized and do not update built-in route state.
- Hook failures, route-hook failures, and runtime-control validation failures preserve current custom state/session mutations in the checkpointed state instead of restoring snapshots.
- Hidden routes stay legal runtime targets and topology entries.

## Intended behavior changes
- Hooks may return `RequestInput`, `Goto`, or `Fail` directly.
- `after_producer` direct controls now execute without invoking verifier.
- `Goto(..., handoff=...)` now carries handoff text to the next provider-mediated target step.
- Non-terminal direct `Goto` writes a checkpoint with the destination cursor before the next step begins.
- Provider-facing route choices omit hidden routes.
- Resume can validate and expose supplied input through `ctx.input_response`.
- Traces/topology/metadata now carry runtime-control and route-visibility details needed by later phases.

## Known non-changes
- This phase does not remove remaining internal/core hook plumbing or extract engine collaborators.
- Structured `FailureContext`/`StepExecutionError` replacement is deferred to the later structured-failures phase.
- Legacy `pending_question` fields are still carried on persisted models for read compatibility.

## Expected side effects
- Provider contract tests that asserted full route sets now need to account for hidden-route filtering while still allowing runtime-injected provider controls.
- Child workflow results now carry checkpoint state so parent workflow mapping can inspect pending input terminals.

## Validation performed
- `python3 -m py_compile core/engine.py tests/contract/test_engine_contracts.py`
- `./.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -k 'after_producer_goto_short_circuits_verifier or on_taken_goto_handoff_reaches_target_provider_step or on_taken_goto_checkpoints_target_before_next_step_dispatch or on_taken_goto_skips_declared_route_target_and_emits_runtime_control'`
- `./.venv/bin/python -m pytest tests/unit/test_primitives_and_stores.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_runtime_tracing.py tests/contract/test_engine_contracts.py`
- Result: `165 passed`.

## Deduplication / centralization
- Provider-visible route filtering is centralized through engine/provider helper paths plus compiled route metadata instead of duplicating separate hidden-route models.
- Pending-input serialization/deserialization is centralized in checkpoint store helpers and engine resume helpers.
