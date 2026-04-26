# Test Strategy

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: test
- Phase ID: runtime-observability-persistence
- Phase Directory Key: runtime-observability-persistence
- Phase Title: Runtime Observability Persistence
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 Git tracking records `commit_after_*` only in `git_tracking.jsonl`, while trace records keep `commit_before_step`
  - `tests/runtime/test_runtime_git_tracking.py::test_git_tracking_run_policy_commits_at_run_boundaries`
  - `tests/runtime/test_runtime_git_tracking.py::test_git_tracking_step_policy_commits_after_each_step`
  - `tests/runtime/test_runtime_git_tracking.py::test_git_tracking_jsonl_records_step_commit_metadata`
  - `tests/runtime/test_runtime_git_tracking.py::test_git_tracking_fatal_commits_and_records_run_metadata`
  - `tests/runtime/test_runtime_tracing.py::test_trace_events_include_commit_before_step_not_commit_after_step`
- AC-2 Runtime-owned raw outputs and trace refs are persisted with stable metadata
  - `tests/runtime/test_runtime_tracing.py::test_runtime_trace_writes_pair_raw_producer_and_verifier_files`
  - `tests/runtime/test_runtime_tracing.py::test_runtime_trace_writes_llm_raw_file`
  - `tests/runtime/test_runtime_tracing.py::test_runtime_trace_records_raw_file_sha256_and_bytes`
  - `tests/runtime/test_runtime_tracing.py::test_runtime_trace_records_provider_usage_when_available`
- AC-3 Resume appends evidence and never overwrites raw files
  - `tests/runtime/test_runtime_git_tracking.py::test_git_tracking_resume_appends_without_overwriting`
  - `tests/runtime/test_runtime_tracing.py::test_trace_resume_uses_next_sequence_and_never_overwrites_raw_files`
  - `tests/runtime/test_runtime_tracing.py::test_trace_resume_falls_back_to_raw_sequence_when_jsonl_is_missing_or_malformed`

## Additional changed behavior coverage

- Runtime git tracking failure-mode degrade path
  - `tests/runtime/test_runtime_git_tracking.py::test_git_tracking_dirty_repo_failure_mode_ignore_disables_tracking_for_run`
  - `tests/runtime/test_runtime_git_tracking.py::test_git_tracking_runtime_failure_mode_ignore_disables_tracking_after_commit_error`
- Runtime tracing initialization and append failure-mode degrade path
  - `tests/runtime/test_runtime_tracing.py::test_runtime_trace_failure_mode_ignore_swallows_initialization_errors`
  - `tests/runtime/test_runtime_tracing.py::test_runtime_trace_failure_mode_ignore_swallows_step_write_errors`
- Terminal and fatal runtime observability payloads
  - `tests/runtime/test_runtime_tracing.py::test_runtime_trace_terminal_writes_terminal_event_payload`
  - `tests/runtime/test_runtime_tracing.py::test_runtime_trace_fatal_writes_error_payload`
  - `tests/runtime/test_runtime_git_tracking.py::test_git_tracking_fatal_commits_and_records_run_metadata`
- Static step graph persistence from the runtime-owned path
  - `tests/runtime/test_runtime_tracing.py::test_runtime_trace_initialization_persists_static_step_graph`
  - `tests/runtime/test_runtime_tracing.py::test_runtime_trace_disabled_still_persists_static_step_graph`
  - `tests/runtime/test_runtime_static_graph.py::test_static_step_graph_written_for_run`
  - `tests/runtime/test_runtime_static_graph.py::test_static_step_graph_includes_step_kind_prompts_routes_and_artifact_names`
  - `tests/runtime/test_runtime_static_graph.py::test_static_step_graph_includes_route_contracts_and_schema_presence`

## Preserved invariants checked

- Disabled git tracking still does not require a repository.
- Dirty repositories still fail before run workspace creation unless ignore mode is explicitly requested.
- `run.json.git_tracking` remains summary-only while `git_tracking.jsonl` stays the append-only step/event log.
- Disabling tracing suppresses `trace.jsonl` writes but does not suppress static graph persistence.
- Trace payloads exclude hidden raw outcome text and `commit_after_step`.

## Edge cases

- No-op step commits return the current head without creating an empty commit.
- Resume sequence discovery tolerates malformed JSONL lines and can recover from raw filenames alone.
- Ignore-mode tracing handles both constructor-time failures and later append failures.

## Failure paths

- Missing git repository or dirty workspace raises under the default git-tracking failure mode.
- Raw-output filename collisions raise `RuntimeTraceError` instead of overwriting prior evidence.
- Runtime git/tracing ignore modes degrade to metadata or warning updates instead of aborting the run.
- Fatal run termination still records runtime-owned trace/git evidence instead of silently dropping the final error snapshot.

## Flake-risk controls

- Git-tracking tests use temporary repositories with local `user.name` and `user.email` configured in-test.
- Runtime tracing tests use temp directories and monkeypatched call sites only; no network, timing, or external process dependencies.

## Known gaps

- Full `pytest` execution is not possible in this environment because `pytest` is not installed, so validation here is limited to static review and `python3 -m py_compile tests/runtime/test_runtime_tracing.py tests/runtime/test_runtime_git_tracking.py`.
- Runner/engine integration coverage remains deferred to the later observability binding phase and is intentionally out of scope here.
