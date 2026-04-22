# Test Strategy

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: test
- Phase ID: subworkflow-parity-and-git-scope
- Phase Directory Key: subworkflow-parity-and-git-scope
- Phase Title: Subworkflow Parity And Git Scope
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 child workflow invocation by imported class and workflow name:
  `tests/runtime/test_workspace_and_context.py`
  `test_context_invoke_workflow_accepts_imported_main_workflow_classes_and_records_child_metadata`
  `test_context_invoke_workflow_by_name_creates_isolated_child_runs_without_inheriting_parent_answers`
- AC-2 preserved isolation and Autoloop-v1 parity sidecars:
  `tests/runtime/test_workspace_and_context.py`
  `test_context_invoke_workflow_by_name_creates_isolated_child_runs_without_inheriting_parent_answers`
  `test_context_invoke_workflow_records_stable_child_metadata_shape_for_fatal_children`
  `tests/runtime/test_workflow_integration_parity.py`
  `test_autoloop_v1_runs_through_general_runtime_and_preserves_package_local_sidecars`
  `test_autoloop_v1_parity_persists_clarifications_on_resume_without_a_custom_runner`
  `test_autoloop_v1_maps_blocked_runs_to_blocked_status_under_the_general_runner`
- AC-3 workflow-scoped git tracking:
  `tests/runtime/test_optional_extensions.py`
  `test_git_tracking_extension_runs_only_through_workflow_declared_opt_in`
  `tests/unit/test_stdlib_and_extensions.py`
  `test_git_filters_preserve_raw_delta_when_scoping_to_the_workflow_workspace`
  `test_git_repo_commit_scope_uses_filtered_delta_without_rewriting_raw_delta`
  `test_git_repo_commit_ignores_empty_selected_scope_when_unrelated_changes_are_pre_staged`
  `test_git_repo_commit_allows_explicit_empty_commit_for_empty_selected_scope`
- AC-4 child result and metadata shape:
  `tests/runtime/test_workspace_and_context.py`
  `test_context_invoke_workflow_accepts_imported_main_workflow_classes_and_records_child_metadata`
  `test_context_invoke_workflow_records_stable_child_metadata_shape_for_fatal_children`
  `tests/contract/test_engine_contracts.py`
  `test_step_finish_exposes_raw_outputs_for_package_local_parity_extensions`

## Preserved invariants checked

- Child runs keep independent run folders, sessions, checkpoints, and request snapshots under the same task.
- Parent answers are not inherited by child runs implicitly.
- Child invocation no longer rewrites shared task `request.md` or `messages.jsonl`, including the fatal child path.
- Autoloop-v1 parity still emits raw logs, clarification notes, session placeholders, and blocked/question mappings through the general runtime.
- Git tracking still ignores non-workflow task files by default while leaving unrelated staged changes untouched.

## Edge cases and failure paths

- Paused child run selected by workflow name with parent resume answer present.
- Fatal child run still writes stable `children.jsonl` metadata and keeps task request state unchanged.
- Blocked Autoloop-v1 verifier outcome maps to paused terminal result with `blocked` run status.
- Empty or out-of-scope git selections do not create unintended commits.

## Stabilization notes

- All child-workflow tests use temp roots plus `workflows.*` module cache eviction to avoid import leakage between generated fixture packages.
- Runtime/provider behavior is deterministic via `ScriptedLLMProvider`; no timing, network, or nondeterministic ordering is used.
- Git tests sanitize inherited `GIT_*` repo-selection env vars so temp repositories are exercised rather than the outer workspace repo.

## Known gaps

- No broader doc-surface assertions are added here because documentation rewrite is explicitly out of phase scope.
- The public package CLI contract itself is covered in earlier phases and is not re-exercised here beyond the runtime behaviors it depends on.
