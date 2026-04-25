# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c9
- Pair: test
- Phase ID: extract-shared-publication-validation
- Phase Directory Key: extract-shared-publication-validation
- Phase Title: Extract Shared Publication Validation
- Scope: phase-local producer artifact

## Behavior-to-Test Coverage Map

- `require_existing_artifact_paths`
  Covered by `tests/unit/test_validation.py::test_publication_validation_helpers_require_existing_artifacts_and_non_empty_text`.
  Checks happy path for existing artifact resolution and failure path for a missing required artifact.
- `read_required_text`
  Covered by `tests/unit/test_validation.py::test_publication_validation_helpers_require_existing_artifacts_and_non_empty_text`.
  Checks stripped non-empty reads and rejection of whitespace-only text artifacts.
- `validate_publication_boundary`
  Covered by `tests/unit/test_validation.py::test_publication_validation_helpers_validate_boundary_authoritative_subset_and_ready_flag` and `::test_publication_validation_helpers_preserve_missing_messages_and_require_literal_true`.
  Checks expected-boundary success, mismatch rejection, and missing/blank boundary rejection with the distinct missing-message path preserved.
- `validate_authoritative_artifact_subset`
  Covered by `tests/unit/test_validation.py::test_publication_validation_helpers_validate_boundary_authoritative_subset_and_ready_flag` and `::test_publication_validation_helpers_preserve_missing_messages_and_require_literal_true`.
  Checks valid superset acceptance, required-subset rejection, and missing list rejection.
- `require_true_flag`
  Covered by `tests/unit/test_validation.py::test_publication_validation_helpers_validate_boundary_authoritative_subset_and_ready_flag` and `::test_publication_validation_helpers_preserve_missing_messages_and_require_literal_true`.
  Checks literal `True` success, `False` rejection, and truthy-non-bool rejection to prevent accidental truthiness widening.
- `contains_hidden_execution_signal` / `validate_no_hidden_execution_signal`
  Covered by `tests/unit/test_validation.py::test_publication_validation_hidden_execution_helpers_reject_implicit_automation_and_allow_negation`.
  Checks hidden-execution detection, explicit-negation allowance, and rejection of implicit downstream automation text.

## Preserved Invariants Checked

- Shared publication helpers remain mechanical and do not encode workflow-specific package section rules, receipt shaping, or state drift policy.
- Missing-value errors remain distinguishable from mismatch errors for publication-boundary and authoritative-artifact validation.
- Readiness validation remains exact-boolean, not generic truthiness.
- Scoped runtime suites for the three migrated workflows still pass after helper extraction.

## Edge Cases and Failure Paths

- Missing publication artifacts.
- Whitespace-only required text artifacts.
- Blank publication-boundary fields.
- Authoritative-artifact lists that omit required package members.
- Hidden-execution phrasing with and without explicit negation.
- Truthy non-boolean readiness flags such as `1`.

## Validation Performed

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_validation.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/test_architecture_baseline_docs.py`

## Known Gaps

- This phase does not add new end-to-end publish-flow fixtures because the changed behavior is concentrated in shared helper mechanics, and the existing scoped runtime suites already exercise the migrated workflows against their local policy checks.
