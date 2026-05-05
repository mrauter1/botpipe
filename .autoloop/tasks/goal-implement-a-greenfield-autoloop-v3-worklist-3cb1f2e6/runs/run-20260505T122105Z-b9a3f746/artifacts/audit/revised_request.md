# Follow-up request: restore full-suite compatibility after the greenfield worklist landing

The greenfield worklist feature itself is implemented and the named focused/adjacent suites are green:

- `tests/unit/test_worklist_selectors.py`
- `tests/unit/test_stdlib_progress_worklists.py`
- `tests/runtime/test_progress_worklists.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/runtime/test_workspace_and_context.py`
- `tests/runtime/test_workflow_catalog_roots.py`

Do not rework the new worklist feature unless a failing full-suite test proves a real regression in it.

## Remaining problem

The repository is not globally green. A direct full-suite rerun currently reports:

- `.venv/bin/python -m pytest`
- Result: `90 failed, 1119 passed, 616 warnings`

This means the original acceptance criterion that existing tests continue to pass is still unmet.

## Next-run scope

Fix the broader compatibility regressions caused or surfaced by the runtime-validation follow-up that added first-class repo-local `workflows/` discovery/import support.

Preserve these already-accepted behaviors:

- core selector semantics with canonical modes `all`, `single`, `up_to`, `from_to`,
- strict stdlib progress-board shape `items/id/title/status`,
- no legacy selector aliases or board-shape compatibility shims,
- `progress_artifact_worklist(...)` common-case authoring,
- repo-local `workflows/` support added during the runtime-validation phase,
- the currently green focused and adjacent suites listed above.

## Priority failure clusters to fix

1. Restore the broader workflow reference-resolution contract.

Evidence:

- `tests/runtime/test_workflow_reference_resolution.py` currently has 5 failures.

Concrete breakpoints now visible:

- repo-local flow packages are rejected unless they re-export the workflow class from `__init__.py`,
- manifest aliases from the workspace catalog root do not resolve,
- some named/workspace resolution paths now prefer `<repo>/workflows/...` where older contracts still expect `.autoloop/workflows/...`,
- explicit class references no longer preserve the existing isolated workspace module namespace contract.

2. Reconcile optimization-helper contracts with the new repo-local workflow source behavior.

Evidence:

- `tests/unit/test_optimization_helpers.py` currently has 10 failures.

Concrete breakpoints now visible:

- observability bundles that used to validate now fail validation,
- normalized trace corpora drop eligible runs and step observations,
- selected-workflow source manifests and mutation checks still assume the old `autoloop/workflows/...` path contract.

3. Fix the packaged-workflow compile/runtime regressions still present across the repository.

Evidence from the current full-suite run includes failures in:

- `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
- `tests/runtime/test_incident_to_hardening_program.py`
- `tests/runtime/test_investigation_request_to_evidence_pack.py`
- `tests/runtime/test_security_finding_to_verified_remediation.py`
- `tests/runtime/test_task_to_candidate_workflow_set.py`
- `tests/runtime/test_task_to_workflow_strategy.py`
- `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`

Representative observed symptoms:

- compile contracts missing expected `blocked` / `failed` routes,
- runtime execution failing on missing required framework artifacts such as `framework_architecture_doc`,
- workflow-package/builder/reference tests still out of sync with the new repo-local discovery/import behavior.

## Acceptance criteria for the next run

- The focused worklist suites remain green.
- The adjacent regression suites remain green.
- `tests/runtime/test_workflow_reference_resolution.py` is green.
- `tests/unit/test_optimization_helpers.py` is green.
- The currently failing packaged-workflow/runtime suites are green.
- A full repository run with `.venv/bin/python -m pytest` is green.

## Constraints

- Keep the greenfield worklist API and semantics intact unless a failing test proves a necessary correction.
- Do not add legacy compatibility shims for the progress worklist board shape or selector aliases.
- Prefer fixing shared discovery/reference/helper contracts centrally rather than patching many tests one by one without restoring a coherent product contract.
