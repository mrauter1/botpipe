# Runtime simplification: implementation and validation

Implements the bounded B1/A1/M1 PRD, revision 3, against main commit
`e4c68c8f72ee306c1cf98e127e8e5bfc0f147e49` (checked 19 September 2026).

- **B1:** Normalize at the existing branch boundaries; use typed results in
  internal policy/rendering helpers. Keep the existing dictionary callback API.
- **A1:** Build SDK result artifacts with the existing declared-write collector
  and `ArtifactMap` converter. Delete the duplicate collector and its context
  alias. Retention collects again at its existing later phase.
- **M1:** Share one strict metadata file parser between runner and inspection;
  replace the bespoke runner write with an explicit-field merge through the
  existing atomic writer. The successful parser already establishes the schema,
  so the merge does not repeat that work.

These changes remove 46 net production lines across six files. There is no new
SDK concept, production module, dependency, configuration, or persisted schema.

## Compatibility and limits

Supported SDK signatures and exports remain unchanged. The public metadata
reader still accepts a run directory or `RunRecord`; non-object JSON now raises
`WorkflowExecutionError` instead of an incidental `AttributeError`. Existing
schema-error labels remain unchanged. Unexported `branch_is_success` and
`branch_error_summary` are now private; unsupported deep-import aliases are not
retained.

Metadata merging preserves unspecified fields and shallow-update semantics.
Atomic replacement has the existing writer's filesystem limits; see
[architecture](architecture.md). Unicode may be escaped while parsed values
remain identical. No standalone migration is needed; touched schema-less records
are normalized as before.

Scoped-artifact retention loss remains separate work. Use `keep_all()` when
task-local branch/worklist outputs must survive; see [SDK retention](sdk.md#retention).
Cache identity, session protocols, provider-policy fixes, child continuation,
phased checkpoints, and adaptive-goal changes are outside this change.

## Retired project compatibility

A separately authorized follow-up removes the former project's trace reader,
its trace-corpus field, and its special source, packaging, and Git exclusions.
The internal trace corpus now contains only Botpipe run summaries and nested
Codex rollout references, alongside its schema, root, and limits. No repository
consumer requires the removed field; the internal schema identifier is retained.
Former runtime directories receive ordinary source-capture treatment if present.

Both authoring-guide copies and the runtime fixtures reflect the supported
inputs. After the original legacy-identity scanner passed against the cleaned
source, that obsolete scanner and its helpers were deleted. The three canonical
Botpipe identity checks remain, as do the SDK sentinel-writer tests. This support
removal does not change the B1/A1/M1 compatibility guarantees above.

## Acceptance coverage

Names below are pytest test functions, including all their parameterized cases.
The tables identify the relevant assertions; a passing case does not establish
guarantees beyond its tested conditions.

### B1: branch boundaries

Unless stated otherwise, tests are in
`tests/contract/test_branch_outcome_contract.py`.

| PRD ID | Test functions |
|---|---|
| B-T1 | `test_each_builtin_policy_is_equivalent_for_typed_and_mapping_manifests` |
| B-T2 | `test_mixed_outcomes_preserve_policy_priority_and_ordered_partial_diagnostics` |
| B-T3 | `test_empty_branch_collection_preserves_existing_all_and_any_behavior` |
| B-T4 | `test_custom_outcome_adapter_supplies_exact_arguments_for_supported_signatures`; `test_custom_outcome_payload_and_context_are_equivalent_for_both_manifest_forms`; `test_custom_outcome_with_required_third_parameter_keeps_normal_python_type_error` |
| B-T5 | `test_custom_non_event_and_unknown_policy_keep_existing_diagnostics` |
| B-T6 | `test_mapping_manifest_error_rendering_matches_typed_rendering_and_sections` |
| B-T7 | In `tests/contract/test_branch_result_serialization.py`: `test_branch_result_to_manifest_dict_matches_current_completed_shape`, `test_branch_result_to_manifest_dict_matches_current_cancelled_shape`, `test_branch_result_to_manifest_dict_matches_current_skipped_shape` |

### A1: artifact collection and retention

All tests are in `tests/unit/test_sdk_facade.py`.

| PRD ID | Test functions |
|---|---|
| A-T1 | `test_sdk_run_default_retention_promotes_task_local_declared_writes_and_keeps_workspace_writes` |
| A-T2 | `test_sdk_run_retention_keep_all_ephemeral_and_keep_declared_writes_false` |
| A-T3 | `test_sdk_run_maps_failed_terminal_to_failed_result_status`; `test_sdk_run_explicit_provider_questions_true_allows_handlerless_pause`; `test_sdk_run_too_many_pauses_keeps_task_scratch_by_default`; `test_sdk_run_handles_typed_input_pause_loop_and_debug_artifacts` |
| A-T4 | `test_sdk_run_retention_keep_all_ephemeral_and_keep_declared_writes_false` |
| A-T5 | `test_sdk_result_preserves_declared_order_and_missing_optional_metadata` |
| A-T6 | `test_sdk_run_retention_collects_declared_writes_with_runtime_param_context`; `test_sdk_run_custom_promoted_writes_dir_uniquifies_collisions`; `test_sdk_run_retention_keep_all_ephemeral_and_keep_declared_writes_false`; `test_sdk_result_preserves_declared_order_and_missing_optional_metadata` |
| A-T7 | `test_sdk_task_local_directory_retention_preserves_existing_modes` |
| A-T8 | Existing `test_sdk_result_artifacts_omit_branch_scoped_writes_without_crashing`; `test_sdk_result_artifacts_omit_worklist_selection_writes_without_crashing` (output-map omission only; no new test endorses data loss) |
| A-T9 | `test_sdk_run_exposes_result_artifact_metadata_and_helpers`; `test_result_artifact_read_model_rejects_missing_or_non_model_schema`; `test_sdk_result_preserves_declared_order_and_missing_optional_metadata` |

### M1: metadata persistence and inspection

Unless stated otherwise, tests are in `tests/runtime/test_run_metadata_contract.py`.

| PRD ID | Test functions |
|---|---|
| M-T1, M-T2 | `test_merge_run_metadata_preserves_unspecified_fields_and_replaces_explicit_values` |
| M-T3 | `test_empty_metadata_merge_does_not_read_or_create_file` |
| M-T4 | `test_merge_run_metadata_rejects_missing_or_invalid_source_without_replacement`; `test_merge_run_metadata_propagates_unreadable_source_without_replacement` |
| M-T5 | `test_merge_run_metadata_migrates_legacy_payload_and_preserves_unknown_fields`; `test_public_run_metadata_reader_migrates_legacy_payload_without_rewriting` |
| M-T6 | `test_merge_run_metadata_preserves_unspecified_fields_and_replaces_explicit_values`; `test_public_run_metadata_reader_accepts_record_string_and_path` |
| M-T7 | `test_merge_run_metadata_serialization_failure_preserves_original_and_cleans_temp`; `test_merge_run_metadata_replace_failure_preserves_original_and_cleans_temp` |
| M-T8 | In `tests/runtime/test_runtime_cli_metadata_integration.py`: `test_workspace_run_metadata_records_origin_fields`. In `tests/runtime/test_workspace_and_context.py`: `test_context_invoke_workflow_supports_typed_child_input_and_output`; `test_context_invoke_workflow_records_typed_child_output_validation_failures` |
| M-T9 | `test_public_run_metadata_reader_accepts_record_string_and_path`; `test_public_run_metadata_reader_migrates_legacy_payload_without_rewriting` |
| M-T10 | `test_public_run_metadata_reader_preserves_errors_and_source` |

## Validation and rollout

Use Python 3.12 and an editable installation following `CONTRIBUTING.md`, then
run `python -m pytest -q` and `git diff --check`. In environments setting
`CODEX_HOME`, remove it only from the test process to accommodate an existing
test assumption. Both packaging tests were exercised using an isolated editable
installation and a local wheel cache; no packaging test was excluded or weakened.

Baseline full suite: **1,450 passed, one failed**. The original B1/A1/M1 candidate
had **1,480 passed, the same one failed**. The failure came from the now-retired
identity scanner rejecting deliberate legacy trace support.

After removing that support, all **12 focused tests passed**, including the
unchanged scanner. After deleting the obsolete scanner, the final full suite
passed: **1,480 passed, zero failures or skips**, including both packaging tests.
All 30 B1/A1/M1 regression cases remain. The existing fake-provider
unawaited-coroutine warning remains unrelated. A tracked-file scan found no
remaining retired-product references. `git diff --check` passed, and independent
review found no blocking defect.

Validation used Python 3.12.14, pytest 9.1.1, Pydantic 2.13.5, Jinja2 3.1.6, and
setuptools 84.0.0 for isolated builds. Reverting only the compatibility-removal
commit restores the retired support and its conflicting scanner; the original
B1/A1/M1 simplifications are a separate commit.
