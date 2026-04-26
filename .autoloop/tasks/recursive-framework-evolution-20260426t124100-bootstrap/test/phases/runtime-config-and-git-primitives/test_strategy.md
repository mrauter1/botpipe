# Test Strategy

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: test
- Phase ID: runtime-config-and-git-primitives
- Phase Directory Key: runtime-config-and-git-primitives
- Phase Title: Runtime Config And Git Primitives
- Scope: phase-local producer artifact

## Behavior Coverage Map

- AC-1 Runtime config defaults and validation
  - `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_defaults_enable_git_tracking_and_tracing`
  - `tests/runtime/test_provider_backends.py::test_parse_runtime_config_rejects_invalid_git_commit_policy`
  - `tests/runtime/test_provider_backends.py::test_parse_runtime_config_rejects_non_mapping_git_tracking_section`
  - `tests/runtime/test_provider_backends.py::test_parse_runtime_config_rejects_non_mapping_tracing_section`
  - `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_merges_runtime_file_overrides_and_preserves_defaults`

- AC-2 CLI overrides deterministically control runtime git/tracing policy
  - `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_no_git_disables_git_tracking`
  - `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_git_commit_policy_off_disables_git_tracking`
  - `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_git_commit_policy_run_enables_run_policy`
  - `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_git_commit_policy_step_enables_step_policy`
  - `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_no_trace_disables_tracing`
  - `tests/runtime/test_package_cli.py::test_cli_mutating_command_help_exposes_provider_and_hides_provider_factory`
  - `tests/runtime/test_package_cli.py::test_cli_mutating_commands_route_runtime_git_and_trace_overrides_through_typed_config`

- AC-3 Git commit-all helpers snapshot the full workspace without empty commits
  - `tests/unit/test_stdlib_and_extensions.py::test_git_repo_status_porcelain_and_is_dirty_report_workspace_changes`
  - `tests/unit/test_stdlib_and_extensions.py::test_git_repo_commit_all_tracks_untracked_files`
  - `tests/unit/test_stdlib_and_extensions.py::test_git_repo_commit_all_stages_tracked_and_untracked_workspace_changes`
  - `tests/unit/test_stdlib_and_extensions.py::test_git_repo_commit_all_returns_current_head_without_empty_commit`

## Preserved Invariants Checked

- Existing provider config merge precedence remains covered by the adjacent runtime config tests already in `tests/runtime/test_provider_backends.py`.
- Workflow-scoped `GitRepo.commit(...)` behavior remains covered by the existing git scope tests in `tests/unit/test_stdlib_and_extensions.py`.

## Edge Cases / Failure Paths

- Invalid nested runtime section types now raise instead of silently defaulting.
- Combined CLI git flags continue to resolve deterministically through the typed config path.
- `commit_all()` returns the current head and `created_commit=False` when the workspace is unchanged.
- `commit_all()` snapshots both tracked edits and untracked files together, guarding against partial staging regressions.

## Flake Risk / Stabilization

- Git helper tests use temporary repositories with explicit local `user.name` / `user.email` configuration and make assertions against local git state only.
- Runtime config tests monkeypatch config file loading instead of relying on user environment or filesystem discovery outside the temp directory.

## Known Gaps

- Full `pytest` execution is not currently runnable in this environment because `pytest` is unavailable, so validation here is limited to static review and the implementation-side smoke checks already documented by the producer.
