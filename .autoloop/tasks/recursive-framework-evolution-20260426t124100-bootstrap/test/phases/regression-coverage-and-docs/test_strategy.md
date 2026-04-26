# Test Strategy

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: test
- Phase ID: regression-coverage-and-docs
- Phase Directory Key: regression-coverage-and-docs
- Phase Title: Regression Coverage And Docs
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Runtime git tracking defaults and commit policies:
  `tests/runtime/test_provider_backends.py`
  `tests/runtime/test_runtime_git_tracking.py`
- Clean-start enforcement before workspace creation:
  `tests/runtime/test_runtime_git_tracking.py::test_git_tracking_enabled_requires_clean_repo_before_run_workspace_creation`
  `tests/runtime/test_optional_extensions.py::test_dirty_repo_fails_before_runner_creates_run_workspace`
- Runtime tracing defaults, raw output refs, provider usage, and sequence-resume behavior:
  `tests/runtime/test_runtime_tracing.py`
- Static step graph persistence:
  `tests/runtime/test_runtime_static_graph.py`
- Plain workflow end-to-end runtime observability without workflow declarations:
  `tests/runtime/test_optional_extensions.py::test_normal_run_writes_runtime_observability_artifacts_without_workflow_declarations`
- Workflow-declared GitTracking deprecation handling:
  `tests/runtime/test_optional_extensions.py::test_workflow_declared_git_tracking_is_ignored_in_favor_of_runtime_git_tracking`
- Resume git-tracking config mismatches:
  `tests/runtime/test_optional_extensions.py::test_resume_with_git_tracking_disabled_after_tracked_segment_records_warning_without_backfill`
  `tests/runtime/test_optional_extensions.py::test_resume_with_git_tracking_enabled_after_untracked_segment_starts_from_resume_point`
- Explicit non-git opt-outs for temp-workspace runtime package tests:
  `tests/runtime/test_workflow_reference_resolution.py`
  `tests/runtime/test_compatibility_runtime.py`
  `tests/runtime/test_workflow_integration_parity.py`
  workflow-package runtime suites updated with `RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False))`
- Documentation contract lock-in:
  `tests/test_architecture_baseline_docs.py`

## Preserved invariants checked

- Runtime git tracking remains enabled by default unless tests opt out explicitly.
- Resume warnings are appended without backfilling earlier git records.
- Workflow-declared tracing remains allowed while runtime tracing still writes the default evidence files.

## Edge cases and failure paths

- No git repo present with tracking enabled vs disabled/ignored behavior.
- Dirty repo failure-before-workspace-creation.
- No-op step commit behavior and untracked-file commit-all behavior.
- Malformed trace/git JSONL during resume sequence discovery.
- Tracked-to-disabled and untracked-to-enabled resume direction changes.

## Flake-risk controls

- Temporary repos initialize git identity locally and avoid network dependencies.
- Validation uses deterministic fake providers and fixed artifact assertions.
- Non-git temp-workspace tests opt out explicitly instead of depending on ambient repo state.

## Known gaps

- No additional repo test edits were needed in this turn because the required coverage already existed after the implementation phase changes; this turn focused on independent validation and artifact documentation.
