# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: implement
- Phase ID: worklists
- Phase Directory Key: worklists
- Phase Title: Worklists And Scoped Steps
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [core/worklists.py:167](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/worklists.py:167) [core/worklists.py:180](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/worklists.py:180) [core/worklists.py:222](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/worklists.py:222): worklist items are never validated for unique `id` values. Duplicate ids silently collapse in the `{item.id: item}` maps used by restore/refresh, selectors, status updates, and `Continuity.work_item(...)`, so scoped execution can resume or mutate the wrong item with no error. Minimal fix: centralize duplicate-id validation in the shared worklist load/materialization path and fail fast before selections, snapshots, or session keys are derived.

- IMP-002 `blocking` [core/engine.py:834](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/engine.py:834) [core/validation.py:677](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/validation.py:677): `Advance(worklist)` currently self-loops the source step whenever the selection still has a current item, even if that step is not scoped to the referenced worklist. A workflow like `Route.to(SUCCESS, Advance(gates))` on an unscoped `LLMStep` runs the same step multiple times (`history == ('publish', 'publish')`) with no item context, which introduces hidden iteration outside the scoped-step model promised by this phase. Minimal fix: validate that `Advance(worklist)` is only used from a step scoped to that same worklist, or guard `_advance_worklist(...)` to raise instead of re-entering unscoped/mismatched steps; the rule should live in shared validation so compile-time and runtime semantics stay aligned.

- Review cycle 2: no remaining blocking or non-blocking findings in phase scope. `IMP-001` and `IMP-002` are resolved by central load-time duplicate-id rejection in `Worklist.load_items(...)`, matching `Advance(...)` compile-time validation, and the runtime guard in `_advance_worklist(...)`. Focused verifier validation passed: `120 passed`.
