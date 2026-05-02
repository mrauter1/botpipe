# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: implement
- Phase ID: hook-control-unification
- Phase Directory Key: hook-control-unification
- Phase Title: Hook And Control Unification
- Scope: phase-local authoritative verifier artifact

## Findings

- `IMP-001` `blocking` [autoloop/core/engine.py:1906]: hook-originated pre-provider routes lose the required `candidate_route=None` attribution because `_finalize_step_result(...)` rewrites an explicit `candidate_route=None` to `candidate_event.tag`. A `before` hook that returns `"done"` before any provider/python execution now produces trace/history data that looks like a provider/python candidate route existed, which contradicts the requested hook short-circuit semantics and the implementation notes. Minimal fix: preserve the distinction between “no candidate route existed” and “candidate route omitted” with a sentinel or an explicit finalization struct, and only backfill `candidate_route` for provider/python-originated candidates.

- `IMP-002` `blocking` [autoloop/core/engine_collaborators.py:23-59]: the in-scope collaborator ownership refactor was not implemented. `StepDispatcher.execute`, `RouteFinalizer.finalize`, and `HookRunner.run_after` / `run_route` are still thin pass-through wrappers back into private `Engine` methods, so the new hook/finalization logic remains owned by `Engine` rather than by the requested collaborators. That leaves the tuple/flag-heavy orchestration and ownership scattering in place, which is a direct miss on the phase deliverable and adds avoidable technical debt for the next phases. Minimal fix: move the actual dispatch, hook normalization/execution, and route finalization logic plus the explicit control data structures into these collaborator classes, then keep `Engine` as the orchestration layer.

- `IMP-003` `blocking` [tests/runtime/test_workspace_and_context.py:1571, tests/runtime/test_package_cli.py:141, tests/contract/test_engine_contracts.py:138, tests/unit/test_validation.py:52]: the repo still contains many repo-owned tests, fixtures, and generated snippets that encode removed python-step return forms such as `(state, Event(...))` and `state.model_copy(...), Event(...)`. That means AC-3 is not fully migrated, and the repository will continue to validate or document behavior that this phase explicitly removed once the full test environment is available. Minimal fix: migrate the remaining repo-owned tests/templates/fixtures to mutate `ctx.state` and return direct route/control values only, then add explicit rejection coverage for tuple and `BaseModel` returns so the removed behavior stays removed.
