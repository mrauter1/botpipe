# Implement ↔ Code Reviewer Feedback

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: implement
- Phase ID: async-step-provider-foundation
- Phase Directory Key: async-step-provider-foundation
- Phase Title: Async Step Foundation
- Scope: phase-local authoritative verifier artifact

- IMP-001 (blocking): `StepDispatcher.execute_async()` claims to support finalize-mode `branch_group` steps, but it immediately calls the synchronous `BranchGroupRuntime.run()` (`autoloop/core/engine_collaborators.py:525-528`). That runtime executes nested branches through `step_dispatcher.execute(..., route_mode="capture")` (`autoloop/core/branch_groups/runtime.py:247-253`), and the sync capture bridge constructs `self.execute_async(...)` before `_run_awaitable_sync(...)` checks for a running loop (`autoloop/core/engine_collaborators.py:337-346`, `1262-1267`). In an actual async caller, `await engine.step_dispatcher.execute_async(branch_group_step, ...)` records branch failures, can return a misleading composite route such as `partial`, and emits `RuntimeWarning: coroutine 'StepDispatcher.execute_async' was never awaited` instead of executing the group. Minimal fix: centralize a real async branch-group entrypoint such as `BranchGroupRuntime.run_async(...)` that awaits nested `execute_async(..., route_mode="capture")`, or reject `branch_group` from `execute_async()` until that runtime exists; in either case, avoid creating coroutine objects before the running-loop guard.
