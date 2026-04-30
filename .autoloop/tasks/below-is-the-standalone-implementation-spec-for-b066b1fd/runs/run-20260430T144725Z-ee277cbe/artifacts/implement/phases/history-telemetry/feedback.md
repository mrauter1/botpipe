# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: implement
- Phase ID: history-telemetry
- Phase Directory Key: history-telemetry
- Phase Title: Add Read-Only History
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [core/engine.py:1168](../../../../../../../../core/engine.py:1168), [core/engine.py:1361](../../../../../../../../core/engine.py:1361), [core/engine.py:1516](../../../../../../../../core/engine.py:1516), [core/history.py:276](../../../../../../../../core/history.py:276): hook events are emitted without `visit`, `step_execution_id`, `scope`, or `item_id`, even for scoped steps. `HistoryReader` keys `hook_failed` failures from the event payload, so a scoped hook failure is currently attributed to an unscoped `StepInstanceKey(step_name, None, None)` instead of the active worklist item. Concrete failure: with a trace containing `step_started(scope="articles", item_id="article_17")` followed by `hook_failed(step_name="legal_review", ...)`, `ctx.history.step_telemetry("legal_review", item_id="article_17")` shows no error and `ctx.history.failures(step="legal_review", item_id="article_17")` is empty. This breaks AC-2's requirement that failures be derivable by scoped step instance. Minimal fix: route hook-event emission through the same step-identity payload builder used by provider/artifact events, so all hook lifecycle events carry the current step execution identity consistently.

- Re-review cycle 2: `IMP-001` is resolved. Hook lifecycle events now carry scoped step execution identity, the new direct engine regression covers emitted `hook_failed` payloads, and `ctx.history` now attributes scoped hook failures to the correct `StepInstanceKey`. No remaining blocking or non-blocking findings in phase-local scope.
