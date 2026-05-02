# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: implement
- Phase ID: scoped-state-worklists
- Phase Directory Key: scoped-state-worklists
- Phase Title: Scoped State And Worklists
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` `autoloop/core/worklists.py:212-226, 280-290, 392-462`
  `Worklist.refresh()` and `WorklistRuntimeView.validate()` do not actually reload the underlying source. Both paths call `load_items()`, which short-circuits to `ctx._get_cached_worklist_items(...)`; `set_current_status()` then overwrites that cache with `updated_selection.items`, which is only the selected subset, not a fresh full-source snapshot. Concrete failure: if an artifact-backed or other mutable source changes after initial selection, `ctx.current_worklist.refresh()` can return stale items and `validation_error()` can miss removed selected ids or status/title changes instead of raising as the contract requires. This violates AC-3 and the explicit `refresh()` semantics in the phase spec. Minimal fix: centralize full-source reload logic in `Worklist` (for example, an uncached validated reload helper used by `refresh_selection()` and `validation_error()`), keep the cache as a validated full-source snapshot rather than `selection.items`, and add a regression test that mutates the backing source between initial selection and `refresh()` / `validate()`.

- Re-review: `IMP-001` verified fixed in cycle 2. `Worklist` now centralizes cached-vs-forced reload behavior, helper validation and refresh force a source reload, mutable status updates no longer collapse the cache to the selected subset, and targeted regression coverage was added for refresh/validate on mutated backing sources.
