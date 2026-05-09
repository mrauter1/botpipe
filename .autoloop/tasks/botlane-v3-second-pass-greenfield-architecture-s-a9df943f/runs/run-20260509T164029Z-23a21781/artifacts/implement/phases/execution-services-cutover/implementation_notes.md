# Implementation Notes

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: execution-services-cutover
- Phase Directory Key: execution-services-cutover
- Phase Title: Remove Engine Reach-Through From Collaborators
- Scope: phase-local producer artifact

## Files changed

- `botlane/core/execution_runtime_services.py`
- `botlane/core/execution_services.py`
- `botlane/core/engine_collaborators.py`
- `botlane/core/branch_groups/runtime.py`
- `botlane/core/engine.py`
- `tests/contract/test_branch_result_runtime.py`
- `tests/strictness/test_no_internal_compat_layers.py`
- `.autoloop/.../decisions.txt`

## Symbols touched

- `ArtifactRuntimeService`
- `RouteRuntimeService`
- `SessionRuntimeService`
- `ProviderRuntimeService`
- `CheckpointRuntimeService`
- `OperationBindingService`
- `ChildWorkflowRuntimeService`
- `EventRuntimeService`
- `ProviderContractBuilder`
- `StepDispatcher`
- `HookRunner`
- `BranchGroupRuntime`
- `StateRuntime`
- `SessionRuntime`
- `CheckpointManager`
- `OperationRecorder`
- `WorkflowInvoker`
- `Engine.__init__`

## Checklist mapping

- Plan milestone 2 / AC-1: completed
  - Replaced collaborator `Engine` injection with Engine-free execution services and direct collaborator dependencies.
- Plan milestone 2 / AC-2: completed
  - Removed Engine-backed execution-service bridge shims from composition and added AST strictness against `engine` injection / `self._engine` / `Engine._*` reach-through in maintained runtime collaborators.
- Plan milestone 2 / AC-3: completed
  - Updated and passed focused execution-service, route, hook, child-workflow, branch-runtime, session/runtime-control/artifact, and strictness suites.

## Assumptions

- This phase stays scoped to execution-service cutover only; one-step SDK collapse and `StepExecutionResult.transition` removal remain out of phase.

## Preserved invariants

- Public SDK behavior and route/artifact/input semantics are unchanged.
- Composite branch-group finalization still preserves nested provider attribution while validating the composite route against the composite step's compiled routes.
- Provider-question legality remains enforced for provider-backed steps only and still respects `allow_provider_questions`.

## Intended behavior changes

- Internal runtime collaborators no longer retain `Engine` or invoke `Engine` private helpers for execution, hooks, child-workflow mapping, branch runtime, checkpoint persistence, operation binding, or route/artifact/session/provider services.

## Known non-changes

- `botlane.__all__`, `botlane.core.__all__`, `.botlane` identity, and current public runtime payload shapes were not changed.
- `WorkflowPlan` route authority and single-step/finalization cleanup were not expanded here beyond what this phase needed.

## Expected side effects

- Execution-service wiring is now centralized through `ExecutionServices` plus concrete runtime services in `execution_runtime_services.py`.
- Engine remains the orchestration/composition root and now forwards provider-policy-resolver lifecycle changes into the operation binding service.

## Validation performed

- `.venv/bin/python -m pytest -q tests/contract/engine/test_execution_services.py tests/contract/engine/test_routes.py tests/contract/engine/test_hooks.py tests/contract/engine/test_child_workflows.py tests/contract/test_branch_group_runtime.py tests/contract/test_branch_result_runtime.py tests/strictness/test_no_internal_compat_layers.py`
- `.venv/bin/python -m pytest -q tests/contract/engine/test_sessions.py tests/contract/engine/test_runtime_controls.py tests/contract/engine/test_artifacts.py`
- `python3 -m py_compile botlane/core/execution_runtime_services.py botlane/core/execution_services.py botlane/core/engine_collaborators.py botlane/core/branch_groups/runtime.py botlane/core/engine.py`

## Deduplication / centralization

- Moved route/artifact/session/provider/error/operation/child-workflow runtime helpers out of Engine-backed bridge shims into concrete Engine-free runtime services.
- Reused shared `step_result_from_direct_control()` / `step_result_from_route_finalization()` helpers so dispatcher and branch-group composite mapping do not keep separate step-result assembly paths.
