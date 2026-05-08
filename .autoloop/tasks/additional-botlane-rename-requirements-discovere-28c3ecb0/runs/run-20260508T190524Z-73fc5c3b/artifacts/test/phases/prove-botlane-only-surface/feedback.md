# Test Author ↔ Test Auditor Feedback

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: test
- Phase ID: prove-botlane-only-surface
- Phase Directory Key: prove-botlane-only-surface
- Phase Title: Prove Botlane Only Surface
- Scope: phase-local authoritative verifier artifact

- Added `tests/strictness/test_no_compat.py::test_branding_scan_walks_repo_root_and_skips_only_explicit_history_files` to lock in the repo-root grep proof and explicit `legacy_docs/*.md` history allowlist behavior, then re-ran `tests/strictness/test_no_compat.py` successfully (`41 passed`).

- TST-001 `non-blocking` [test_strategy.md:10-18]
  The AC3 section of the coverage map uses representative examples rather than naming the explicit legacy config-compatibility tests in `tests/runtime/test_provider_policy_config.py`. Coverage is present and this does not block acceptance, but citing one of those config tests directly would make the preserved legacy-read story easier to audit later.
