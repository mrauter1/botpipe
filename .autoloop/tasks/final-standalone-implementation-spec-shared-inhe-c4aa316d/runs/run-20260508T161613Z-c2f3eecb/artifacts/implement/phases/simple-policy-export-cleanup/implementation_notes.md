# Implementation Notes

- Task ID: final-standalone-implementation-spec-shared-inhe-c4aa316d
- Pair: implement
- Phase ID: simple-policy-export-cleanup
- Phase Directory Key: simple-policy-export-cleanup
- Phase Title: Clean Up Simple Policy Exports
- Scope: phase-local producer artifact

## Files Changed
- `autoloop/simple.py`
- `tests/unit/test_simple_policy.py`
- `.autoloop/tasks/final-standalone-implementation-spec-shared-inhe-c4aa316d/runs/run-20260508T161613Z-c2f3eecb/decisions.txt`

## Symbols Touched
- `autoloop.simple._SimplePolicyInput`
- `autoloop.simple.Workflow.policy`
- `autoloop.simple.StepDeclaration`
- `autoloop.simple.ProduceVerifyStepDeclaration`
- `autoloop.simple.PythonStepDeclaration`
- `autoloop.simple._WorkflowStepDeclaration`
- `autoloop.simple.step`
- `autoloop.simple.produce_verify_step`
- `autoloop.simple.python_step`
- `autoloop.simple.workflow_step`
- `autoloop.simple._normalize_provider_policy`
- `autoloop.simple.LLMOperation.__call__`
- `autoloop.simple.ClassifyOperation.__call__`
- `tests.unit.test_simple_policy.test_policy_input_export_matrix_matches_phase_contract`

## Checklist Mapping
- Milestone 1 (`autoloop.simple` leaked alias cleanup without behavior change): completed
- Validation plan targets from `plan.md`: completed

## Assumptions
- Only `autoloop.simple` leaked `PolicyInput` and `ProviderPolicyInput`; canonical exports in `autoloop.policy` and `autoloop.sdk` remain correct and unchanged.

## Preserved Invariants
- `autoloop.policy.PolicyInput` stays public.
- `autoloop.sdk.PolicyInput` stays public and identical to `autoloop.policy.PolicyInput`.
- Simple declarations and inline operations still accept `Policy`, `ProviderPolicy`, `ProviderPolicyOverride`, and `None`.
- `_normalize_provider_policy()` runtime type checks and behavior remain unchanged.

## Intended Behavior Changes
- `autoloop.simple` no longer binds public `PolicyInput`.
- `autoloop.simple` no longer binds public `ProviderPolicyInput`.

## Known Non-Changes
- No changes to `autoloop.policy.PolicyInput`.
- No changes to `autoloop.sdk.PolicyInput`.
- No changes to provider-policy merge semantics or accepted runtime values.

## Expected Side Effects
- `from autoloop.simple import PolicyInput` now fails.
- `getattr(autoloop.simple, "PolicyInput")` now raises `AttributeError`.
- `from autoloop.simple import ProviderPolicyInput` now fails.

## Deduplication / Centralization
- Kept a single private `_SimplePolicyInput` alias in `autoloop.simple` rather than duplicating unions across declarations and helper signatures.

## Validation Performed
- `./.venv/bin/pytest tests/unit/test_simple_policy.py`
- `./.venv/bin/pytest tests/unit/test_simple_surface.py tests/unit/test_policy.py tests/runtime/test_sdk_policy.py tests/unit/test_sdk_facade.py`
