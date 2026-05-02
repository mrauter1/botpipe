# Implementation Notes

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: implement
- Phase ID: failure-trace-optimizer-alignment
- Phase Directory Key: failure-trace-optimizer-alignment
- Phase Title: Failure, Trace, And Optimizer Alignment
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/core/errors.py`
- `autoloop/core/engine.py`
- `autoloop/core/extensions.py`
- `autoloop/core/history.py`
- `autoloop/core/operations.py`
- `autoloop/core/providers/retries.py`
- `autoloop/runtime/runner.py`
- `autoloop/runtime/tracing.py`
- `autoloop_optimizer/optimization.py`
- `tests/runtime/test_history.py`
- `tests/runtime/test_runtime_tracing.py`
- `tests/runtime/test_workspace_and_context.py`
- `tests/unit/test_optimization_helpers.py`
- `tests/unit/test_provider_retries.py`

## Symbols Touched
- `WorkflowExecutionError`, `StepExecutionError`
- `exception_checkpoint_state`, `exception_failure_context`, `exception_failure_context_payload`
- `exception_pending_handoffs`, `exception_retry_kind`
- `replace_execution_error`, `enrich_execution_error`
- `StepFinalizationRecord`
- `Engine._annotate_execution_error`
- `Engine._next_retry_feedback`
- `Engine._provider_attempt_flags`
- `RuntimeTraceWriter._write_step_finished`
- `HistoryReader._record_step_finished`
- `normalize_trace_corpus`

## Checklist Mapping
- Milestone 4 / AC-1: replaced engine, retry-feedback, and operation-record failure metadata recovery with typed `WorkflowExecutionError` fields plus explicit helper readers.
- Milestone 4 / AC-2: added `provider_attempted`, `producer_attempted`, `verifier_attempted`, `pending_input_id`, `source_hook`, and `source_phase` through step finalization, trace output, history records, and child-run metadata.
- Milestone 4 / AC-3: updated optimizer trace normalization to carry direct runtime controls separately from route tags and to distinguish `AWAIT_INPUT` terminal handling from provider route tags.

## Assumptions
- Generic runtime, hook, and provider transport failures may now surface as `WorkflowExecutionError` wrappers so structured failure context can survive checkpointing without mutating arbitrary exception instances.

## Preserved Invariants
- Current mutated state, scoped state, worklist selections, sessions, and pending input continue to be checkpointed on failure.
- Provider-selected route validation and retry feedback still use the existing route/payload messaging contract.
- Direct runtime controls still do not update finalized-route built-ins.

## Intended Behavior Changes
- Runtime metadata is no longer attached to arbitrary exceptions via `setattr`; it now travels through typed workflow execution errors.
- Step-finished trace/history/finalization payloads now persist attempt booleans and pending-input ids for hook-originated control paths and pre-provider exits.
- Optimizer corpora now preserve direct runtime-control observations instead of collapsing them into missing/unknown route-only records.

## Known Non-Changes
- External terminal names remain `FINISH`, `AWAIT_INPUT`, and `FAIL`.
- The broader documentation migration and non-phase workflow package refactors remain out of scope for this turn.

## Expected Side Effects
- Tests that previously asserted raw `RuntimeError` propagation on hook/provider transport failures now need to assert `WorkflowExecutionError` with the original message.
- Child-run summaries and runtime trace/history payloads include additional finalization fields.

## Validation Performed
- `python3 -m compileall autoloop autoloop_optimizer tests/runtime/test_history.py tests/runtime/test_runtime_tracing.py tests/runtime/test_workspace_and_context.py tests/unit/test_provider_retries.py tests/unit/test_optimization_helpers.py tests/contract/test_engine_contracts.py`
- `./.venv/bin/python -m pytest tests/unit/test_provider_retries.py tests/runtime/test_runtime_tracing.py tests/runtime/test_history.py tests/unit/test_optimization_helpers.py tests/runtime/test_workspace_and_context.py tests/contract/test_engine_contracts.py -q`

## Deduplication / Centralization
- Centralized exception read/replace logic in `autoloop/core/errors.py` so engine, operation recording, and retry feedback use one typed metadata path instead of parallel `getattr(...)` fallbacks.
