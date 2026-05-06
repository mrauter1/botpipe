# Implement ↔ Code Reviewer Feedback

- Task ID: revised-standalone-spec-second-pass-cleanup-for-dd5e2acb
- Pair: implement
- Phase ID: async-branch-group-cleanup
- Phase Directory Key: async-branch-group-cleanup
- Phase Title: Async Branch-Group Cleanup
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [tests/strictness/test_no_compat.py::_runtime_provider_turn_execution_failures]: the new provider-turn strictness scanner does not catch directly imported forbidden executor primitives inside `run_turn`. A concrete probe with `from concurrent.futures import ThreadPoolExecutor` plus `return ThreadPoolExecutor()` in `run_turn` produces `[]`, so the required strictness coverage can pass even if a thread-backed fallback is reintroduced in provider turn execution. Minimal fix: extend `_runtime_provider_turn_execution_failures(...)` to treat resolved call names ending in `.ThreadPoolExecutor`, `.Future`, and `.FIRST_COMPLETED` the same way it already handles attribute access, and add probe tests for the direct-import call forms.
