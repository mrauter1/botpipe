# Test Author ↔ Test Auditor Feedback

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: test
- Phase ID: rewrite-runtime-and-workspace-identity
- Phase Directory Key: rewrite-runtime-and-workspace-identity
- Phase Title: Rewrite Runtime And Workspace Identity
- Scope: phase-local authoritative verifier artifact

- Added focused regression coverage for Botlane CLI branding and for runtime-config fallback across canonical vs legacy global config directories, alongside the already-landed workspace-root and mixed-root resume tests for this phase.

- `TST-001` `blocking` [tests/runtime/test_runtime_cli_metadata_integration.py:410-423] The existing CLI metadata integration suite still asserts the opposite of the confirmed Botlane help contract: `test_cli_workflows_list_help_describes_package_and_dot_autoloop_roots` requires `.botlane/workflows/` to be absent from help output even though this phase explicitly requires workspace-loading help to advertise `.botlane/workflows/`. That leaves the request-relevant test surface internally contradictory: the new `test_cli_help_uses_botlane_identity` expects Botlane help text, while this older test still encodes the legacy expectation and will fail or pressure future edits back toward stale wording. Minimal fix: update or replace the stale CLI metadata integration test so it asserts Botlane wording and `.botlane/workflows/` presence, and remove any remaining legacy help expectation from that file.
