# Test Author ↔ Test Auditor Feedback

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: test
- Phase ID: engine-runner-observability-binding
- Phase Directory Key: engine-runner-observability-binding
- Phase Title: Engine And Runner Binding
- Scope: phase-local authoritative verifier artifact

- Added integration coverage for paused git-tracked runs staying clean across resume (`tests/runtime/test_optional_extensions.py`), alongside the existing runtime git/tracing/contract coverage. Validated with `.venv/bin/python -m pytest tests/runtime/test_optional_extensions.py tests/runtime/test_runtime_git_tracking.py tests/runtime/test_runtime_tracing.py tests/contract/test_engine_contracts.py -q` (`91 passed`).

- TST-001 | blocking | Missing AC-5 mixed-mode resume coverage
  The updated tests still do not cover the phase-contract behavior where a previously git-tracked run is resumed with tracking disabled, or the inverse case where an earlier untracked segment is resumed with tracking enabled from that point onward. A repo-wide grep across the runtime/contract tests shows no assertions on the required warning payload or the mixed-mode `run.json.git_tracking` behavior for resume config mismatches. That leaves the most phase-specific part of AC-5 vulnerable to silent regression even though pause cleanliness and CLI wiring are now covered. Minimal correction: add integration tests that pause a run, resume it once with git tracking disabled and assert the warning is persisted without backfilling, then cover the inverse case where a previously untracked paused run resumes with tracking enabled and starts recording git metadata only from the resume point.
