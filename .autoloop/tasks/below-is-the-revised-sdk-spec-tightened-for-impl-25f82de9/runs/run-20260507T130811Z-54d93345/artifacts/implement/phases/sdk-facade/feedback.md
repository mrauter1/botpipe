# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-sdk-spec-tightened-for-impl-25f82de9
- Pair: implement
- Phase ID: sdk-facade
- Phase Directory Key: sdk-facade
- Phase Title: Add SDK Facade
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` `[autoloop/runtime/runner.py::_execute_compiled_workflow, autoloop/sdk.py::Autoloop.run]` Explicit SDK `message=None` is still broken end-to-end. `Autoloop.run(..., None)` passes `message=None` into `RunnerOptions`, but `_execute_compiled_workflow(...)` never forwards `options.message` into `engine.run(...)` / `engine.resume(...)`. The runner instead falls back to the persisted request snapshot, which is the workspace default text (`"No explicit initial message was provided..."`) for message-less runs. Repro: a one-step workflow that records `ctx.message` after `client.run(Wf, None)` observes the default placeholder string instead of `None`, so `ctx.input.message` is also wrong and any `{input.message}`-based artifact resolution can diverge from the SDK result surface. Minimal fix: thread `message=options.message` through both `engine.run(...)` and `engine.resume(...)` in `_execute_compiled_workflow(...)`, then add tracked regression coverage for `client.run(Wf, None)` asserting `ctx.message is None`, `ctx.input.message is None`, and message-based artifact/template rendering stays empty rather than using the placeholder snapshot text.
- `IMP-002` `non-blocking` `[tests/unit/test_primitives_and_stores.py, implementation_notes.md]` The validation notes cite `tests/unit/test_primitives_and_stores.py`, but that file is currently untracked in this worktree. That makes part of the recorded validation local-only and easy to lose in a later handoff. Minimal fix: either move the relevant assertions into an existing tracked test module or stop relying on the untracked file in the implementation notes.
