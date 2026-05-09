# Original intent considered

The audit considered the immutable request in `request.md`, the full run ledger in `raw_phase_log.md`, the recorded implementation decisions in `decisions.txt`, the phase artifacts under `artifacts/plan`, `artifacts/implement`, and `artifacts/test`, the final Botlane codebase, and an independent final validation run.

The original intent was an internal-only Botlane architecture refactor that introduced stronger internal runtime/value-plan structures while freezing the public `botlane` root API, the simple authoring surface, the SDK surface, route sentinels, persistence/schema identity, and behavior compatibility.

# Clarifications / superseding decisions

There were no later user clarifications that changed product intent. The authoritative superseding execution decisions were implementation-shape decisions recorded in `decisions.txt`, including:

- `WorkflowPlan` would be introduced as an adapter layer first, with engine migration remaining optional until parity was proven.
- `RunPaths`/`RunIdentity` and `WorkflowLocator` would reuse existing `botlane.runtime.workspace` and `botlane.runtime.loader` ownership instead of introducing parallel path or loader systems.
- `CompiledWorkflow`, `CompiledStep`, and `CompiledRoute` would remain compatibility facades, with conversions centralized in `botlane/core/plan_adapters.py`.
- `SingleStepPlan` would remain an internal parity target, and `Botlane.step(...)` would stay on the existing synthetic-workflow execution path unless exact execution-path replacement was proven necessary and safe.
- `ExecutionServices` migration would begin with narrow seams rather than a whole-engine rewrite.

# Implemented behavior

The final codebase contains the requested internal primitives and adapters, including:

- `botlane/core/identifiers.py`, `run_paths.py`, `provider_policy_resolution.py`, `route_contracts.py`, `step_plans.py`, `workflow_plan.py`, `placeholders.py`, `reference_graph.py`, `execution_frame.py`, `execution_services.py`, `plan_adapters.py`
- `botlane/core/branch_groups/results.py`
- `botlane/runtime/workflow_locator.py`

The public frozen surfaces remain intact:

- `botlane/__init__.py` still exports the same public root `__all__`.
- `botlane/core/__init__.py` and `botlane/core/branch_groups/__init__.py` did not promote the new internal architecture types.
- `tests/unit/test_simple_surface.py` freezes the root and internal module export surfaces and exercises the simple authoring contract.
- `tests/unit/test_sdk_facade.py` covers SDK compatibility, dataclass positional compatibility, and Botlane persistence sentinel behavior.

The requested internal behaviors are present and tested:

- `ArtifactId`, `RunPaths`, and `RunIdentity` exist and are covered by `tests/unit/test_artifact_ids.py` and `tests/unit/test_run_paths.py`.
- The no-core-to-runtime import boundary is enforced by the AST-based `tests/strictness/test_core_runtime_boundary.py`.
- `ProviderPolicyResolverProtocol` exists in core, the runtime resolver satisfies it, and coverage exists in `tests/runtime/test_provider_policy_core_protocol.py`.
- `RouteContract`, `RouteDecision`, `RouteAction`, route-view helpers, and required-write inventory behavior are covered by `tests/unit/test_route_contracts.py`.
- `StepPlan` variants, `ProviderTurnPlan`, `WorkflowPlan`, and adapter round trips are covered by `tests/unit/test_step_plans.py` and `tests/unit/test_workflow_plan_adapters.py`.
- `ExecutionFrame` is wired behind `Context` and covered by `tests/unit/test_execution_frame_context_parity.py`.
- `PlaceholderRef` and `ReferenceGraph` are implemented and covered by `tests/unit/test_placeholder_refs.py`.
- `BranchResult` manifest parity and `WorkflowLocator` variants are covered by `tests/contract/test_branch_result_serialization.py` and `tests/runtime/test_workflow_locator_variants.py`.
- `ProviderTurnPlan` feeds the existing rendered-provider boundary and is covered by `tests/contract/test_provider_turn_plan_adapter.py`.
- `SingleStepPlan` exists as an internal parity adapter and is covered by `tests/contract/test_single_step_plan_equivalence.py`.

Independent final validation on the final codebase passed:

- `./.venv/bin/python -m pytest`
- Result: `1286 passed, 1 warning`

# Unresolved gaps

No material unresolved implementation gaps were found.

# Differences justified by later clarification or analysis

- `WorkflowPlan` remains primarily an adapter layer while core execution continues to rely on `CompiledWorkflow` compatibility paths in key places. This matches both the original spec’s explicit allowance and the later adapter-first decisions.
- `Botlane.step(...)` was not switched to execute through `SingleStepPlan`; instead, `SingleStepPlan` was added as an internal parity target with equivalence tests. This is explicitly allowed by the request and reinforced by the later run decisions.
- `ExecutionServices` was introduced incrementally rather than replacing all engine collaborator coupling in one pass. That is consistent with the spec’s phased migration rules and its explicit non-goal of a whole-engine rewrite.
- Persistence-identity coverage landed partly in existing suites such as `tests/unit/test_sdk_facade.py` and branch-manifest contract tests rather than in a dedicated new `tests/runtime/test_botlane_persistence_identity.py` file. The behavior is covered, so this is not a material gap.

# Recommended next run

No follow-up implementation run is required for this request.
