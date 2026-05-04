# Implement ↔ Code Reviewer Feedback

- Task ID: framework-authoring-flexibility-change-specifica-7e827c69
- Pair: implement
- Phase ID: milestone-a-runtime-route-policy-and-lazy-scoped-runtime
- Phase Directory Key: milestone-a-runtime-route-policy-and-lazy-scoped-runtime
- Phase Title: Milestone A Runtime Semantics
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` — [autoloop/core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/engine.py:1995) now calls source `ensure()` only from `Engine._ensure_worklist_selection(...)`, but [autoloop/core/worklists.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/worklists.py:272) `restore_selection(...)` and [autoloop/core/worklists.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/worklists.py:314) `refresh_selection(...)` still reload through `load_items()` / `reload_items()` without any ensure step. A scaffold-capable source that can recreate missing backing data will still hard-fail on resume or refresh if its backing file is absent, which violates AC-3 and the run decision that missing-source behavior must remain source-policy-driven on lazy worklist paths. Minimal fix: centralize `ensure` into the shared load/reload/restore path used by fresh materialization, restore, and refresh, rather than applying it only in the engine’s first-materialization branch.
- IMP-002 `non-blocking` — The implementation notes confirm only `py_compile` ran; the targeted contract/runtime suites required by AC-4 were not executed because the environment lacks `pytest` and installed runtime deps. Re-run the Milestone A contract/runtime suites once dependencies are available before merging.
- IMP-003 `non-blocking` — Cycle 2 resolves `IMP-001` by centralizing source `ensure()` through the shared worklist load path and by adding resume/refresh regression tests for ensure-capable sources. The remaining review caveat is still the environment-level validation gap from `IMP-002`.
