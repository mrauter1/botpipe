# Follow-up request: finish the remaining second-pass architecture conformance cleanup

Preserve the public Botlane API and current user-facing behavior, but finish the remaining internal greenfield constraints from the original second-pass spec.

The current tree is functionally green and the full pytest suite passes, but several internal architecture requirements are still not met:

1. `WorkflowPlan.routes` is not yet the sole route authority.
   - Remove private step-plan route-table ownership (`_route_table` and route-view derivation from it).
   - Make all runtime and inspection route views derive from `WorkflowPlan.routes` / `WorkflowPlan.global_routes` only.

2. `ExecutionServices` is still a bridge over `Engine`.
   - Finish the service-boundary cutover so services and collaborators no longer hold `Engine` or call `Engine` private methods.
   - `StepDispatcher`, `ProviderContractBuilder`, `BranchGroupRuntime`, route finalization, hook execution, and related collaborators must depend on narrow services instead of `Engine`.

3. SDK one-step execution still keeps two internal architectures alive.
   - Collapse `Botlane.step(...)` to exactly one canonical one-step architecture.
   - Remove the alternate path so the SDK no longer builds both `SingleStepPlan` and a one-step `WorkflowPlan` in parallel.
   - If the canonical path still needs single-step planning metadata, keep only the minimal canonical representation and delete the redundant one.

4. Remove the remaining parallel step-finalization representation.
   - `StepExecutionResult` should keep the canonical `route_decision` / `action` flow and should not carry a second transition/finalization record once the above cutovers are complete.

Required guardrails:

- Do not change `botlane.__all__`, `botlane.core.__all__`, or the preserved public SDK behavior.
- Keep `.botlane` identity and all current public route/artifact/input behavior unchanged.
- Keep the full pytest suite green.
- Update strictness/contract coverage so the remaining architectural constraints are enforced directly and cannot regress.
