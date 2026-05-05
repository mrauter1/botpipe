# Test Author ↔ Test Auditor Feedback

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: test
- Phase ID: authoring-and-compile-model
- Phase Directory Key: authoring-and-compile-model
- Phase Title: Authoring And Compile Model
- Scope: phase-local authoritative verifier artifact

- Added compile-time regression coverage for `fan_out(...)` branch input/order metadata, unsafe branch-group and branch names, `FanIn.context()` / `{fan_in.*}` misuse outside fan-in, and non-fresh `verifier_session` rejection inside branch groups. Re-ran `tests/unit/test_simple_surface.py` and adjacent compile validation coverage.
- Extended the composite compile-shape test to prove nested branch declarations stay out of the top-level compiled workflow, and added explicit child-workflow branch-step rejection coverage for `parallel(...)`.

## Findings

- TST-001 [blocking] `tests/unit/test_simple_surface.py::test_parallel_branch_group_compiles_as_one_external_step_with_ordered_internal_specs`: the test claims AC-1 coverage for “one external workflow step,” but it never asserts that internal branch declarations are absent from the top-level compiled workflow. A regression that re-emits `security_review` / `cost_review` as ordinary top-level compiled steps would still pass the current suite as long as the composite metadata is also present. Minimal correction: extend the existing compile-shape test to assert that only the composite branch-group step is exposed at top level for the nested branch declarations, for example by checking `compiled.steps` / `compiled.routes` do not contain the branch-step names.

- TST-002 [blocking] `tests/unit/test_simple_surface.py` branch-group validation coverage: the phase contract and v1 spec both require unsupported branch step kinds to fail compilation, including child-workflow branch steps, but the suite only checks child-workflow rejection for `fan_in`. If a regression stops rejecting `simple.workflow_step(...)` inside `parallel(...)` or `fan_out(...)`, the current tests would silently accept an out-of-scope branch kind. Minimal correction: add a compile-time regression test that uses a child workflow as a branch step and asserts the branch-step-specific validation error.
