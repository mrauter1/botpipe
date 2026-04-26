# Test Strategy

- Task ID: recursive-framework-evolution-20260426t124100-c1
- Pair: test
- Phase ID: typed-publication-contracts
- Phase Directory Key: typed-publication-contracts
- Phase Title: Typed Publication Contracts
- Scope: phase-local producer artifact

## Coverage Map

- Behavior covered: workflow-local typed publication artifact specs exist for the scoped governance/company/diagnostic family.
  - Tests:
    - `tests/unit/test_stdlib_and_extensions.py::test_split_summary_artifact_specs_match_on_disk_json_shapes`
- Behavior covered: the new typed specs accept stable on-disk JSON without renaming filenames, keys, or publication-boundary literals.
  - Tests:
    - `tests/unit/test_stdlib_and_extensions.py::test_split_summary_artifact_specs_match_on_disk_json_shapes`
- Behavior covered: the new typed specs reject missing required durable fields before workflow-local publish policy runs.
  - Tests:
    - `tests/unit/test_stdlib_and_extensions.py::test_typed_publication_artifact_specs_report_missing_required_fields`
- Preserved invariant checked: workflow-local publication policy remains outside the typed artifact seam and still runs in the existing publish-handler runtime suites.
  - Tests:
    - `tests/runtime/test_workflow_portfolio_to_operating_system.py`
    - `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
    - `tests/runtime/test_workflow_run_history_to_failure_modes.py`

## Edge Cases

- Missing `publication_boundary` on the typed portfolio summary artifact.
- Missing `priority_category_counts` on the typed recursive-improvement summary artifact.
- Missing `failure_modes` on the typed diagnostic manifest.
- Missing `ready_for_publication` on the typed improvement-opportunities summary artifact.

## Failure Paths

- `JsonArtifactSpec.validate(...)` must return a non-OK report with the expected field locations for malformed scoped publication artifacts.
- Existing runtime publish tests remain the source of truth for invalid publication boundary values, hidden execution text, unknown references, and cross-artifact drift.

## Known Gaps

- No new runtime scenarios were added in this phase because the existing scoped runtime suites already cover workflow-local policy and regression-sensitive publish behavior.
- Refinement/decomposition publication-surface follow-ons remain intentionally out of scope for this phase.
