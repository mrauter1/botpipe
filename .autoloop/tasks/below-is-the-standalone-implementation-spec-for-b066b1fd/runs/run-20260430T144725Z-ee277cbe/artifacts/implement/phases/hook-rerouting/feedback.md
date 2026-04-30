# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: implement
- Phase ID: hook-rerouting
- Phase Directory Key: hook-rerouting
- Phase Title: Enable Hook Rerouting
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` `core/validation.py::_validate_step_hooks`, `core/engine.py::_run_after_hook`: producer-phase pair hooks still compile as if route redirects are legal, but runtime rejects them. `_validate_step_hooks()` continues to run `_validate_static_after_hook_routes(...)` on `after_do`, so a workflow like `produce_verify_step(..., after_do=lambda ctx, out: "accepted", routes={"accepted": FINISH})` validates cleanly. At runtime, `_run_after_hook()` hard-fails the same hook because `candidate_event is None` and `allow_redirect` is false, raising `after_producer hook for step '...' cannot redirect before a candidate route exists`. That is a user-visible compiler/runtime contract split introduced by this phase. Minimal fix: centralize the “producer-phase after hooks are state-only” rule in validation by rejecting redirect-like `after_do` / `after_producer` returns up front, or implement explicit short-circuit semantics and tests so validation and execution agree.
