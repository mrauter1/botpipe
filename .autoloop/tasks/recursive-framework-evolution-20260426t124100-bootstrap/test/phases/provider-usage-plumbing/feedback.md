# Test Author ↔ Test Auditor Feedback

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: test
- Phase ID: provider-usage-plumbing
- Phase Directory Key: provider-usage-plumbing
- Phase Title: Provider Usage Plumbing
- Scope: phase-local authoritative verifier artifact

- Added coverage for typed usage defaults, fake/rendered provider passthrough, Codex/Claude usage extraction, `StepFinish.provider_usage` exposure for pair/llm/system steps, and the persisted-session invariant that transient usage blobs are stripped from `provider_metadata`.
- Validated with `./.venv/bin/python -m pytest tests/runtime/test_compatibility_runtime.py tests/runtime/test_provider_backends.py tests/unit/test_provider_boundary_core.py tests/runtime/test_runtime_providers.py tests/contract/test_engine_contracts.py -q` -> `161 passed`.
- TST-000 | non-blocking | No audit findings. The phase-local suite covers the requested provider-usage behavior at the right layers, protects the preserved compatibility invariant around persisted session metadata, exercises relevant failure paths, and uses deterministic mocked-provider setup without flake-prone timing or network assumptions.
