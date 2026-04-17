# Implement ↔ Code Reviewer Feedback

- Task ID: you-are-a-principal-software-architect-and-imple-63e1905d
- Pair: implement
- Phase ID: workflow-migration-parity
- Phase Directory Key: workflow-migration-parity
- Phase Title: Workflow Migration And Autoloop_v1 Parity
- Scope: phase-local authoritative verifier artifact

- IMP-001 [blocking] `autoloop_v3/workflows/autoloop_v1_support.py:220-241`: `run_autoloop_v1()` emits every `step_executed` event after the run has already finished and tags each one with `_phase_id(result.state)`, which is the final phase id. Reproducing a two-phase run shows `plan phase-b`, `implement phase-b`, `test phase-b`, etc. for every step, and the harness never emits any `phase_started` / `phase_completed` events. That breaks AC-3 event-log parity and means any consumer that reconstructs prior phase status from `events.jsonl` gets the wrong answer. Minimal fix: capture per-step phase metadata at execution time inside the workflow-owned harness and emit workflow-owned phase lifecycle events there (or at minimum stop attaching a bogus final `phase_id` to earlier steps).

- IMP-002 [non-blocking] `autoloop_v3/workflows/autoloop_v1_support.py:431-487`: `_append_terminal_notice()` and `_append_resume_clarification()` hardcode `cycle=1` / `attempt=1`, so blocked/question/clarification records are misattributed once a pair loops within the same phase. Minimal fix: thread the logging provider’s tracked cycle/attempt state through these writes so raw-log and clarification metadata stay consistent with the corresponding producer/verifier entries.

- Cycle 2 verification: `IMP-001` and `IMP-002` are resolved. The harness now emits phase-aware step events at execution time, reintroduces `phase_started` / `phase_completed` in workflow-owned code, and reuses persisted session metadata for blocked/question/clarification cycle attribution. No new findings in scope.
