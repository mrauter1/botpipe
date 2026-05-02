# Test Author ↔ Test Auditor Feedback

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: test
- Phase ID: public-surface-cleanup
- Phase Directory Key: public-surface-cleanup
- Phase Title: Public Surface Cleanup
- Scope: phase-local authoritative verifier artifact

- Added `tests/unit/test_simple_surface.py::test_exported_public_simple_workflows_no_longer_fail_for_legacy_class_handlers` to guard the nine migrated exported `autoloop.simple.Workflow` packages against regressing back to removed class-level `on_outcome` / `on_<step>` surfaces.
- Updated `test_strategy.md` with the behavior-to-test map, preserved invariants, failure-path intent, and the explicit stabilization note that the new regression test tolerates unrelated out-of-scope route-handoff validation failures.
