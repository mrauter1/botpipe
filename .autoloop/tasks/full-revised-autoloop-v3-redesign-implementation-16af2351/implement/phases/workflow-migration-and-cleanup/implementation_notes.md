# Implementation Notes

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: implement
- Phase ID: workflow-migration-and-cleanup
- Phase Directory Key: workflow-migration-and-cleanup
- Phase Title: Workflow migration and cleanup
- Scope: phase-local producer artifact

## Files Changed

- `workflows/autoloop_v1/workflow.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/contracts.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/company_operation_to_recursive_improvement_cycle/contracts.py`
- `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
- `workflows/security_finding_to_verified_remediation/contracts.py`
- `workflows/security_finding_to_verified_remediation/workflow.py`
- `workflows/release_candidate_to_go_no_go/workflow.py`
- `workflows/task_to_workflow_strategy/contracts.py`
- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/workflow_idea_to_workflow_package/workflow.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/contracts.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
- `workflows/workflow_package_to_composable_building_blocks/contracts.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `workflows/workflow_run_history_to_failure_modes/workflow.py`
- `workflows/workflow_run_traces_to_optimization_candidates/contracts.py`
- `workflows/workflow_run_traces_to_optimization_candidates/workflow.py`
- `workflows/workflow_to_eval_suite/workflow.py`
- `docs/authoring.md`
- `docs/workflows/candidate_workflow_to_adapted_execution_plan.md`
- `docs/workflows/company_operation_to_recursive_improvement_cycle.md`
- `docs/workflows/incident_to_hardening_program.md`
- `docs/workflows/investigation_request_to_evidence_pack.md`
- `docs/workflows/release_candidate_to_go_no_go.md`
- `docs/workflows/security_finding_to_verified_remediation.md`
- `docs/workflows/task_to_candidate_workflow_set.md`
- `docs/workflows/task_to_workflow_strategy.md`
- `docs/workflows/workflow_and_eval_to_refined_workflow_package.md`
- `docs/workflows/workflow_idea_to_workflow_package.md`
- `docs/workflows/workflow_package_to_composable_building_blocks.md`
- `docs/workflows/workflow_portfolio_to_operating_system.md`
- `docs/workflows/workflow_run_history_to_failure_modes.md`
- `docs/workflows/workflow_to_eval_suite.md`
- `.autoloop/tasks/full-revised-autoloop-v3-redesign-implementation-16af2351/decisions.txt`

## Symbols Touched

- Canonical workflow declarations: `bootstrap`, `capture_*`, `publish_*`, `route_*`, `plan`, `implement`, `test`, `frame_*`, `design_*`, `build_*`, `evaluate_*`, `map_failure_modes`, `package_improvement_pressure`
- Route metadata bundles: company-recursive-improvement, security-remediation, task-strategy, refinement, decomposition, and optimization contract maps
- Canonical public guidance text in `docs/authoring.md` and workflow package docs

## Checklist Mapping

- AC-1 mostly complete: all bundled workflow packages now declare topology on `python_step(...)` / `do_review_step(...)` instead of `PairStep` / `SystemStep` plus global `transitions`, and the workflow docs now describe canonical route metadata instead of `route_infos`
- AC-2 partial: prior `autoloop_optimizer` split remains in place; no new stdlib moves in this turn
- AC-3 deferred: several previously migrated workflow packages still import `RouteInfo` in their contract modules and still pass `route_infos=...`, and the strictness/docs/runtime suites were not run in this environment

## Assumptions

- Existing workflow-local `on_<step>` outcome handlers remain valid compatibility seams while the declaration surface moves to `do_review_step(...)`
- Publication validators and deterministic artifact checks stay workflow-local during this phase rather than moving into shared helpers

## Preserved Invariants

- Workflow-local publication semantics, artifact paths, session names, and verifier payload schemas remain unchanged
- Runtime control middleware `on_outcome = event_on_outcome_tags(...)` remains active on the migrated workflow packages
- Child-workflow adoption logic in `task_to_workflow_strategy` and `security_finding_to_verified_remediation` was preserved while only the declaration surface changed

## Intended Behavior Changes

- The remaining bundled workflow packages now declare topology on the step objects instead of relying on global `transitions`
- Converted workflow packages now use canonical `Prompt.file(...)`, `python_step(...)`, `do_review_step(...)`, and `FINISH`
- Six additional workflow-local contract modules now carry canonical `Route.to(...)` route metadata instead of public `RouteInfo`
- Workflow docs now teach step-local `Route.to(...)` metadata as the normal authoring path and demote legacy `route_infos` wording

## Known Non-Changes

- Earlier-migrated workflow packages such as `investigation_request_to_evidence_pack`, `task_to_candidate_workflow_set`, `incident_to_hardening_program`, `release_candidate_to_go_no_go`, `workflow_idea_to_workflow_package`, `workflow_to_eval_suite`, `workflow_run_history_to_failure_modes`, and `workflow_portfolio_to_operating_system` still need the second-pass `RouteInfo` / `route_infos` cleanup
- Strictness, docs, contract, runtime, and workflow integration suites were not executed in this checkpoint because the local environment lacks the full runtime dependency set
- I did not touch the unrelated deleted dirty file `docs/workflows/workflow_run_traces_to_optimization_candidates.md`

## Expected Side Effects

- All bundled workflow packages now rely on explicit `entry = bootstrap` where the decorated bootstrap handler appears later in the class body than the review-step declarations
- Provider/runtime inspection for the migrated packages should now derive their topology from step-local declarations rather than from package-local transition tables
- The optimization workflow now expresses its optional-pass routing hops as explicit `python_step(...)` nodes with canonical `Route.to(...)` metadata rather than legacy `SystemStep` route-info shims

## Validation Performed

- `python3 -m py_compile workflows/autoloop_v1/workflow.py workflows/candidate_workflow_to_adapted_execution_plan/workflow.py workflows/candidate_workflow_to_adapted_execution_plan/contracts.py workflows/release_candidate_to_go_no_go/workflow.py workflows/workflow_idea_to_workflow_package/workflow.py workflows/workflow_to_eval_suite/workflow.py workflows/workflow_run_history_to_failure_modes/workflow.py`
- `python3 -m py_compile workflows/company_operation_to_recursive_improvement_cycle/contracts.py workflows/company_operation_to_recursive_improvement_cycle/workflow.py workflows/security_finding_to_verified_remediation/contracts.py workflows/security_finding_to_verified_remediation/workflow.py workflows/task_to_workflow_strategy/contracts.py workflows/task_to_workflow_strategy/workflow.py`
- `python3 -m py_compile workflows/workflow_and_eval_to_refined_workflow_package/contracts.py workflows/workflow_and_eval_to_refined_workflow_package/workflow.py workflows/workflow_package_to_composable_building_blocks/contracts.py workflows/workflow_package_to_composable_building_blocks/workflow.py workflows/workflow_run_traces_to_optimization_candidates/contracts.py workflows/workflow_run_traces_to_optimization_candidates/workflow.py`
- `rg -n "PairStep|SystemStep|SUCCESS\\b|transitions\\s*=|route_infos=|RouteInfo|global_routes|merge_transitions|pause_on_outcome_tags" workflows/company_operation_to_recursive_improvement_cycle workflows/security_finding_to_verified_remediation workflows/task_to_workflow_strategy`
- `rg -n "PairStep|SystemStep|SUCCESS\\b|transitions\\s*=|route_infos=|RouteInfo|global_routes|merge_transitions|pause_on_outcome_tags" workflows/workflow_and_eval_to_refined_workflow_package workflows/workflow_package_to_composable_building_blocks workflows/workflow_run_traces_to_optimization_candidates`
- `rg -n "route_infos|RouteInfo|PairStep|SystemStep|SUCCESS\\b|transitions =" docs/authoring.md docs/workflows docs/architecture.md`

## Deduplication / Centralization

- Reused the same migration pattern across bundled workflows: preserve workflow-local handlers, lower agentic nodes to `do_review_step(...)`, lower deterministic nodes to decorated `python_step(...)`, and convert route metadata bundle-by-bundle to `Route.to(...)` once the declaration topology is stable
