# Test Strategy

- Task ID: framework-authoring-flexibility-change-specifica-7e827c69
- Pair: test
- Phase ID: milestone-a-runtime-route-policy-and-lazy-scoped-runtime
- Phase Directory Key: milestone-a-runtime-route-policy-and-lazy-scoped-runtime
- Phase Title: Milestone A Runtime Semantics
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Provider route policy:
  `tests/contract/test_engine_contracts.py`
  `test_full_auto_hides_default_question_route_from_provider_contract`
  `test_explicit_blocked_and_failed_routes_do_not_require_reason_field`
  `test_provider_question_route_is_illegal_in_full_auto_mode`
  Coverage: interactive vs full-auto question visibility, no default blocked/failed provider contract, explicit blocked/failed payload handling.

- Child workflow explicit mapping:
  `tests/contract/test_engine_contracts.py`
  `test_workflow_step_requires_explicit_failed_route_for_child_fail`
  `test_workflow_step_requires_explicit_blocked_route_for_child_await_without_question`
  Coverage: undeclared mapped `failed`/`blocked` routes fail clearly; preserved question validation remains covered by `test_workflow_step_rejects_child_question_without_question_payload`.

- Lazy worklist materialization and observability:
  `tests/contract/test_engine_contracts.py`
  `test_non_scoped_explicit_worklist_access_emits_resolution_event_for_only_requested_worklist`
  existing scoped-selection event coverage around `worklist_selection_resolved`
  Coverage: first-use resolution emits additive payload fields `lazy`, `source`, and `current_index`; unrelated worklists remain unmaterialized.

- Source-policy-driven ensure/scaffold behavior:
  `tests/contract/test_engine_contracts.py`
  `test_worklist_source_ensure_can_scaffold_backing_data_at_first_use`
  `test_resume_restores_materialized_worklist_via_source_ensure_when_backing_data_is_missing`
  `test_worklist_refresh_uses_source_ensure_when_backing_data_is_missing`
  Coverage: first-use scaffold, resume restore after backing-data deletion, and refresh after backing-data deletion all honor source `ensure()`.

- Preserved invariants and compatibility:
  existing lazy-resume/session tests in `tests/contract/test_engine_contracts.py`
  `test_resume_restores_materialized_worklists_and_lazily_materializes_unused_ones`
  `test_work_item_session_resume_uses_dir_key_based_key_and_reuses_session`
  `test_non_scoped_work_item_session_fails_when_no_current_item_exists`
  Coverage: checkpointed selections remain sparse/lazy, work-item session continuity still binds deterministically, and the updated no-current-item error path stays explicit.

## Edge cases and failure paths

- Illegal provider `question` in full-auto remains a failure-path assertion.
- Child `FAIL` and child await-without-question now have explicit undeclared-route failure assertions.
- Missing worklist backing data is covered on both failure-only artifact-backed paths and ensure-capable scaffold paths.

## Stabilization approach

- Tests use local temporary paths and in-memory stores only.
- Ensure-capable source fixtures are deterministic and write fixed JSON payloads to avoid ordering and timing flakes.

## Known gaps

- Environment-backed execution is still pending because this shell does not provide `pytest` or installed runtime dependencies.
- Static-graph/inspection payload behavior is still covered by existing runtime/static-graph suites; this turn did not add new static-graph assertions because the implementation left those code paths unchanged.
