# Implementation Notes

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: implement
- Phase ID: history-telemetry
- Phase Directory Key: history-telemetry
- Phase Title: Add Read-Only History
- Scope: phase-local producer artifact

## Files Changed

- `core/history.py`
- `core/context.py`
- `core/extensions.py`
- `core/engine.py`
- `core/operations.py`
- `runtime/tracing.py`
- `runtime/runner.py`
- `tests/runtime/test_history.py`
- `tests/runtime/test_runtime_tracing.py`
- `tests/contract/test_engine_contracts.py`

## Symbols Touched

- `HistoryReader`, `StepInstanceKey`
- `Context.history`
- `StepStart`, `StepFinish`
- `Engine(..., runtime_event_sink=...)`
- `Engine._emit_provider_attempt_*`, `Engine._step_runtime_event_payload`
- `OperationRuntime.event_sink`, `_emit_operation_attempt_event`
- `RuntimeTraceWriter.runtime_event`

## Checklist Mapping

- AC-1 `ctx.history` read-only queries: implemented via `core/history.py`; bound lazily on `Context`; trace-first with events-only fallback.
- AC-1 missing `trace.jsonl` behavior: covered by `tests/runtime/test_history.py::test_context_history_falls_back_to_events_without_trace`.
- AC-2 derived telemetry: step completion, accepted routes, retries, do/verify attempts, failures, routes, and token usage keyed by `StepInstanceKey`.
- Deliverable runtime instrumentation: step execution ids, provider attempt events, artifact validation events, hook events mirrored into trace, and operation attempt instrumentation.
- Deliverable regression tests: trace payload tests, history reader tests, engine runtime-event tests, plus handoff-resume regression coverage kept green.

## Intended Behavior Changes

- `ctx.history` is now available on runtime contexts and reads `trace.jsonl`, `events.jsonl`, and checkpoint failure context without mutating them.
- Trace records now include `visit`, `step_execution_id`, and scoped `scope` / `item_id` fields on step start/finish events.
- Runtime now emits structured `provider_attempt_*` and `artifact_validation_failed` events for trace/event consumers.

## Preserved Invariants

- No mutable telemetry blob is added to checkpoints.
- Existing step trace persistence remains authoritative for `step_started` / `step_finished`; runtime events are additive.
- Route handoffs still resume correctly after provider transport failures.

## Known Non-Changes

- No new top-level public exports were added beyond the already-approved `ctx.history` surface.
- Step telemetry stays derived from run artifacts; runtime does not implicitly call `ctx.history` during step execution.

## Validation Performed

- `python3 -m py_compile core/history.py core/context.py core/engine.py core/operations.py core/extensions.py runtime/tracing.py runtime/runner.py`
- `python3 -m py_compile tests/runtime/test_runtime_tracing.py tests/runtime/test_history.py tests/contract/test_engine_contracts.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_runtime_tracing.py tests/runtime/test_history.py tests/contract/test_engine_contracts.py`
- `.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py::test_python_step_feedforward_helpers_accept_plain_string_prompts_with_rendered_provider tests/contract/test_engine_contracts.py::test_operation_replay_fingerprint_mismatch_fails_loudly`

## Assumptions

- `trace.jsonl` remains the highest-fidelity source when present; events-only telemetry is intentionally partial.
- Operation token usage is derived from provider-attempt events rather than expanding `StepProviderUsage` for non-step operation calls.
