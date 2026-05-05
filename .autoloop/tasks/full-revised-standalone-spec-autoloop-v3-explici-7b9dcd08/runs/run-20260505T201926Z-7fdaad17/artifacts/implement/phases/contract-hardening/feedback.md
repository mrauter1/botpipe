# Implement ↔ Code Reviewer Feedback

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: implement
- Phase ID: contract-hardening
- Phase Directory Key: contract-hardening
- Phase Title: Contract Hardening
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [`autoloop/core/branch_groups/validation.py::validate_fan_in_step_kind`, `tests/unit/test_simple_surface.py::test_branch_group_fan_in_accepts_supported_step_kinds`]: Operation-based fan-in declarations still compile even though the v1 contract narrows fan-in to prompt/LLM, produce/verify, and authored Python steps. `simple.llm.step(...)` lowers to an `OperationStepDeclaration`, but `validate_fan_in_step_kind()` only inspects the lowered runtime `Step` type, so the operation is treated as a plain `PythonStep` and accepted. Concrete failure: `simple.parallel(..., fan_in=simple.llm.step(...))` compiles today and the fan-in becomes a provider-backed operation handler hidden behind `PythonStep`, which contradicts the contract-hardening goal of rejecting unsupported authored fan-in kinds before runtime work begins. Minimal fix: centralize authored-kind inspection for fan-in validation the same way branch validation now checks `_simple_declaration_kind(step)`, reject `operation` fan-in declarations there, and update the fan-in-kind test to assert the contract instead of preserving the old behavior.
- IMP-001 resolution note: Re-reviewed in cycle 2 after the implementer patched `validate_fan_in_step_kind()` and replaced the old support-preserving test with a rejection test. Direct compile-time repro now raises `WorkflowValidationError`, and no additional findings remain in this phase scope.
