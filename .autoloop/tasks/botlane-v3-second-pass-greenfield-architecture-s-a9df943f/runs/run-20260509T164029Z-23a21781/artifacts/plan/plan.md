# Plan

## Goal

Preserve the public Botlane API, `.botlane` identity, and current user-facing runtime behavior while finishing the remaining second-pass greenfield cutovers: make `WorkflowPlan` the only route authority, remove Engine-backed collaborator reach-through, collapse `Botlane.step(...)` to one canonical internal architecture, and delete the redundant step-finalization representation from `StepExecutionResult`.

## Repo Findings

- Route ownership is still split. `botlane/core/compiler.py` injects `_route_table` into every step-plan variant, `_BaseStepPlan` derives all route views from that field, and multiple inspection/runtime surfaces still read step-local route tables or fall back to them.
- `ExecutionServices` exists, but `Engine` still composes `_EngineArtifactService`, `_EngineRouteService`, and `_EngineStateService` bridge shims while `StepDispatcher`, `ProviderContractBuilder`, `HookRunner`, `WorkflowInvoker`, and `BranchGroupRuntime` keep an `Engine` reference and call many `Engine._*` helpers directly.
- `Botlane.step(...)` still builds both `SingleStepPlan` and a one-step `WorkflowPlan` via `_build_single_step_execution_plan(...)`; only the `WorkflowPlan` executes, so the duplicate plan path is architectural overhead rather than a required behavior surface.
- `StepExecutionResult` already exposes canonical `route_decision` and `action`, but it still carries `transition`. `Engine` loop code and branch-group composite logic still depend on that duplicate record, while public runtime metadata derives from `RunResult.last_transition`.

## Milestones

### 1. Make `WorkflowPlan` the sole route authority

- Remove `_route_table` from all step-plan dataclasses and delete `_effective_route_table` ownership from `_BaseStepPlan`.
- Rebase route-tag derivation on `WorkflowPlan.routes` and `WorkflowPlan.global_routes` only:
  - runtime lookup in `botlane/core/engine.py`
  - provider contract construction in `botlane/core/engine_collaborators.py`
  - inspection/static graph/CLI capability exports in `botlane/runtime/static_graph.py`, `botlane/runtime/cli.py`, and `botlane/core/workflow_capabilities.py`
- Keep route behavior unchanged: step-local effective routes remain in `WorkflowPlan.routes`; global routes remain separately owned by `WorkflowPlan.global_routes` and are merged only by consumers that need fallback lookup.
- Strengthen contract coverage so maintained sources cannot reintroduce step-plan route tables or route-view derivation from step-local compatibility state.

### 2. Finish the `ExecutionServices` boundary cutover

- Expand `ExecutionServices` from the current partial artifact/route/hook/state bridge into the narrow service surface actually needed by collaborators:
  - artifact resolution and validation
  - route lookup, route finalization support, and handoff scheduling
  - hook execution helpers
  - session persistence / lookup
  - provider prompt + request support
  - child-workflow invocation
  - runtime state mutation helpers
- Replace Engine-owned bridge shims and constructor injection so `StepDispatcher`, `ProviderContractBuilder`, `BranchGroupRuntime`, route finalization, hook execution, and related collaborators depend on services or compiled plan data instead of `Engine`.
- Keep `Engine` as the orchestration/composition root only. Do not replace `Engine` with a renamed god object exposed through services.
- Add direct strictness coverage that collaborators no longer store `Engine` or call `Engine` private methods.

### 3. Collapse SDK one-step execution and remove duplicate step-finalization state

- Collapse `Botlane.step(...)` to one canonical internal execution path. The executable artifact should be a single compiled one-step `WorkflowPlan`; any remaining single-step inspection metadata must be derived from that plan rather than compiled in parallel.
- Remove the alternate builder path so the SDK no longer constructs both `SingleStepPlan` and `WorkflowPlan` for one-step execution.
- Remove `transition` from `StepExecutionResult` and switch internal consumers, especially branch-group composite mapping, to `route_decision`, `action`, `pending_input`, and provider-attempt metadata as the canonical transition surface.
- Preserve current public/runtime behavior by deriving `RunResult.last_transition` and the runner/workspace `finalization` payloads from canonical route-decision data at the engine boundary instead of carrying a second record on `StepExecutionResult`.

## Interface Contracts

- `WorkflowPlan.routes` is the only authoritative step-local effective route table.
- `WorkflowPlan.global_routes` is the only authoritative global route table.
- Step-plan variants may expose convenience route views only if those views are derived from `WorkflowPlan`, not from copied route ownership on the step object.
- `ExecutionServices` methods must be narrow and Engine-free. No service method may accept `Engine`, and no collaborator may call `Engine._*`.
- `Botlane.step(...)` must compile and execute exactly one one-step architecture.
- `StepExecutionResult` keeps `route_decision`, `action`, `pending_input`, `event`, `outcome`, and provider/raw-output data, but no duplicate finalization/transition record.

## Compatibility Notes

- Do not change `botlane.__all__`, `botlane.core.__all__`, or preserved SDK signatures/behavior.
- Keep `.botlane` task/run/artifact layout, route behavior, provider-question behavior, and input handling unchanged.
- Preserve current `RunResult.last_transition` shape and runtime/workspace `finalization` payload shape even though the internal `StepExecutionResult.transition` field is removed.

## Validation

- Focused architecture/contract suites during implementation:
  - `tests/unit/test_route_contracts.py`
  - `tests/unit/test_step_plans.py`
  - `tests/runtime/test_runtime_static_graph.py`
  - `tests/contract/engine/test_execution_services.py`
  - `tests/contract/engine/test_routes.py`
  - `tests/contract/engine/test_hooks.py`
  - `tests/contract/test_branch_result_runtime.py`
  - `tests/contract/test_sdk_single_step_execution.py`
  - `tests/contract/test_single_step_plan_equivalence.py` if any inspection-only single-step metadata remains
  - `tests/runtime/test_workspace_and_context.py`
  - `tests/strictness/test_no_internal_compat_layers.py`
- Final acceptance: full `pytest` suite green.

## Risk Register

- Route-view drift: one inspection surface could keep reading copied step data.
  - Control: remove `_route_table` as part of the same slice that rewires runtime/static-graph/capability call sites and add strictness checks against reintroduction.
- Service cutover regressions: collaborator rewiring can break provider/session/handoff behavior if done piecemeal.
  - Control: expand `ExecutionServices` first, then migrate constructors/call sites in one dependency-ordered slice with contract tests around `RouteFinalizer`, step dispatch, and branch runtime.
- SDK parity regressions: collapsing dual one-step builders can break typed input/params, explicit routes, or provider-question flow.
  - Control: keep the same compiler lowering and assert parity through the existing SDK single-step tests before deleting redundant builders.
- Finalization visibility regressions: removing `StepExecutionResult.transition` can accidentally change `RunResult.last_transition` or persisted runtime metadata.
  - Control: move finalization-record construction to the engine/run boundary before deleting the duplicate field, and validate runner/workspace payload tests.

## Rollback

- Roll back by milestone, not file-by-file:
  - route-authority slice
  - service-boundary slice
  - SDK/finalization slice
- Do not leave mixed architectures in place:
  - no partial `_route_table` removal
  - no collaborator set where some still depend on `Engine`
  - no `StepExecutionResult` shape carrying both canonical route-decision data and duplicate transition state
