# Original intent considered

- Implement a greenfield ordered/selectable/progress-tracked worklist system with:
  - generic core selector support in `autoloop/core/worklists.py`,
  - stdlib canonical progress JSON worklists in `autoloop/stdlib/worklists.py`,
  - concise authoring via `progress_artifact_worklist("phase", model=..., fallback=...)`,
  - new focused selector/stdlib/runtime tests,
  - no legacy aliases or board-shape compatibility shims.
- The request also required that new tests pass and existing tests continue to pass.

# Clarifications / superseding decisions

- Plan and decisions explicitly treated selector-bound params under `mode=all` as an intentional compatibility break required by the new core selector contract.
- Later verifier findings (`IMP-001`, `IMP-002`) in the runtime-validation phase justified additional integration changes outside the original file list:
  - repo-root inference had to recognize repo-local `workflows/`,
  - workflow catalog discovery/import had to treat `<repo>/workflows` as a first-class source.
- Later decisions also justified keeping helper outputs scoped to workspace-discovered workflows and updating adjacent tests to the repo-local `workflows/` path/module shape.

# Implemented behavior

- Core selector contract is present in `autoloop/core/worklists.py`:
  - `Selector` now supports exactly `all`, `single`, `up_to`, and `from_to`,
  - selection is resolved in `Worklist`,
  - `Worklist.artifact` exposes the backing artifact when present.
- Stdlib canonical progress worklists are present in `autoloop/stdlib/worklists.py` and exported from `autoloop/stdlib/__init__.py`:
  - `WorkStatus`, `WorkStatusPolicy`, `SKIPPABLE_WORK_STATUS_POLICY`,
  - `ProgressItem`, `ProgressBoard`,
  - `ProgressJsonCollectionSource`,
  - `progress_selector`,
  - `progress_artifact_worklist`.
- Requested focused tests exist and pass on direct rerun:
  - `.venv/bin/python -m pytest tests/unit/test_worklist_selectors.py tests/unit/test_stdlib_progress_worklists.py tests/runtime/test_progress_worklists.py`
  - Result: `49 passed`.
- The requested adjacent regression command also passes on direct rerun:
  - `.venv/bin/python -m pytest tests/unit/test_stdlib_and_extensions.py tests/unit/test_primitives_and_stores.py tests/runtime/test_workspace_and_context.py`
  - Result: `173 passed`.
- The repo-local workflow catalog regression file added during the runtime-validation follow-up also passes on direct rerun:
  - `.venv/bin/python -m pytest tests/runtime/test_workflow_catalog_roots.py`
  - Result: `20 passed`.

# Unresolved gaps

- Material gap: the final tree is not globally green, so the request’s acceptance criterion that existing tests continue to pass is not met.
  - Direct evidence:
    - `.venv/bin/python -m pytest`
    - Result: `90 failed, 1119 passed, 616 warnings in 67.84s`.
- Failure cluster 1: broader workflow reference/discovery/import contracts are still inconsistent after the repo-local `workflows/` follow-up.
  - Direct evidence:
    - `tests/runtime/test_workflow_reference_resolution.py` -> `5 failed, 7 passed`.
  - Concrete failures:
    - repo-local flow packages are now rejected unless they re-export the workflow class from `__init__.py`,
    - manifest aliases from the workspace catalog root do not resolve,
    - named resolution now prefers `<repo>/workflows/...` where some tests still require `.autoloop/workflows/...`,
    - explicit class references now expose `workflows.*` parameter modules instead of the isolated `_autoloop_workspace_workflows.*` namespace expected by existing tests.
- Failure cluster 2: optimization-helper contracts were not updated coherently with the repo-local workflow path change.
  - Direct evidence:
    - `tests/unit/test_optimization_helpers.py` -> `10 failed, 19 passed`.
  - Concrete failures:
    - observability bundles that previously validated now fail `validate_observability_bundle(...)`,
    - normalized trace corpora drop all eligible runs in cases that previously produced observations,
    - selected-workflow source manifests now emit `workflows/...` paths where existing helper tests still require `autoloop/workflows/...`,
    - downstream mutation-detection tests still look for files under the old path.
- Failure cluster 3: multiple packaged workflow runtime/contract tests remain broken.
  - Direct evidence from the full-suite summary:
    - failures remain in `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`,
      `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`,
      `tests/runtime/test_incident_to_hardening_program.py`,
      `tests/runtime/test_investigation_request_to_evidence_pack.py`,
      `tests/runtime/test_security_finding_to_verified_remediation.py`,
      `tests/runtime/test_task_to_candidate_workflow_set.py`,
      `tests/runtime/test_task_to_workflow_strategy.py`,
      `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`,
      `tests/runtime/test_workflow_package_to_composable_building_blocks.py`,
      `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`,
      and others.
  - Representative concrete failures:
    - compile contracts missing expected `blocked` / `failed` routes,
    - runtime package execution missing required framework artifacts such as `framework_architecture_doc`,
    - workflow-builder / workflow-package tests still encode the older repo path/layout contract.
- Inference from the failure clustering above:
  - the worklist feature itself is implemented and locally validated,
  - the later repo-local `workflows/` discovery/import follow-up fixed the narrow adjacent gates but did not restore the broader repository-wide workflow reference, package-contract, and optimization-helper expectations.

# Differences justified by later clarification or analysis

- Additional product changes outside the original requested file list were justified.
  - `autoloop/core/context.py`,
    `autoloop/core/workflow_catalog.py`,
    `autoloop/runtime/loader.py`,
    `autoloop/core/workflow_capabilities.py`,
    `autoloop_optimizer/portfolio.py`,
    `tests/runtime/test_workflow_catalog_roots.py`,
    and `tests/unit/test_stdlib_and_extensions.py`
    were changed only after adjacent tests exposed direct runtime integration bugs in repo-root and workflow discovery behavior.
- Exporting `SKIPPABLE_WORK_STATUS_POLICY` and `progress_selector` is within the original request’s optional allowance.
- No evidence was found that root `autoloop/__init__.py`, provider internals, checkpoint internals, session internals, or route internals were modified for the worklist feature itself.

# Recommended next run

- Do not re-implement the worklist feature.
- Run a follow-up compatibility pass focused on restoring full-suite green status while preserving the new worklist system and the already-green focused/adjacent suites.
- Scope that next run to the unresolved contract surfaces exposed by the full suite:
  - reconcile repo-local `workflows/` support with the broader workflow reference-resolution contract,
  - update or restore optimization-helper path/observability expectations coherently,
  - fix packaged-workflow compile/runtime regressions caused or surfaced by the repo-local discovery/import changes,
  - rerun `pytest` until the full suite is green.
