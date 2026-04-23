# Test Author ↔ Test Auditor Feedback

- Task ID: recursive-framework-evolution-20260423t120129-bootstrap
- Pair: test
- Phase ID: public-cli-provider-contract
- Phase Directory Key: public-cli-provider-contract
- Phase Title: Remove Public Provider Factory Surfaces
- Scope: phase-local authoritative verifier artifact

- Added provider-contract regression coverage in `tests/runtime/test_provider_backends.py` for file-generic routing to the final selected provider, later file-specific precedence over earlier generic config, and CLI last-wins overrides over file config.
- Kept user-facing CLI coverage in `tests/runtime/test_package_cli.py` focused on the public contract: mutating help shows `--provider`, the removed public flag is parser-rejected, and the non-public injected seam still succeeds.
- Validation in this environment: `./.venv/bin/python -m pytest tests/runtime/test_provider_backends.py tests/runtime/test_package_cli.py tests/runtime/test_workspace_and_context.py tests/runtime/test_compatibility_runtime.py -k 'not recursive_wrapper_targets_the_package_cli_contract'`.

- TST-001 | non-blocking | Audit closeout
  Coverage is sufficient for this phase scope. The tests exercise the public help surface, the removed-flag failure path, the preserved non-public injection seam, the final-provider merge order across file and CLI layers, and the preserved non-CLI runner surface without relying on flaky environment assumptions. No remaining audit findings were identified.
