# Test Author ↔ Test Auditor Feedback

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: test
- Phase ID: session-state-evidence-correctness
- Phase Directory Key: session-state-evidence-correctness
- Phase Title: Session, State, Evidence
- Scope: phase-local authoritative verifier artifact

## Test Additions

- Added `test_parallel_branch_group_leaves_manifest_provider_session_empty_without_provider_returned_id` in `tests/contract/test_branch_group_runtime.py` to pin the negative path for AC-2: fresh branch requests start with `session_id=None`, and manifests keep `provider_session`/`provider_sessions` empty when the provider never returns a real session id.
- Revalidated the active phase coverage set:
  - `./.venv/bin/pytest tests/contract/test_branch_group_runtime.py`
  - `./.venv/bin/pytest tests/unit/test_branch_group_context_sessions.py`
  - `./.venv/bin/pytest tests/runtime/test_runtime_tracing.py -k branch_group`
