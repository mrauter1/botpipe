# Test Strategy

- Task ID: recursive-framework-evolution-20260425t013735-c1
- Pair: test
- Phase ID: converge-eval-helper-validation
- Phase Directory Key: converge-eval-helper-validation
- Phase Title: Converge Eval Helper Validation
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- Shared validation seam adoption in `stdlib/evaluation.py`
  - Covered by `tests/unit/test_stdlib_and_extensions.py::test_evaluation_helper_validates_eval_cases_via_selected_workflow_snapshot_and_loader_paths`
  - Checks happy-path reuse of `read_json_object(...)`, `validate_selected_workflow_capability_snapshot(...)`, and loader-based parameter coercion
- Shared snapshot-validator failure path
  - Covered by `tests/unit/test_stdlib_and_extensions.py::test_evaluation_helper_rejects_snapshot_mismatch_through_shared_snapshot_validator`
  - Checks that selected-workflow identity mismatch still fails through the shared validator after the refactor
- Preserved eval-manifest behavior and publish contract
  - Covered by `tests/unit/test_stdlib_and_extensions.py` eval-helper success/failure cases plus `tests/runtime/test_workflow_to_eval_suite.py::test_workflow_to_eval_suite_package_runs_and_publishes_terminal_eval_artifacts`
  - Checks artifact names, manifest payload keys, publish-step output, case ordering, expected-artifact coverage, and no downstream workflow execution

## Preserved Invariants Checked

- `validated_eval_case_manifest.json` top-level keys remain unchanged
- `workflow_to_eval_suite` still publishes the same authoritative artifact set
- Eval-specific case policy remains local: case-kind ordering, expected-artifact checks, and parameter coercion
- No `stdlib/validation.py` change, so no broadened shared-seam suite was required

## Edge Cases

- Single-file workflow references remain supported
- Duplicate case IDs, unsupported case kinds, blank prompts, empty expected artifacts, and invalid parameter shapes still fail deterministically
- Path escape and wrong output suffix validation still fail

## Failure Paths

- Shared snapshot identity mismatch now has an explicit regression test
- Unknown expected artifacts still fail before publication
- Invalid workflow parameters still surface the shared loader failure

## Known Gaps

- No additional `tests/unit/test_validation.py` or adjacent selected-workflow consumer suites were added because `stdlib/validation.py` did not change
- Flake risk is low; coverage uses deterministic local fixtures, monkeypatching, and filesystem-local assertions only
