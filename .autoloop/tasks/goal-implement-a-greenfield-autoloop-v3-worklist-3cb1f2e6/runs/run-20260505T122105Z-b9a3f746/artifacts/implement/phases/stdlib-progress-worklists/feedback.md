# Implement ↔ Code Reviewer Feedback

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: implement
- Phase ID: stdlib-progress-worklists
- Phase Directory Key: stdlib-progress-worklists
- Phase Title: Add canonical progress JSON worklists
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — [autoloop/stdlib/worklists.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/stdlib/worklists.py) `ProgressJsonCollectionSource._normalize_fallback_payload` / `ensure`
  The fallback materialization path writes duplicate item ids to disk without rejecting them first. A fallback such as `{"items": [{"id": "p1", ...}, {"id": "p1", ...}]}` passes through `_normalize_fallback_payload`, is persisted by `ensure()` or `load(write_fallback=True)`, and only fails later on a subsequent `load()` when `_items_from_payload()` detects the duplicate. That leaves an invalid canonical board on disk and violates AC-3’s requirement that fallback materialization produce a valid canonical progress board. Minimal fix: validate duplicate ids during fallback normalization before any write, ideally by centralizing the duplicate-id check used by load/materialization and adding a regression test for duplicate-id fallbacks.
