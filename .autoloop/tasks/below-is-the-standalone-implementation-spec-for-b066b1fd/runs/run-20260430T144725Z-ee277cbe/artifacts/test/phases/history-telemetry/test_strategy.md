# Test Strategy

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: test
- Phase ID: history-telemetry
- Phase Directory Key: history-telemetry
- Phase Title: Add Read-Only History
- Scope: phase-local producer artifact

## Behavior-to-Test Coverage Map

- AC-1 `ctx.history` read-only access and trace-first behavior:
  - `tests/runtime/test_history.py::test_context_history_derives_scoped_telemetry_from_trace`
  - `tests/runtime/test_history.py::test_context_history_falls_back_to_events_without_trace`
- AC-2 scoped telemetry derivation from trace/events/checkpoint inputs:
  - `tests/runtime/test_history.py::test_context_history_derives_scoped_telemetry_from_trace`
  - `tests/runtime/test_history.py::test_context_history_attributes_scoped_hook_failures_from_trace`
- Runtime instrumentation for stable execution identity:
  - `tests/runtime/test_runtime_tracing.py::test_runtime_trace_records_step_execution_identity`
  - `tests/contract/test_engine_contracts.py::test_engine_emits_provider_attempt_events_with_step_execution_identity`
  - `tests/contract/test_engine_contracts.py::test_engine_emits_scoped_hook_failure_events_with_step_execution_identity`
  - `tests/contract/test_engine_contracts.py::test_engine_emits_scoped_hook_redirect_events_with_step_execution_identity`
- Structured failure/event paths:
  - `tests/contract/test_engine_contracts.py::test_engine_emits_artifact_validation_failure_events`
  - `tests/runtime/test_history.py::test_context_history_attributes_scoped_hook_failures_from_trace`

## Preserved Invariants Checked

- `ctx.history` still works when `trace.jsonl` is absent and returns partial telemetry from `events.jsonl` without failing.
- Scoped telemetry keys remain `StepInstanceKey(step_name, scope, item_id)` and do not collapse item-specific failures into unscoped buckets.
- Hook instrumentation remains additive to existing hook phase/route payloads; tests pin the old fields while asserting the new identity fields.

## Edge Cases And Failure Paths

- Scoped `hook_failed` trace records must surface through `ctx.history.failures(..., item_id=...)`.
- Scoped `hook_route_redirected` events must carry the same `visit` / `step_execution_id` / `scope` / `item_id` payload as other runtime events.
- Events-only fallback is intentionally partial and is covered without asserting unavailable route or acceptance metadata.

## Flake Risk And Stabilization

- Tests are deterministic: they use fixed timestamps, temporary directories, in-memory stores, and scripted providers.
- No network, wall-clock ordering dependency, or randomized data is involved.

## Known Gaps

- No new tests were added for optional raw-provider metadata ingestion because this phase derives telemetry from `trace.jsonl`, `events.jsonl`, and checkpoint failure context only.
