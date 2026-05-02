# Implementation Notes

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: implement
- Phase ID: migrate-exported-workflow-contracts
- Phase Directory Key: migrate-exported-workflow-contracts
- Phase Title: Migrate Exported Workflow Packages
- Scope: phase-local producer artifact

## Files Changed

- Exported workflow packages:
  `workflows/autoloop_v1/workflow.py`
  `workflows/candidate_workflow_to_adapted_execution_plan/{contracts.py,workflow.py}`
  `workflows/company_operation_to_recursive_improvement_cycle/{contracts.py,workflow.py}`
  `workflows/incident_to_hardening_program/{contracts.py,workflow.py}`
  `workflows/investigation_request_to_evidence_pack/{contracts.py,workflow.py}`
  `workflows/release_candidate_to_go_no_go/{contracts.py,workflow.py}`
  `workflows/security_finding_to_verified_remediation/{contracts.py,workflow.py}`
  `workflows/task_to_candidate_workflow_set/{contracts.py,workflow.py}`
  `workflows/task_to_workflow_strategy/{contracts.py,workflow.py}`
  `workflows/workflow_and_eval_to_refined_workflow_package/{contracts.py,workflow.py}`
  `workflows/workflow_idea_to_workflow_package/{contracts.py,workflow.py}`
  `workflows/workflow_package_to_composable_building_blocks/{contracts.py,workflow.py}`
  `workflows/workflow_portfolio_to_operating_system/{contracts.py,workflow.py}`
  `workflows/workflow_run_history_to_failure_modes/{contracts.py,workflow.py}`
  `workflows/workflow_run_traces_to_optimization_candidates/{contracts.py,workflow.py}`
  `workflows/workflow_to_eval_suite/{contracts.py,workflow.py}`
- Shared test surface:
  `tests/runtime/workflow_contract_helpers.py`
  `tests/unit/test_simple_surface.py`
- Workflow runtime suites:
  `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
  `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
  `tests/runtime/test_incident_to_hardening_program.py`
  `tests/runtime/test_investigation_request_to_evidence_pack.py`
  `tests/runtime/test_release_candidate_to_go_no_go.py`
  `tests/runtime/test_security_finding_to_verified_remediation.py`
  `tests/runtime/test_task_to_candidate_workflow_set.py`
  `tests/runtime/test_task_to_workflow_strategy.py`
  `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  `tests/runtime/test_workflow_builder_package.py`
  `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  `tests/runtime/test_workflow_portfolio_to_operating_system.py`
  `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
  `tests/runtime/test_workflow_to_eval_suite.py`
- Justified dependency/regression fix:
  `autoloop_optimizer/candidate_surfaces.py`

## Symbols Touched

- Exported hook and step surfaces across the 16 packages, including `bootstrap`, capture-context steps, publish steps, and `after_verifier` hooks that now read from `ctx.outcome` and mutate `ctx.state`.
- Contract route tables in affected `contracts.py` files where downstream `python_step` targets could no longer carry `handoff=` metadata.
- Shared direct-invocation helpers:
  `invoke_python_step`
  `invoke_after_verifier_hook`
  `_normalize_control_result`
- Repo-level contract gates:
  `test_exported_public_simple_workflows_no_longer_fail_for_legacy_class_handlers`
  `test_discovered_exported_workflow_sources_avoid_removed_public_contract_forms`
- Overlay validator:
  `_is_runnable_repo_root`

## Checklist Mapping

- Milestone 1 complete:
  migrated exported hooks to `hook(ctx)`, removed hook state-replacement returns, converted remaining exported `python_step(state, ctx)` handlers to `python_step(ctx)`, and fixed lingering `ctx.state` regressions in package publish/capture steps.
- Milestone 2 complete:
  replaced legacy `WorkflowClass.on_*` direct calls with compiled-handler helpers, normalized direct-call assertions to the final control/event surface, and updated runtime metadata assertions from legacy `pending_question` to `pending_input`.
- Milestone 3 complete:
  enabled zero-failure discovered-package compile coverage and added raw-source regression checks for banned public-contract forms.

## Assumptions

- The final public runtime surface for paused runs is `pending_input`, with `pending_question` treated only as legacy input data.
- Normalized question events may include `handoff: None` in persisted child-run summaries.
- The compiler-enforced route contract rejects `handoff=` metadata on routes that target downstream `python_step` nodes instead of child-workflow handoffs.

## Preserved Invariants

- Workflow prompts, artifact filenames, publication boundaries, route tags, and output schemas were preserved.
- No legacy compatibility wrappers were added back onto exported workflow classes.
- Core engine/compiler compatibility rules were not changed in this phase.

## Intended Behavior Changes

- Exported workflow packages now conform to the enforced ctx-only public contract for hooks and python steps.
- Direct-call workflow regression tests now use compiled public surfaces and assert normalized control/runtime metadata.
- Overlay publication validation now accepts both legacy flat repo roots and the current packaged `autoloop/{core,runtime}` layout so workflow-builder publication tests validate the actual repository shape.

## Known Non-Changes

- The existing `schema`-field Pydantic warnings in `workflow_run_traces_to_optimization_candidates/contracts.py` remain unchanged.
- No non-exported workflow packages were migrated.

## Expected Side Effects

- Workflow-health snapshot expectations now surface `pending_input` and `finalization` fields in recent-run excerpts.
- Child-question propagation assertions now see explicit `handoff: None` on normalized last-event payloads.

## Validation Performed

- Targeted regression rerun:
  `./.venv/bin/pytest -q tests/runtime/test_security_finding_to_verified_remediation.py::test_security_remediation_package_propagates_child_question_without_adopting_artifacts tests/runtime/test_company_operation_to_recursive_improvement_cycle.py::test_company_operation_to_recursive_improvement_cycle_normalizes_repeatable_inputs tests/runtime/test_company_operation_to_recursive_improvement_cycle.py::test_company_operation_to_recursive_improvement_cycle_runs_and_publishes_terminal_cycle_artifacts tests/runtime/test_workflow_portfolio_to_operating_system.py::test_workflow_portfolio_to_operating_system_runs_and_publishes_terminal_governance_artifacts tests/runtime/test_workflow_portfolio_to_operating_system.py::test_workflow_portfolio_to_operating_system_publish_rejects_summary_drift tests/runtime/test_workflow_portfolio_to_operating_system.py::test_workflow_portfolio_to_operating_system_publish_rejects_invalid_lifecycle_posture tests/runtime/test_workflow_portfolio_to_operating_system.py::test_workflow_portfolio_to_operating_system_publish_rejects_hidden_downstream_execution_in_next_actions[...] tests/runtime/test_workflow_portfolio_to_operating_system.py::test_workflow_portfolio_to_operating_system_publish_rejects_hidden_downstream_execution_in_summary_next_action tests/runtime/test_workflow_portfolio_to_operating_system.py::test_workflow_portfolio_to_operating_system_publish_allows_explicit_negative_guardrails tests/runtime/test_workflow_run_history_to_failure_modes.py::test_workflow_run_history_to_failure_modes_package_runs_and_publishes_terminal_diagnostic_artifacts tests/runtime/test_workflow_run_history_to_failure_modes.py::test_workflow_run_history_to_failure_modes_publish_rejects_hidden_downstream_execution_boundary tests/runtime/test_workflow_run_history_to_failure_modes.py::test_workflow_run_history_to_failure_modes_publish_rejects_incomplete_authoritative_artifacts tests/runtime/test_workflow_run_history_to_failure_modes.py::test_workflow_run_history_to_failure_modes_publish_rejects_hidden_downstream_execution_text`
  result: `16 passed`
- Acceptance suite:
  `./.venv/bin/pytest -q tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_run_traces_to_optimization_candidates.py tests/runtime/test_workflow_builder_package.py tests/runtime/test_security_finding_to_verified_remediation.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_to_eval_suite.py tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_incident_to_hardening_program.py tests/runtime/test_investigation_request_to_evidence_pack.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_integration_parity.py::test_all_repo_workflow_packages_resolve_and_compile_under_canonical_simple_surface tests/unit/test_simple_surface.py`
  result: `421 passed, 602 warnings`

## Deduplication / Centralization

- Added `tests/runtime/workflow_contract_helpers.py` so runtime suites can invoke compiled public handlers consistently without reintroducing legacy package-local helper shims.
