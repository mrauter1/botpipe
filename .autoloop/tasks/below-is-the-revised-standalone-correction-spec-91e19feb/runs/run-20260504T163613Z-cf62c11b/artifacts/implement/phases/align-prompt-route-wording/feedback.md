# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-standalone-correction-spec-91e19feb
- Pair: implement
- Phase ID: align-prompt-route-wording
- Phase Directory Key: align-prompt-route-wording
- Phase Title: Align Prompt Route Wording
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 | blocking | `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py::test_company_operation_to_recursive_improvement_cycle_compiles_with_explicit_control_contracts` and the other five runtime suites named in AC-3 still fail under full-suite execution, so the phase does not satisfy the requirement that the updated runtime prompt-package suites "pass". Independent verification with `python -m pytest` against the six full files still fails immediately, for example at [tests/runtime/test_company_operation_to_recursive_improvement_cycle.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_company_operation_to_recursive_improvement_cycle.py:105) where `frame_step.available_routes` does not match the test's expected `question`/`blocked`/`failed` route set. Minimal fix direction: either make the six named suites green when run as full files, or obtain an explicit clarification that narrows AC-3 to prompt-only node coverage before marking this phase complete.
