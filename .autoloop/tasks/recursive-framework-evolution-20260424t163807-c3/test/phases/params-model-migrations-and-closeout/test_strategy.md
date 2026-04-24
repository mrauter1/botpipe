# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c3
- Pair: test
- Phase ID: params-model-migrations-and-closeout
- Phase Directory Key: params-model-migrations-and-closeout
- Phase Title: Migrate Params Models And Close Out
- Scope: phase-local producer artifact

## Behavior coverage map

- Shared `params.py` migration preserves generic normalization across the scoped workflow portfolio.
  - Covered by: existing targeted runtime parameter-normalization tests for builder, domain, portfolio, adaptation, evaluation, refinement, diagnostics, governance, decomposition, and company-operation workflows.
- Workflow-specific local exceptions remain intact after the migration.
  - Covered by:
    - `tests/runtime/test_workflow_builder_package.py::test_workflow_builder_package_rejects_invalid_package_name`
    - `tests/runtime/test_workflow_builder_package.py::test_workflow_builder_package_accepts_cli_style_flow_specs_parameter`
    - `tests/runtime/test_workflow_builder_package.py::test_workflow_builder_package_normalizes_optional_title_aliases_and_target_command`
    - existing investigation/security runtime parameter tests for literal pre-normalization
    - existing diagnostics runtime parameter test for sorted status output
- Shared positive-int validator routing preserves workflow-specific failure messages.
  - Covered by:
    - `tests/unit/test_stdlib_and_extensions.py::test_repo_workflow_parameter_models_preserve_positive_int_failures`
    - existing runtime happy-path normalization tests for `max_runs`, `max_runs_per_workflow`, `max_tasks`, and related limits
- Docs and recursive-memory closeout stays aligned with the new baseline.
  - Covered by: `tests/test_architecture_baseline_docs.py`

## Preserved invariants checked

- Workflow parameter names, defaults, repeatability, and normalization behavior remain unchanged.
- Generic parameter-model mechanics now come from stdlib without changing `runtime/loader.py` ownership of parameter coercion and error surfacing.
- No new workflow, runtime-owned validation automation, or `workflow.toml` semantic change is encoded in test expectations.

## Edge cases

- Duplicate aliases collapse deterministically while blank aliases are dropped.
- Blank optional text fields still normalize to `None`.
- CLI-style `authoring_shape=flow-specs` still normalizes to `flow_specs`.
- Positive-int limit fields still reject `0` with the workflow-specific error wording.

## Failure paths

- Invalid builder package identifiers still fail with `package_name`-specific errors.
- Shared-seam required-text failures still surface field-specific or explicitly configured messages.
- Unknown workflow parameters still fail through the shared loader path in existing adaptation/evaluation tests.

## Known gaps

- The suite relies on existing targeted runtime files rather than adding new per-workflow tests for every migrated `params.py`; coverage stays focused on representative generic behavior plus the intentionally local exceptions.
- No prompt-template compression assertions were added because that work is out of scope for this phase.
