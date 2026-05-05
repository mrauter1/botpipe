# Test Author ↔ Test Auditor Feedback

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: test
- Phase ID: async-step-provider-foundation
- Phase Directory Key: async-step-provider-foundation
- Phase Title: Async Step Foundation
- Scope: phase-local authoritative verifier artifact

- Added regression coverage in `tests/contract/test_async_step_dispatcher.py` for direct async branch-group dispatch inside an active event loop and for the active-loop sync-capture refusal path, including a warning-capture + `gc.collect()` assertion that fails if unawaited-coroutine warnings regress. Revalidated with `.venv/bin/pytest tests/contract/test_async_step_dispatcher.py tests/contract/test_branch_group_runtime.py -q` and the wider phase suite (`77 passed`).
