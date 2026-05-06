# Test Author ↔ Test Auditor Feedback

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: test
- Phase ID: policy-claude-regression
- Phase Directory Key: policy-claude-regression
- Phase Title: Claude Emission And Regression Sweep
- Scope: phase-local authoritative verifier artifact

## Cycle 1 Summary

- Added focused Claude regression coverage for the new `--add-dir` capability requirement and for policy-backed legacy-bypass execution so the earlier transport regression cannot reappear silently.
- Confirmed the updated Claude emitter/transport/config path with:
  - `.venv/bin/python -m pytest tests/runtime/test_runtime_providers.py tests/runtime/test_provider_policy_emitters.py tests/runtime/test_provider_policy_config.py tests/runtime/test_provider_backends.py -q`
  - `.venv/bin/python -m pytest tests/runtime/test_provider_policy_steps.py -q`

## Findings

- `TST-001` `blocking` [tests/runtime/test_runtime_providers.py, tests/runtime/test_provider_policy_config.py]
  The new coverage proves the positive legacy path (`permission_strategy=bypass` still reaches `--dangerously-skip-permissions`) and the config-layer negative path (explicit policy beats the compatibility mapping), but it still does not exercise the runtime negative path where a safe explicit policy is executed while `provider.claude.permission_strategy=bypass` remains configured. That leaves the exact seam that regressed earlier partially unguarded: a future transport change could reintroduce a config-driven `--dangerously-skip-permissions` branch for policy-backed turns, silently widening an explicit safe policy, and the current config-only negative test would still pass. Minimal fix: add a runtime-provider test that runs a policy-backed Claude turn with `permission_strategy=bypass` plus an explicit safe policy and asserts the emitted command omits `--dangerously-skip-permissions`.
