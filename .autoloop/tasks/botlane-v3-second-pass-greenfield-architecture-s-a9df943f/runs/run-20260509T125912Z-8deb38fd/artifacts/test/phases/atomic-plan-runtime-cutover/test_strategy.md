# Test Strategy

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: test
- Phase ID: atomic-plan-runtime-cutover
- Phase Directory Key: atomic-plan-runtime-cutover
- Phase Title: Atomic Plan Runtime Cutover
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- `compile_workflow(...) -> WorkflowPlan`
  Covered by `tests/unit/test_step_plans.py` and existing runtime compilation tests.
  Preserved invariants: typed `StepPlan` variants, `ArtifactId`-backed IO, no `original_step`.

- Route finalization exposes canonical decision/action data
  Covered by `tests/contract/test_provider_turn_plan_adapter.py`.
  Happy paths: finish route and await-input route expose `route_decision` and matching `action`.
  Regression guard: `StepExecutionResult` no longer exposes legacy `finalization`.

- Engine consumes `RouteAction` as authoritative control flow
  Covered by `tests/unit/test_engine_route_actions.py`.
  Edge cases: conflicting legacy `destination` vs `Continue.target_step`, `Finish`, `AwaitInput`, and `FailAction` must all follow `action`.
  Failure path: missing canonical `action` raises `WorkflowExecutionError`.

- Branch-group public export cutover
  Covered by `tests/unit/test_public_surface.py`.
  Preserved invariant: compiled branch exports removed; internal plan/result types still not public.

## Validation plan

- Run focused route/engine/compiler/public-surface tests for deterministic feedback.
- Avoid timing-sensitive or networked cases; all added coverage uses fake/scripted providers and private engine helpers only.

## Known gaps

- This phase does not add placeholder-centralization or typed branch-evidence tests because those belong to later phase scopes.
