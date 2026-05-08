# Implement ↔ Code Reviewer Feedback

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: implement
- Phase ID: rewrite-schemas-workflows-and-fixtures
- Phase Directory Key: rewrite-schemas-workflows-and-fixtures
- Phase Title: Rewrite Schemas Workflows And Fixtures
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | `tests/strictness/test_no_compat.py`, `tests/runtime/test_workspace_and_context.py:44`, `tests/runtime/test_wheel_packaging_smoke.py:91`, `tests/unit/stdlib/test_authoring_helpers.py:277` and many other maintained tests still contain raw `autoloop` / `.autoloop` / `autoloop_optimizer` strings, while the new strictness proof explicitly scopes itself away from the maintained test tree. That contradicts the explicit request and the run decisions requiring the final grep gate to cover maintained tests, docs, examples, and embedded fixture strings with only minimal historical allowlists. Concrete failure: a repo-wide grep over maintained files still returns live Autoloop branding across tests, so the phase does not yet satisfy the requested negative strictness proof or the “rewrite embedded source strings inside tests” requirement. Minimal fix: widen the strictness scan back to maintained tests (or add an equivalent repo-wide gate) and rewrite or obfuscate the remaining intentional legacy/negative-test literals so they do not appear as raw contiguous Autoloop tokens outside explicit historical allowlists.
