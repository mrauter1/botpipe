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
- `workflows/release_candidate_to_go_no_go/workflow.py`
- `workflows/workflow_idea_to_workflow_package/workflow.py`
- `workflows/workflow_run_history_to_failure_modes/workflow.py`
- `workflows/workflow_to_eval_suite/workflow.py`
- `.autoloop/tasks/full-revised-autoloop-v3-redesign-implementation-16af2351/decisions.txt`

## Symbols Touched

- Canonical workflow declarations: `bootstrap`, `capture_*`, `publish_*`, `plan`, `implement`, `test`, `frame_*`, `design_*`, `build_*`, `evaluate_*`, `map_failure_modes`, `package_improvement_pressure`
- Route metadata bundle: `FRAME_ADAPTATION_REQUEST_ROUTE_CONTRACTS`, `ANALYZE_ADAPTATION_SURFACE_ROUTE_CONTRACTS`, `PACKAGE_ADAPTED_EXECUTION_PLAN_ROUTE_CONTRACTS`

## Checklist Mapping

- AC-1 partial: converted additional bundled workflows from `PairStep` / `SystemStep` plus global `transitions` to `do_review_step(...)` / `python_step(...)`, including `autoloop_v1`, `candidate_workflow_to_adapted_execution_plan`, `release_candidate_to_go_no_go`, `workflow_idea_to_workflow_package`, `workflow_run_history_to_failure_modes`, and `workflow_to_eval_suite`
- AC-2 partial: prior `autoloop_optimizer` split remains in place; no new stdlib moves in this turn
- AC-3 deferred: remaining bundled workflows, route-metadata cleanup, doc cleanup, and suite migration are not finished in this turn

## Assumptions

- Existing workflow-local `on_<step>` outcome handlers remain valid compatibility seams while the declaration surface moves to `do_review_step(...)`
- Publication validators and deterministic artifact checks stay workflow-local during this phase rather than moving into shared helpers

## Preserved Invariants

- Workflow-local publication semantics, artifact paths, session names, and verifier payload schemas remain unchanged
- Runtime control middleware `on_outcome = event_on_outcome_tags(...)` remains active on the migrated workflow packages
- Child-workflow adoption logic in `task_to_workflow_strategy` was intentionally not touched in this checkpoint

## Intended Behavior Changes

- The migrated workflow packages now declare topology on the step objects instead of relying on global `transitions`
- Converted workflow packages now use canonical `Prompt.file(...)`, `python_step(...)`, `do_review_step(...)`, and `FINISH`
- `candidate_workflow_to_adapted_execution_plan/contracts.py` now carries canonical `Route.to(...)` route metadata instead of public `RouteInfo`

## Known Non-Changes

- Several bundled workflows still need the same declaration migration pass, especially `company_operation_to_recursive_improvement_cycle`, `security_finding_to_verified_remediation`, `task_to_workflow_strategy`, `workflow_and_eval_to_refined_workflow_package`, `workflow_package_to_composable_building_blocks`, and `workflow_run_traces_to_optimization_candidates`
- Most workflow-local contract bundles still use `RouteInfo` / `route_infos`
- Remaining compatibility-era docs/examples were not cleaned up in this checkpoint
- I did not touch the unrelated deleted dirty file `docs/workflows/workflow_run_traces_to_optimization_candidates.md`

## Expected Side Effects

- Converted workflow packages now rely on explicit `entry = bootstrap` where the decorated bootstrap handler appears later in the class body than the review-step declarations
- Provider/runtime inspection for the migrated packages should now derive their topology from step-local declarations rather than from a package-local transition table

## Validation Performed

- `python3 -m py_compile workflows/autoloop_v1/workflow.py workflows/candidate_workflow_to_adapted_execution_plan/workflow.py workflows/candidate_workflow_to_adapted_execution_plan/contracts.py workflows/release_candidate_to_go_no_go/workflow.py workflows/workflow_idea_to_workflow_package/workflow.py workflows/workflow_to_eval_suite/workflow.py workflows/workflow_run_history_to_failure_modes/workflow.py`

## Deduplication / Centralization

- Reused the same migration pattern across straight-line bundled workflows: preserve workflow-local handlers, lower agentic nodes to `do_review_step(...)`, lower deterministic nodes to decorated `python_step(...)`, and keep route policy local until the later `Route.to(...)` cleanup pass
