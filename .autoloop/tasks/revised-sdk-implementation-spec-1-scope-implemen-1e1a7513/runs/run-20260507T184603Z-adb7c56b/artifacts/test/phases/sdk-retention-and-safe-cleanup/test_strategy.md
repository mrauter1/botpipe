# Test Strategy

- Task ID: revised-sdk-implementation-spec-1-scope-implemen-1e1a7513
- Pair: test
- Phase ID: sdk-retention-and-safe-cleanup
- Phase Directory Key: sdk-retention-and-safe-cleanup
- Phase Title: SDK Retention And Safe Cleanup
- Scope: phase-local producer artifact

## Behavior Coverage Map

- AC-1 successful retention: `tests/unit/test_sdk_facade.py::test_sdk_run_default_retention_promotes_task_local_declared_writes_and_keeps_workspace_writes`, `test_sdk_step_default_retention_deletes_task_scratch_on_success`, `test_sdk_run_retention_keep_all_and_ephemeral_modes`, `test_sdk_run_custom_promoted_writes_dir_uniquifies_collisions`
- AC-2 retained partial results: `tests/unit/test_sdk_facade.py::test_sdk_run_raises_input_required_with_partial_result`, `test_sdk_run_too_many_pauses_keeps_task_scratch_by_default`, `test_sdk_run_wraps_resume_schema_mismatch_as_input_response_validation_error`
- AC-3 cleanup and safe deletion: `tests/unit/test_sdk_facade.py::test_sdk_cleanup_only_targets_valid_completed_sdk_task_directories`, `test_sdk_cleanup_honors_older_than_and_include_failed_opt_in`, `test_safe_delete_sdk_task_dir_refuses_unsafe_candidates`
- AC-4 runtime-equivalent declared-write resolution: `tests/unit/test_sdk_facade.py::test_sdk_run_retained_artifacts_preserve_schema_and_runtime_context_paths`, `test_sdk_run_resolves_input_message_artifact_paths_for_none_message`, `test_sdk_run_params_surface_in_retained_artifact_paths`

## Preserved Invariants Checked

- Successful default retention deletes only the current SDK task scratch and keeps workspace writes intact.
- `keep_all` retains task scratch, while `ephemeral` omits task-local declared writes without deleting workspace files.
- Shared custom promotion directories do not overwrite earlier retained outputs from a different SDK run.
- Cleanup remains conservative by default and skips failed or awaiting-input candidates unless explicitly opted in.
- Safe deletion rejects non-`sdk-*`, missing-sentinel, mismatched-task, wrong-schema, wrong-owner, and outside-root candidates.

## Edge Cases And Failure Paths

- Task-local declared writes promoted out of scratch before deletion.
- Too-many-pauses and unhandled input pauses return partial results with populated retention metadata.
- Cleanup age filtering uses sentinel `created_at` timestamps, with failure deletion enabled only through `include_failed=True`.
- Sentinel corruption and ownership mismatches fail closed at the `_safe_delete_sdk_task_dir(...)` guard.

## Known Gaps

- `llm(...)` and `classify(...)` replay-folder cleanup remains intentionally out of scope for this phase.
- Cleanup fallback to directory mtime on invalid sentinel timestamps is not directly asserted here because the sentinel `created_at` path is the intended stable contract.
