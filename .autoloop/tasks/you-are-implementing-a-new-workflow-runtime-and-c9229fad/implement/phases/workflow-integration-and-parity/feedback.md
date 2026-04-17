# Implement ↔ Code Reviewer Feedback

- Task ID: you-are-implementing-a-new-workflow-runtime-and-c9229fad
- Pair: implement
- Phase ID: workflow-integration-and-parity
- Phase Directory Key: workflow-integration-and-parity
- Phase Title: Workflow Integration And Parity
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — `autoloop_v3/runtime/runner.py:run_workflow` still mutates rejected legacy resume targets before returning the intended compatibility error. In the current order, `run_workflow()` opens the existing run and emits `run_resumed` before `_validate_resume_state()` rejects “legacy session/event only” runs, so a failed resume appends new `run_resumed`/`run_finished` events to the legacy run’s `events.jsonl` even though the runner explicitly claims it cannot resume that state. This is a persisted-state compatibility regression: the guard path is supposed to reject unsupported resumes without altering the legacy run it refused to handle. Minimal fix: perform the resume compatibility gate before any run-scoped writes for rejected resumes, and add a regression test that asserts `events.jsonl` is unchanged on this failure path. If `open_existing_run()` also needs to stay read-only for this path, split the lookup/validation boundary there rather than relying on post-hoc cleanup.
