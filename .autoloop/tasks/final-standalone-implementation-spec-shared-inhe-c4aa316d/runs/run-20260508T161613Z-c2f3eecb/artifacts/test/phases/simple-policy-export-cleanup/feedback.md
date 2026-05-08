# Test Author ↔ Test Auditor Feedback

- Task ID: final-standalone-implementation-spec-shared-inhe-c4aa316d
- Pair: test
- Phase ID: simple-policy-export-cleanup
- Phase Directory Key: simple-policy-export-cleanup
- Phase Title: Clean Up Simple Policy Exports
- Scope: phase-local authoritative verifier artifact

- Added `test_simple_declarations_accept_provider_policy_and_none` in `tests/unit/test_simple_policy.py` to close the remaining AC-3 coverage gap for direct `ProviderPolicy` and explicit `None`.
- Re-ran the required phase commands: `tests/unit/test_simple_policy.py` passed with 8 tests; the combined `test_simple_surface.py`, `test_policy.py`, `test_sdk_policy.py`, and `test_sdk_facade.py` command passed with 155 tests.
- `TST-000` `non-blocking` No actionable audit findings in phase scope. The test suite now covers the removed `autoloop.simple` exports, the preserved canonical `PolicyInput` exports, and all accepted simple policy inputs (`Policy`, `ProviderPolicy`, `ProviderPolicyOverride`, and `None`) with deterministic checks.
