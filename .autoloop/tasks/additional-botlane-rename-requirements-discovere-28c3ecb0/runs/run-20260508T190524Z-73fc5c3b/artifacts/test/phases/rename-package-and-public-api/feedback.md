# Test Author ↔ Test Auditor Feedback

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: test
- Phase ID: rename-package-and-public-api
- Phase Directory Key: rename-package-and-public-api
- Phase Title: Rename Package And Public API
- Scope: phase-local authoritative verifier artifact

- Added phase-local regression coverage for the bundled workflow rename: the live package catalog must expose `botlane_v1` / `botlane-v1` and reject `autoloop_v1`, and the built wheel must import `botlane.workflows.botlane_v1` while leaving `botlane.workflows.autoloop_v1` absent.
