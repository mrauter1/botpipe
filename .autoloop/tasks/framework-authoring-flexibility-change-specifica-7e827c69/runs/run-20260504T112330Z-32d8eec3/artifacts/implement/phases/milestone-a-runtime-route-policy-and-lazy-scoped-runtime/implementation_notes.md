# Implementation Notes

- Task ID: framework-authoring-flexibility-change-specifica-7e827c69
- Pair: implement
- Phase ID: milestone-a-runtime-route-policy-and-lazy-scoped-runtime
- Phase Directory Key: milestone-a-runtime-route-policy-and-lazy-scoped-runtime
- Phase Title: Milestone A Runtime Semantics
- Scope: phase-local producer artifact

## Files changed

- `autoloop/core/engine.py`
- `autoloop/core/worklists.py`
- `autoloop/core/context.py`
- `autoloop/core/sessions.py`
- `tests/contract/test_engine_contracts.py`
- `.../decisions.txt`

## Symbols touched

- `Engine._map_workflow_step_result`
- `Engine._ensure_child_workflow_route_declared`
- `Engine._ensure_worklist_selection`
- `Engine._worklist_source_path`
- `Engine._worklist_source_descriptor`
- `Engine._worklist_selector_details`
- `Engine._worklist_selection_resolution_error`
- `Worklist.ensure_source`
- `Worklist._load_source_items`
- `Worklist._validate_loaded_items`
- `Worklist._cache_loaded_items`
- `_ContextRuntime.emit_worklist_selection_resolved`
- `derive_session_key`

## Checklist mapping

- Milestone A.2 child workflow terminal mapping hardening: completed in `Engine._map_workflow_step_result(...)` and new contract tests.
- Milestone A.3 lazy worklist materialization / first-use observability: completed in `Engine._ensure_worklist_selection(...)`, centralized `Worklist` load helpers, and event payload assertions.
- Milestone A.4 lazy work-item session continuity messaging: completed in `derive_session_key(...)`.
- Milestone A.5 inspection/static graph parity: no code change needed in this turn because existing compiled/static-graph route-policy payloads already matched the requested authored/runtime-control/full-auto split; preserved by keeping route-policy changes runtime-local.

## Intended behavior changes

- Child workflow `FAIL` now maps to `failed` only when the parent step declares `failed`; otherwise runtime raises a targeted route-mapping error.
- Child workflow `AWAIT_INPUT` without a concrete question now maps to `blocked` only when the parent step declares `blocked`; otherwise runtime raises a targeted route-mapping error.
- First-use worklist resolution now runs explicit `ensure -> load -> validate -> select` phases and reports the failing phase, source type, optional path, and selector details.
- Resume restore and worklist refresh now reuse the same source `ensure()` path as first materialization, so scaffold-capable sources can recreate missing backing data consistently.
- `worklist_selection_resolved` events now record `lazy`, `source`, and `current_index`.
- Work-item continuity with no current item now fails with the session slot, worklist, and step name.

## Preserved invariants

- No provider-visible default `blocked` or `failed` routes were reintroduced.
- Default `question` policy handling stayed on the existing runtime-policy path.
- Resume/checkpoint behavior still restores only materialized worklists, keeps missing/null `worklist_selections` compatible, and now honors source `ensure()` during restore.
- Existing custom worklist sources remain compatible because `ensure()` is optional at runtime.

## Known non-changes

- No workflow package code changed.
- No Milestone B helper/effect/prompt work was pulled into this patch.
- No static-graph/inspection payload schema changed beyond preserving the already-landed route-policy model.

## Expected side effects

- Worklist resolution failures will now include more context in their messages, so tests or callers matching exact strings may need updates.
- First-use worklist runtime events include extra fields; existing consumers should remain compatible because the payload is additive.
- Worklist restore/refresh now invoke source `ensure()` when they need to reload backing data after a cache miss or forced reload.

## Validation performed

- `python3 -m py_compile autoloop/core/engine.py autoloop/core/worklists.py autoloop/core/context.py autoloop/core/sessions.py tests/contract/test_engine_contracts.py`
- Attempted targeted `pytest` execution, but the shell environment does not provide `pytest`.
- Attempted direct runtime smoke execution, but the shell environment does not provide installed runtime dependencies such as `pydantic`.

## Assumptions and centralization decisions

- Reused the existing runtime-policy/static-graph foundations instead of adding new inspection abstractions.
- Kept phased first-use error reporting in `Engine._ensure_worklist_selection(...)`, but centralized reusable source ensuring in `Worklist._load_source_items(..., ensure=...)` so restore and refresh do not drift from first-use semantics.
