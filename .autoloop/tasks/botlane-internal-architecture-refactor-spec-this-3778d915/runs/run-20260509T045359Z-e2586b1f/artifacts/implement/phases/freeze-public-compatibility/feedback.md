# Implement ↔ Code Reviewer Feedback

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: freeze-public-compatibility
- Phase Directory Key: freeze-public-compatibility
- Phase Title: Freeze Public Compatibility
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` `tests/strictness/test_no_compat.py`: the phase added valid freeze assertions and the touched unit suites pass, but the required compatibility baseline is still not validated because `tests/strictness/test_no_compat.py` remains red (`test_removed_compatibility_scan_scope_covers_maintained_tree_only`, `test_explicit_history_allowlist_matches_legacy_docs_inventory`, `test_branding_scan_walks_repo_root_and_skips_only_explicit_history_files`). That leaves this phase short of the "validated baseline for later adapter phases" deliverable even if the failures come from repo-local doc inventory drift rather than the new tests. Minimal fix: either reconcile the current repo-local doc inventory with that strictness suite's allowlists in-scope, or get an explicit clarification that this pre-existing dirty-file failure is excluded from phase acceptance before marking the phase complete.
