# Original intent considered

- The immutable request required the second-pass greenfield cutover to remove all `Compiled*` internal objects, keep `WorkflowPlan` as the only compiled workflow representation, keep `WorkflowPlan.routes` as the canonical route table, make `ExecutionFrame` authoritative, collapse SDK one-step execution to exactly one canonical architecture, and move collaborators behind narrow `ExecutionServices` boundaries without keeping `Engine`-owned bridges.
- I compared that request against the final source tree, the authoritative raw log, the decisions ledger, the phase implementation notes, and the test suite.

# Clarifications / superseding decisions

- I did not find any later raw-log clarification that changed the user intent from the immutable request.
- The decisions ledger records several implementation-time assumptions that matter for this audit:
  - block 6 accepted private step-plan route-table caches.
  - block 18 and block 19 accepted building both `SingleStepPlan` and a one-step `WorkflowPlan`.
  - the phase implementation notes for execution services describe the current service layer as a temporary bridge rather than the final boundary.
- Those decisions help explain the final tree, but they do not supersede the original request on their own.

# Implemented behavior

- The major public-surface and removal goals landed:
  - `compile_workflow(...)` returns `WorkflowPlan` in [botlane/core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/compiler.py:99).
  - `WorkflowPlan`, `ArtifactId`, `ArtifactSpec`, `RouteContract`, typed `StepPlan` variants, `BranchResult`, `BranchManifest`, `ExecutionFrame`, and placeholder/reference-graph modules exist in the requested canonical locations.
  - `botlane.__all__`, `botlane.core.__all__`, and `botlane.core.branch_groups.__all__` preserve the intended public/internal split in [botlane/__init__.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/__init__.py:66), [botlane/core/__init__.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/__init__.py:27), and [botlane/core/branch_groups/__init__.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/branch_groups/__init__.py:11).
  - The source tree no longer contains `CompiledWorkflow`, `CompiledStep`, `CompiledRoute`, `CompiledArtifact`, `CompiledBranchGroupSpec`, `CompiledBranchStepSpec`, `plan_adapters.py`, `_COMPILED_WORKFLOW_CACHE`, or `compile_workflow_plan(...)` outside absence-check tests.
- The final suite is green:
  - `.venv/bin/pytest -q` completed with `1278 passed, 1 warning` on May 9, 2026.

# Unresolved gaps

1. `StepPlan` still owns a duplicate private route-table representation, so `WorkflowPlan.routes` is not the sole route authority.
   Evidence:
   - `_BaseStepPlan` derives route views from `self._route_table` in [botlane/core/step_plans.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/step_plans.py:101).
   - Every concrete step-plan variant still stores `_route_table` in [botlane/core/step_plans.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/step_plans.py:311), [botlane/core/step_plans.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/step_plans.py:340), [botlane/core/step_plans.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/step_plans.py:391), [botlane/core/step_plans.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/step_plans.py:406), and [botlane/core/step_plans.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/step_plans.py:436).
   - Runtime still prefers the step-local cache in [botlane/core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/engine.py:1632).
   Why this is material:
   - The request explicitly required `WorkflowPlan.routes` / `WorkflowPlan.global_routes` to own route contracts and said `StepPlan` must not own route tables. The final tree still keeps both representations alive.

2. The execution-service boundary is still an `Engine` bridge, and key collaborators still hold `Engine` directly.
   Evidence:
   - `_EngineRouteService` and `_EngineStateService` are explicitly temporary bridge wrappers around `Engine` private methods in [botlane/core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/engine.py:293) and [botlane/core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/engine.py:391).
   - `Engine.__init__` wires those bridge objects into `ExecutionServices` and still instantiates `HookRunner(self)`, `StepDispatcher(self)`, `ProviderContractBuilder(self)`, and `BranchGroupRuntime(self)` in [botlane/core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/engine.py:442).
   - `ProviderContractBuilder` and `StepDispatcher` both retain `self._engine` in [botlane/core/engine_collaborators.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/engine_collaborators.py:201) and [botlane/core/engine_collaborators.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/engine_collaborators.py:495); `BranchGroupRuntime` does the same in [botlane/core/branch_groups/runtime.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/branch_groups/runtime.py:40).
   Why this is material:
   - The request explicitly forbade collaborators holding `Engine`, services calling `Engine` private methods, and `ExecutionServices` becoming a renamed engine shell. The current boundary remains transitional rather than canonical.

3. SDK one-step execution still uses two internal architectures instead of one canonical path.
   Evidence:
   - `_compile_single_step_execution_plan(...)` returns both `SingleStepPlan` and `WorkflowPlan` in [botlane/core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/compiler.py:152).
   - `_compile_single_step_workflow_plan(...)` still synthesizes a private workflow class in [botlane/core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/compiler.py:180) and [botlane/core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/compiler.py:1066).
   - `Botlane.step(...)` builds both plans and executes the `WorkflowPlan` path in [botlane/sdk.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/sdk.py:761).
   - Tests now codify both helpers in [tests/contract/test_single_step_plan_equivalence.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_single_step_plan_equivalence.py:113) and [tests/contract/test_single_step_plan_equivalence.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_single_step_plan_equivalence.py:134).
   Why this is material:
   - The request required exactly one one-step execution architecture and explicitly forbade keeping both `SingleStepPlan` and a one-step workflow path in parallel.

4. `StepExecutionResult` still carries a parallel transition record beyond the allowed action/decision fields.
   Evidence:
   - `StepExecutionResult` still includes `transition` in [botlane/core/engine_collaborators.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/engine_collaborators.py:121).
   - Branch runtime and engine completion paths still read that transition record in [botlane/core/branch_groups/runtime.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/branch_groups/runtime.py:117) and nearby fan-in/composite remapping logic.
   Why this is material:
   - The request allowed `route_decision` and `action` as the canonical control metadata and specifically pushed removal of compatibility-style parallel finalization representations.

# Differences justified by later clarification or analysis

- The exact test filenames differ from the request in a few places, but equivalent coverage exists across the final suite. That is acceptable because it does not remove requested behavior or weaken the public/internal boundary checks by itself.
- Compatibility shims such as string equality on `ArtifactId` / `RouteTarget` and the preserved mapping-shaped `ctx.fan_in.results` public payload are documented in the decisions ledger and preserve existing user-facing behavior without reintroducing removed `Compiled*` dataclasses.
- Placeholder parsing/rendering is centralized in [botlane/core/placeholders.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/placeholders.py:18), and [botlane/core/artifacts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/artifacts.py:183) only delegates at the artifact boundary. That matches the request and is not a gap.

# Recommended next run

- Run a focused architecture-conformance cleanup, not a full reimplementation.
- Scope the next run to:
  - remove `_route_table` storage and any step-plan route ownership so all route views derive from `WorkflowPlan.routes` / `WorkflowPlan.global_routes`,
  - complete the execution-service cutover so services and collaborators no longer hold `Engine` or call its private methods,
  - collapse SDK one-step execution to exactly one canonical internal architecture and delete the alternate path,
  - remove the residual `StepExecutionResult.transition` parallel representation if it is no longer needed after the service and one-step cleanup,
  - update strictness/contract tests so these constraints are enforced directly and cannot regress while keeping the full pytest suite green.
