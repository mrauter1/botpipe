# Implementation Notes

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: implement
- Phase ID: repair-packaged-workflow-contracts-and-proof
- Phase Directory Key: repair-packaged-workflow-contracts-and-proof
- Phase Title: Repair Packaged Workflow Contracts And Proof
- Scope: phase-local producer artifact

## Files Changed

- Product contract surfaces:
  `autoloop/core/artifacts.py`,
  `autoloop/core/compiler.py`,
  `autoloop/core/discovery.py`,
  `autoloop/core/hook_validation.py`,
  `autoloop/core/workflow_capabilities.py`,
  `autoloop/runtime/loader.py`,
  `autoloop/runtime/runner.py`,
  `autoloop_optimizer/candidate_surfaces.py`
- Packaged workflows:
  `autoloop/workflows/candidate_workflow_to_adapted_execution_plan/{contracts.py,workflow.py}`,
  `autoloop/workflows/company_operation_to_recursive_improvement_cycle/workflow.py`,
  `autoloop/workflows/incident_to_hardening_program/{contracts.py,workflow.py}`,
  `autoloop/workflows/investigation_request_to_evidence_pack/{contracts.py,workflow.py}`,
  `autoloop/workflows/release_candidate_to_go_no_go/workflow.py`,
  `autoloop/workflows/security_finding_to_verified_remediation/contracts.py`,
  `autoloop/workflows/task_to_candidate_workflow_set/{contracts.py,workflow.py}`,
  `autoloop/workflows/task_to_workflow_strategy/{contracts.py,workflow.py}`,
  `autoloop/workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`,
  `autoloop/workflows/workflow_idea_to_workflow_package/workflow.py`,
  `autoloop/workflows/workflow_package_to_composable_building_blocks/workflow.py`,
  `autoloop/workflows/workflow_portfolio_to_operating_system/workflow.py`,
  `autoloop/workflows/workflow_run_history_to_failure_modes/workflow.py`,
  `autoloop/workflows/workflow_run_traces_to_optimization_candidates/{contracts.py,workflow.py}`,
  `autoloop/workflows/workflow_to_eval_suite/workflow.py`
- Test contracts updated to restored shared behavior:
  `tests/contract/test_canonical_runtime_contracts.py`,
  `tests/contract/test_engine_contracts.py`,
  `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`,
  `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`,
  `tests/runtime/test_incident_to_hardening_program.py`,
  `tests/runtime/test_investigation_request_to_evidence_pack.py`,
  `tests/runtime/test_release_candidate_to_go_no_go.py`,
  `tests/runtime/test_runtime_providers.py`,
  `tests/runtime/test_runtime_static_graph.py`,
  `tests/runtime/test_security_finding_to_verified_remediation.py`,
  `tests/runtime/test_task_to_candidate_workflow_set.py`,
  `tests/runtime/test_task_to_workflow_strategy.py`,
  `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`,
  `tests/runtime/test_workflow_builder_package.py`,
  `tests/runtime/test_workflow_package_to_composable_building_blocks.py`,
  `tests/runtime/test_workflow_portfolio_to_operating_system.py`,
  `tests/runtime/test_workflow_reference_resolution.py`,
  `tests/runtime/test_workflow_run_history_to_failure_modes.py`,
  `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`,
  `tests/runtime/test_workflow_to_eval_suite.py`,
  `tests/runtime/test_workspace_and_context.py`,
  `tests/unit/test_simple_surface.py`,
  `tests/unit/test_stdlib_and_extensions.py`,
  `tests/unit/test_validation.py`

## Symbols Touched

- `autoloop.core.artifacts`: root placeholder resolution
- `autoloop.core.compiler`: python-step handler arity support
- `autoloop.core.discovery`: framework-default runtime-control route injection
- `autoloop.core.workflow_capabilities`: selected-workflow authoring/decomposition repo-relative surfaces
- `autoloop.runtime.loader`: isolated repo-local package namespace handling
- `autoloop.runtime.runner`: child workflow result context root propagation
- `autoloop_optimizer.candidate_surfaces`: baseline source-entry normalization and validation

## Checklist Mapping

- Shared route-contract fixes:
  added default `blocked`/`failed` runtime-control expectations across packaged workflow contracts and contract/static-graph tests.
- Shared artifact-path fixes:
  added `{root}` artifact support, switched packaged workflow shared-doc references to `{root}`, and propagated `root` into child workflow synthetic contexts.
- Package-boundary/publish validation fixes:
  separated canonical publication labels from actual selected-workflow source bytes and carried `baseline_source_entries` through refinement/decomposition validators.
- Final proof:
  reran targeted packaged-workflow slices, acceptance-adjacent suites, and full repository pytest.

## Assumptions

- Framework-default `blocked`/`failed` routes are part of the intended provider/runtime contract for prompt-driven steps, not a regression to suppress.
- First-party package publication labels should remain canonical `autoloop/workflows/...` even when the selected source lives under repo-local `workflows/...`.

## Preserved Invariants

- Greenfield worklist selector semantics and strict progress-board shape were left intact.
- No legacy selector aliases or progress-board compatibility shims were introduced.
- Repo-local `workflows/` discovery/import support remained enabled.
- Shared fixes were centralized in runtime/discovery/capability helpers instead of adding product-only test shims.

## Intended Behavior Changes

- Prompt/provider contracts now consistently expose default `blocked`/`failed` runtime-control routes wherever provider-driven steps are compiled or rendered.
- Selected-workflow refinement/decomposition manifests now retain both canonical package labels and actual source-path provenance.

## Known Non-Changes

- No rework of the accepted greenfield worklist API.
- No change to stdlib progress worklist payload shape.

## Expected Side Effects

- Contract/static-graph snapshots and provider request surfaces now show wider default runtime-control metadata.
- First-party selected-workflow snapshot repo-relative fields may be `autoloop/workflows/...` while actual source files remain under repo-local `workflows/...`.

## Validation Performed

- Targeted packaged-workflow cluster from the request: `252 passed`
- Residual contract/static-graph/workspace group:
  `tests/contract/test_canonical_runtime_contracts.py`
  `tests/contract/test_engine_contracts.py`
  `tests/unit/test_simple_surface.py`
  `tests/unit/test_validation.py`
  `tests/runtime/test_runtime_static_graph.py`
  `tests/runtime/test_workspace_and_context.py`
  Result: `364 passed`
- Remaining reference/runtime group:
  `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
  `tests/runtime/test_release_candidate_to_go_no_go.py`
  `tests/runtime/test_workflow_portfolio_to_operating_system.py`
  `tests/runtime/test_workflow_to_eval_suite.py`
  `tests/runtime/test_workflow_reference_resolution.py`
  Result: `115 passed`
- Refinement/decomposition group:
  `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  Result: `59 passed`
- Focused stdlib/run-history regression group:
  `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  `tests/unit/test_stdlib_and_extensions.py`
  Result: `119 passed`
- Full repository:
  `.venv/bin/python -m pytest`
  Result: `1214 passed, 616 warnings`

## Deduplication / Centralization Decisions

- Kept provider-route widening centralized in discovery/runtime metadata instead of hand-authoring `blocked`/`failed` routes into every expectation surface.
- Kept canonical-label vs actual-source-path handling centralized in selected-workflow capability and candidate-surface helpers so refinement/decomposition suites share one boundary contract.
