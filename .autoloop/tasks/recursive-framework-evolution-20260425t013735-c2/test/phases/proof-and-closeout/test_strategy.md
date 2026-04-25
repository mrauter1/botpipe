# Test Strategy

- Task ID: recursive-framework-evolution-20260425t013735-c2
- Pair: test
- Phase ID: proof-and-closeout
- Phase Directory Key: proof-and-closeout
- Phase Title: Proof And Closeout
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Shared parameter bundle normalization and exported seam identity
  - Covered by `tests/unit/test_stdlib_and_extensions.py::test_parameter_model_bundles_preserve_shared_task_and_selected_workflow_normalization`
  - Checks trimmed required text, optional text normalization, deduped string lists, positive-int inheritance, and stdlib export identity.
- Workflow-local subclasses preserve inherited validation and local deltas
  - Covered by `tests/unit/test_stdlib_and_extensions.py::test_workflow_specific_parameter_models_keep_inherited_selected_workflow_validation`
  - Checks refinement/decomposition subclasses keep inherited selected-workflow validation while preserving workflow-local fields.
- Shared loader-backed helpers preserve failure behavior
  - Covered by:
    - `tests/unit/test_stdlib_and_extensions.py::test_adaptation_helpers_preserve_shared_loader_failure_for_unknown_workflow_parameters`
    - `tests/unit/test_stdlib_and_extensions.py::test_evaluation_helper_preserves_shared_loader_failure_for_invalid_case_parameters`
  - Checks unknown workflow parameters still fail through the shared loader path.
- CLI workflow-parameter compatibility stays intact
  - Covered by `tests/runtime/test_package_cli.py`
  - Checks unknown and duplicate `-wf` handling plus CLI parameter reporting.
- Runtime typed-parameter persistence stays intact
  - Covered by `tests/runtime/test_workspace_and_context.py`
  - Checks `ctx.params`, `ctx.workflow_params`, pause/resume persistence, and validation before run metadata is written.
- Migrated workflow family still resolves `Parameters` and preserves coercion behavior
  - Covered by:
    - `tests/runtime/test_task_to_candidate_workflow_set.py`
    - `tests/runtime/test_task_to_workflow_strategy.py`
    - `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
    - `tests/runtime/test_workflow_to_eval_suite.py`
    - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
    - `tests/runtime/test_workflow_portfolio_to_operating_system.py`
    - `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
    - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
    - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - Checks `resolve_workflow_reference(...).parameters_cls`, parameter coercion happy paths, blank required text failures, unknown-parameter failures where applicable, and workflow-local special cases such as sorted statuses.
- Architecture and authoring contract remain synchronized with the seam
  - Covered by `tests/test_architecture_baseline_docs.py`
  - Checks the docs still describe the narrow authoring/runtime boundary and the shared parameter-model guidance.

## Preserved invariants checked

- CLI `-wf` behavior remains unchanged.
- Runtime parameter resolution order remains unchanged.
- Local workflow `Parameters` exports remain discoverable.
- `ctx.params` and `ctx.workflow_params` remain consistent.
- Shared seam stays additive under `stdlib/` and does not widen runtime/provider behavior.

## Edge cases

- Blank required text values.
- Deduped repeated string inputs with surrounding whitespace.
- Positive-int validation on inherited subclasses.
- Workflow-specific local normalization such as sorted `statuses`.
- Duplicate and unknown CLI `-wf` inputs.

## Failure paths

- Unknown workflow parameters rejected by loader-backed helpers.
- Invalid per-case evaluation workflow parameters rejected.
- Invalid workflow params rejected before run metadata persists.
- Duplicate single-value CLI parameters rejected.

## Determinism / flake control

- Uses repository-local fixtures and synchronous filesystem assertions only.
- No network, sleep, timing, or nondeterministic ordering dependency is introduced.
- Status ordering checks rely on sorted output where the workflow intentionally preserves that behavior.

## Known gaps

- No new repository test assertions were added in this phase because the existing scoped suites already cover the shared seam and migrated workflow family.
- Full-repo regression expansion remains intentionally out of scope for this phase.

## Proof run

- Command:
  - `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_package_cli.py tests/runtime/test_workspace_and_context.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/test_architecture_baseline_docs.py`
- Result: `357 passed in 33.50s`
