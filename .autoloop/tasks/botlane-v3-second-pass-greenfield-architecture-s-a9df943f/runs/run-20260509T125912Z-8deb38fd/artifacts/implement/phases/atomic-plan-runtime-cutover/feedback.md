# Implement ↔ Code Reviewer Feedback

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: atomic-plan-runtime-cutover
- Phase Directory Key: atomic-plan-runtime-cutover
- Phase Title: Atomic Plan Runtime Cutover
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — `botlane/core/engine_collaborators.py:122-133`, `botlane/core/engine_collaborators.py:1647-1861`, `botlane/core/engine.py:988-999`, `botlane/core/engine.py:3433-3472`: AC-2 is not actually satisfied because `RouteFinalizer.finalize(...)` still returns the legacy `_RouteResolution` wrapper, `StepExecutionResult` still carries `finalization`, and `Engine._handle_step_result(...)` still branches on `destination` strings plus `last_transition.runtime_control` instead of consuming `RouteDecision` / `RouteAction` as the authoritative control-flow result. Concrete risk: the route outcome is now duplicated across `destination`, `finalization`, and `route_decision.action`; a future hook/direct-control change can update the new decision/action path without updating the legacy fields, and the engine will still take the old branch. Minimal fix: make `RouteFinalizer.finalize(...)` return `RouteDecision` (or a canonical step-finalization result whose primary payload is `RouteDecision` / `RouteAction`), remove `finalization` as the engine control-flow source from `StepExecutionResult`, and centralize terminal/continue handling in `Engine._handle_step_result(...)` on `RouteAction`.
