# Test Author ↔ Test Auditor Feedback

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: test
- Phase ID: runtime-observability-persistence
- Phase Directory Key: runtime-observability-persistence
- Phase Title: Runtime Observability Persistence
- Scope: phase-local authoritative verifier artifact

- Added focused regression coverage in `tests/runtime/test_runtime_tracing.py` for three phase-specific gaps: static graph persistence even when tracing is disabled, ignore-mode degradation on post-init trace write failures, and raw-only resume sequence fallback when JSONL evidence is missing or malformed.
- Added terminal/fatal observability coverage in `tests/runtime/test_runtime_tracing.py` and `tests/runtime/test_runtime_git_tracking.py`, including terminal trace payloads, fatal trace error payloads, and fatal git-tracking commit metadata persistence.
- Updated `test_strategy.md` with an explicit acceptance-criteria-to-test map, preserved invariants, edge cases, failure paths, flake controls, and the current environment limitation that `pytest` is unavailable here.
- Validation performed: `python3 -m py_compile tests/runtime/test_runtime_tracing.py tests/runtime/test_runtime_git_tracking.py` passed; `python3 -m pytest --version` failed with `/usr/bin/python3: No module named pytest`.

### TST-001 — blocking — terminal and fatal observability branches still have no phase-local regression coverage
The updated suite strengthens step-level tracing and resume behavior, but it still does not exercise `RuntimeTraceWriter.terminal()`, `RuntimeTraceWriter.fatal()`, or `RuntimeGitTracker.on_fatal()`. Those branches are explicitly part of the requested runtime-owned observability API and are the highest-risk evidence path when a run ends abnormally. A concrete missed-regression scenario is a future change dropping fatal `error_type` / `error_message`, omitting terminal outcome/state payloads, or failing to record the fatal git commit metadata while the current tests still pass because they only cover `after_run()` success and step-level trace writes. Minimal correction: add focused tests for enabled terminal trace emission, enabled fatal trace emission, and fatal git-tracking commit metadata persistence, including the expected event types and required fields.

- Addressed `TST-001` by adding `test_runtime_trace_terminal_writes_terminal_event_payload`, `test_runtime_trace_fatal_writes_error_payload`, and `test_git_tracking_fatal_commits_and_records_run_metadata`.
