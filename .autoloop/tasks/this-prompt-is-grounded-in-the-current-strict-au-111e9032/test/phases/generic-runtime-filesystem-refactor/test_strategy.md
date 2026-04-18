# Test Strategy

- Task ID: this-prompt-is-grounded-in-the-current-strict-au-111e9032
- Pair: test
- Phase ID: generic-runtime-filesystem-refactor
- Phase Directory Key: generic-runtime-filesystem-refactor
- Phase Title: Refactor The Generic Runtime
- Scope: phase-local producer artifact

## Behavior Coverage Map
- Runtime-neutral workspace layout:
  `test_workspace_creates_generic_layout_and_preserves_resume_root_compatibility`
  Covers request snapshot creation, generic directories, and legacy resume-root detection without phase-specific scaffolding.
- Persisted session compatibility:
  `test_filesystem_session_store_uses_generic_paths_and_loads_legacy_thread_id`
  `test_runtime_store_placeholder_helper_creates_generic_session_payload`
  `test_runtime_store_write_helper_preserves_sparse_metadata_and_non_codex_thread_id`
  `test_runtime_store_write_helper_mirrors_codex_session_id_into_thread_id`
  `test_filesystem_session_store_sparse_writes_preserve_existing_metadata`
  Covers `thread_id` compatibility, sparse metadata preservation, placeholder creation, and codex mirroring.
- Checkpoints and resume failure paths:
  `test_filesystem_checkpoint_store_round_trip`
  `test_runner_resume_without_checkpoint_but_with_persisted_state_fails_with_targeted_message`
  `test_runner_resume_without_checkpoint_rejects_scoped_session_files`
  Covers checkpoint persistence, targeted no-checkpoint resume errors, and scoped-session resume rejection.
- Workflow-declared session-path strategies:
  `test_filesystem_session_store_supports_custom_path_resolver`
  `test_runner_uses_declared_session_path_strategy_from_workflow_extensions`
  `test_runner_rejects_multiple_declared_session_path_strategies_before_creating_a_run`
  Covers generic path customization, workflow-facing `SessionPaths(...)` wiring, and duplicate-strategy failure before workspace side effects.
- Deterministic prompt resolution:
  `test_runner_prompt_resolution_is_independent_of_current_working_directory`
  `test_runner_prompt_resolution_uses_workspace_root_as_explicit_fallback`
  Covers workflow-relative prompt priority, explicit workspace-root fallback, and exclusion of ambient cwd prompt lookup.
- Config and CLI compatibility:
  `test_resolve_runtime_config_merges_global_local_and_cli`
  `test_discover_config_file_preserves_legacy_superloop_names`
  `test_cli_main_threads_generic_runtime_options_into_runner_options`
  `test_cli_main_turns_config_errors_into_parser_exit`
  `test_cli_main_turns_workflow_execution_errors_into_clean_exit`
  Covers typed config merging, both `superloop.*` legacy filenames, and CLI wiring/error paths.
- Runtime neutrality / integration:
  `test_runner_executes_toy_workflow_without_phase_scaffolding`
  `test_cli_module_smoke_executes_toy_workflow_end_to_end`
  `test_autoloop_v1_runs_with_generic_runtime_and_explicit_prompt_paths`
  `test_ralph_loop_executes_with_generic_runtime_and_persistent_main_session`
  Covers generic runtime behavior with an unrelated toy workflow plus strict repo-root workflows.

## Preserved Invariants Checked
- Runtime code remains phase-agnostic for generic runs.
- Prompt lookup is deterministic and uses explicit roots only.
- Legacy `superloop.*` config discovery remains intact.
- Session JSON compatibility, including legacy `thread_id`, is preserved.

## Edge Cases
- Duplicate `SessionPaths(...)` declarations.
- Scoped-session files without checkpoints on resume.
- Sparse legacy session payloads missing newer metadata keys.
- Conflicting cwd prompt files while workflow/workspace prompts exist.

## Failure Paths
- Invalid `max_steps`.
- CLI config parsing failure.
- CLI workflow execution failure.
- Resume requested without a compatible checkpoint.

## Known Gaps
- This phase does not add Git or tracing extension tests; those belong to later extension-focused phases.
- Autoloop-v1 raw-log, decisions-ledger, and status-policy parity remain covered in workflow/parity tests rather than generic runtime tests.
