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

No active findings in this audit pass.

## Resolution Updates

- TST-001: resolved in cycle 2. `test_parallel_branch_group_compiles_as_one_external_step_with_ordered_internal_specs` now asserts the nested branch declarations do not appear in top-level `compiled.steps` or `compiled.routes`.
- TST-002: resolved in cycle 2. `test_branch_group_rejects_unsafe_names_child_workflow_fan_in_and_non_serializable_fan_out_inputs` now includes explicit child-workflow branch-step rejection coverage.
