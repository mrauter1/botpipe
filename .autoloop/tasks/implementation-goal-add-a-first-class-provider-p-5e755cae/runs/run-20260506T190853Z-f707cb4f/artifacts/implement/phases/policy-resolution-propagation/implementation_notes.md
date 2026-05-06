# Implementation Notes

- Task ID: implementation-goal-add-a-first-class-provider-p-5e755cae
- Pair: implement
- Phase ID: policy-resolution-propagation
- Phase Directory Key: policy-resolution-propagation
- Phase Title: Resolution And Propagation
- Scope: phase-local producer artifact

## Files changed
- `autoloop/runtime/provider_policy_resolver.py`
- `autoloop/core/compiler.py`
- `autoloop/core/providers/models.py`
- `autoloop/core/providers/rendered.py`
- `autoloop/core/providers/rendering.py`
- `autoloop/core/providers/turns.py`
- `autoloop/core/operations.py`
- `autoloop/core/providers/fake.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/engine.py`
- `autoloop/core/branch_groups/runtime.py`
- `autoloop/runtime/runner.py`
- `autoloop/runtime/cli.py`
- `tests/runtime/test_provider_policy_steps.py`

## Symbols touched
- `ProviderPolicyResolver.resolve_for_step`
- `ProviderPolicyResolver.resolve_for_operation`
- `CompiledWorkflow.provider_policy`
- `CompiledStep.provider_policy`
- `ProviderTurnContext.policy`
- `ProducerRequest.policy`
- `VerifierRequest.policy`
- `LLMRequest.policy`
- `OperationRequest.policy`
- `RenderedProviderTurn.policy`
- `OperationRuntime.policy`
- `OperationRuntime.provider_policy_resolver`
- `llm_call(..., policy=...)`
- `classify_call(..., policy=...)`
- `RunnerOptions.provider_policy_config`

## Checklist mapping
- Plan milestone 3 completed for compiled workflow and step policy metadata, topology hash participation, resolver introduction, request propagation, inline `policy=` overrides, and replay fingerprint expansion.
- Phase AC-1 covered by new runtime tests for workflow inheritance, step overrides, reusable policy reuse, strict rejection on step and inline paths, and python-step inline inheritance.
- Phase AC-2 covered by new topology-hash and operation-replay fingerprint tests plus existing replay contract regression coverage.

## Preserved invariants
- Provider backend dispatch remains backend-selection-only.
- No provider-specific emission or CLI config-file writing was added in this phase.
- Existing provider request surfaces remain backward compatible because all new policy fields default to `None`.
- Inline provider calls without an explicit `policy=` continue to work; they now inherit the current step policy only when a workflow runtime binding exists.

## Intended behavior changes
- Effective provider policy now resolves once per executing provider-capable step and is propagated to provider requests, rendered turns, and inline operations.
- Workflow and step policy changes now affect compiled topology hashes.
- Operation replay fingerprints now include the effective policy fingerprint.

## Known non-changes
- No provider-specific policy emission, capability reporting, or subprocess wiring landed here.
- Child-workflow invocation steps still do not consume provider policy in this phase.

## Side effects and centralization
- Centralized runtime policy ownership in `ProviderPolicyResolver` plus the operation-recorder binding seam rather than duplicating merge logic in provider transports or operation helpers.
- Reused the same step-binding seam for branch-group branch and fan-in execution so nested inline operations do not bypass policy resolution.

## Validation performed
- `./.venv/bin/python -m py_compile autoloop/runtime/provider_policy_resolver.py autoloop/core/compiler.py autoloop/core/providers/models.py autoloop/core/providers/rendered.py autoloop/core/providers/rendering.py autoloop/core/providers/turns.py autoloop/core/operations.py autoloop/core/providers/fake.py autoloop/core/engine_collaborators.py autoloop/core/engine.py autoloop/core/branch_groups/runtime.py autoloop/runtime/runner.py autoloop/runtime/cli.py tests/runtime/test_provider_policy_steps.py`
- `./.venv/bin/python -m pytest -q tests/runtime/test_provider_policy_steps.py`
- `./.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py -k 'policy or operation_surface_singletons'`
- `./.venv/bin/python -m pytest -q tests/unit/test_provider_boundary_core.py -k 'operation or rendered'`
- `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k 'operation_replay_fingerprint or operation_replay_override'`

## Assumptions
- The runner handoff only needs `provider_policy_config`; provider selection and legacy provider-field mapping were already resolved in the previous config phase.
- Using an ephemeral `Context._provider_policy` slot is acceptable for this phase because contexts are step-scoped runtime objects, not persisted user API surfaces.
