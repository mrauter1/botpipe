# Implementation Notes

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: implement
- Phase ID: workflow-migration-and-cleanup
- Phase Directory Key: workflow-migration-and-cleanup
- Phase Title: Workflow migration and cleanup
- Scope: phase-local producer artifact

## Files Changed

- `autoloop/simple.py`
- `core/validation.py`
- `core/workflow_capabilities.py`
- `runtime/runner.py`
- `workflows/autoloop_v1/workflow.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/contracts.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/company_operation_to_recursive_improvement_cycle/contracts.py`
- `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
- `workflows/incident_to_hardening_program/contracts.py`
- `workflows/incident_to_hardening_program/workflow.py`
- `workflows/investigation_request_to_evidence_pack/contracts.py`
- `workflows/investigation_request_to_evidence_pack/workflow.py`
- `workflows/security_finding_to_verified_remediation/contracts.py`
- `workflows/security_finding_to_verified_remediation/workflow.py`
- `workflows/release_candidate_to_go_no_go/contracts.py`
- `workflows/release_candidate_to_go_no_go/workflow.py`
- `workflows/task_to_candidate_workflow_set/contracts.py`
- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/task_to_workflow_strategy/contracts.py`
- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/workflow_idea_to_workflow_package/contracts.py`
- `workflows/workflow_idea_to_workflow_package/workflow.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/contracts.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
- `workflows/workflow_package_to_composable_building_blocks/contracts.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `workflows/workflow_portfolio_to_operating_system/contracts.py`
- `workflows/workflow_portfolio_to_operating_system/workflow.py`
- `workflows/workflow_run_history_to_failure_modes/contracts.py`
- `workflows/workflow_run_history_to_failure_modes/workflow.py`
- `workflows/workflow_run_traces_to_optimization_candidates/contracts.py`
- `workflows/workflow_run_traces_to_optimization_candidates/workflow.py`
- `workflows/workflow_to_eval_suite/contracts.py`
- `workflows/workflow_to_eval_suite/workflow.py`
- `docs/architecture.md`
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
- `cleanup.md`
- `.autoloop/tasks/full-revised-autoloop-v3-redesign-implementation-16af2351/decisions.txt`

## Symbols Touched

- Canonical workflow declarations: `bootstrap`, `capture_*`, `publish_*`, `route_*`, `plan`, `implement`, `test`, `frame_*`, `design_*`, `build_*`, `evaluate_*`, `map_failure_modes`, `package_improvement_pressure`
- Route metadata bundles: selected-workflow adaptation, investigation evidence, incident hardening, release go/no-go, workflow packaging, eval suite, failure modes, portfolio operating system, company-recursive-improvement, security-remediation, task-strategy, refinement, decomposition, and optimization contract maps
- Simple-surface lowering and compatibility shims: `_install_simple_system_handler_aliases`, `_order_steps_from_entry`, `seen_simple_declarations`, `_legacy_capability_target`, `_ensure_default_session_binding`
- Canonical public guidance text in `docs/authoring.md`, `docs/architecture.md`, `cleanup.md`, and workflow package docs

## Checklist Mapping

- AC-1 complete: bundled workflows and remaining compatibility-era docs/examples now use the canonical step-local route authoring model, while public guidance stays on `autoloop.simple` / `autoloop`
- AC-2 complete: prior `autoloop_optimizer` split remains in place and no optimizer-specific logic was moved back into framework core during cleanup
- AC-3 complete: strictness, docs, contract, and runtime integration suites pass after removing first-party `RouteInfo` / `route_infos` workflow dependencies and restoring the required compatibility shims centrally

## Assumptions

- Existing workflow-local `on_<step>` outcome handlers remain valid compatibility seams while the declaration surface moves to `do_review_step(...)`
- Publication validators and deterministic artifact checks stay workflow-local during this phase rather than moving into shared helpers

## Preserved Invariants

- Workflow-local publication semantics, artifact paths, session names, and verifier payload schemas remain unchanged
- Runtime control middleware `on_outcome = event_on_outcome_tags(...)` remains active on the migrated workflow packages
- Child-workflow adoption logic in `task_to_workflow_strategy` and `security_finding_to_verified_remediation` was preserved while only the declaration surface changed
- Runtime outward compatibility remains intact for legacy inspection and package execution seams that still expect `SUCCESS` terminals and callable `on_<step>` helpers

## Intended Behavior Changes

- The remaining bundled workflow packages now declare topology on the step objects instead of relying on global `transitions`
- Converted workflow packages now use canonical `Prompt.file(...)`, `python_step(...)`, `do_review_step(...)`, and `FINISH`
- The remaining first-party workflow-local contract modules now carry canonical `Route.to(...)` route metadata instead of public `RouteInfo`
- Workflow docs now teach step-local `Route.to(...)` metadata as the normal authoring path and keep compatibility vocabulary only where runtime payload surfaces still expose it
- Simple-declaration compatibility is now enforced centrally: `python_step(...)` installs `on_<step>` aliases, compiled step ordering starts from the resolved entry graph, and workflow capability inspection still reports `SUCCESS` for legacy terminal consumers

## Known Non-Changes

- I did not touch the unrelated deleted dirty file `docs/workflows/workflow_run_traces_to_optimization_candidates.md`

## Expected Side Effects

- All bundled workflow packages now rely on explicit `entry = bootstrap` where the decorated bootstrap handler appears later in the class body than the review-step declarations
- Provider/runtime inspection for the migrated packages should now derive their topology from step-local declarations rather than from package-local transition tables
- The optimization workflow now expresses its optional-pass routing hops as explicit `python_step(...)` nodes with canonical `Route.to(...)` metadata rather than legacy `SystemStep` route-info shims
- Compatibility runtime surfaces still persist a default session file and still expose `SUCCESS` transition targets where existing tooling/tests expect the legacy outward vocabulary

## Validation Performed

- `python3 -m py_compile workflows/autoloop_v1/workflow.py workflows/candidate_workflow_to_adapted_execution_plan/workflow.py workflows/candidate_workflow_to_adapted_execution_plan/contracts.py workflows/release_candidate_to_go_no_go/workflow.py workflows/workflow_idea_to_workflow_package/workflow.py workflows/workflow_to_eval_suite/workflow.py workflows/workflow_run_history_to_failure_modes/workflow.py`
- `python3 -m py_compile workflows/company_operation_to_recursive_improvement_cycle/contracts.py workflows/company_operation_to_recursive_improvement_cycle/workflow.py workflows/security_finding_to_verified_remediation/contracts.py workflows/security_finding_to_verified_remediation/workflow.py workflows/task_to_workflow_strategy/contracts.py workflows/task_to_workflow_strategy/workflow.py`
- `python3 -m py_compile workflows/workflow_and_eval_to_refined_workflow_package/contracts.py workflows/workflow_and_eval_to_refined_workflow_package/workflow.py workflows/workflow_package_to_composable_building_blocks/contracts.py workflows/workflow_package_to_composable_building_blocks/workflow.py workflows/workflow_run_traces_to_optimization_candidates/contracts.py workflows/workflow_run_traces_to_optimization_candidates/workflow.py`
- `python3 -m py_compile workflows/investigation_request_to_evidence_pack/contracts.py workflows/investigation_request_to_evidence_pack/workflow.py workflows/task_to_candidate_workflow_set/contracts.py workflows/task_to_candidate_workflow_set/workflow.py workflows/incident_to_hardening_program/contracts.py workflows/incident_to_hardening_program/workflow.py workflows/release_candidate_to_go_no_go/contracts.py workflows/workflow_idea_to_workflow_package/contracts.py`
- `python3 -m py_compile workflows/workflow_to_eval_suite/contracts.py workflows/workflow_run_history_to_failure_modes/contracts.py workflows/workflow_portfolio_to_operating_system/contracts.py workflows/workflow_portfolio_to_operating_system/workflow.py autoloop/simple.py core/validation.py core/workflow_capabilities.py runtime/runner.py`
- `rg -n "PairStep|SystemStep|SUCCESS\\b|transitions\\s*=|route_infos=|RouteInfo|global_routes|merge_transitions|pause_on_outcome_tags" workflows/company_operation_to_recursive_improvement_cycle workflows/security_finding_to_verified_remediation workflows/task_to_workflow_strategy`
- `rg -n "PairStep|SystemStep|SUCCESS\\b|transitions\\s*=|route_infos=|RouteInfo|global_routes|merge_transitions|pause_on_outcome_tags" workflows/workflow_and_eval_to_refined_workflow_package workflows/workflow_package_to_composable_building_blocks workflows/workflow_run_traces_to_optimization_candidates`
- `rg -n "route_infos=|from core import RouteInfo|RouteInfo\\(" workflows -g 'workflow.py' -g 'contracts.py'`
- `./.venv/bin/pytest tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_to_eval_suite.py`
- `./.venv/bin/pytest tests/strictness/test_no_compat.py::test_active_tree_does_not_reintroduce_removed_compatibility_surfaces tests/test_architecture_baseline_docs.py::test_authoring_doc_describes_greenfield_simple_surface tests/runtime/test_compatibility_runtime.py::test_execute_workflow_package_persists_default_session_for_system_only_workflow tests/runtime/test_workflow_reference_resolution.py::test_simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection`
- `./.venv/bin/pytest tests/strictness/test_no_compat.py tests/test_architecture_baseline_docs.py tests/contract/test_engine_contracts.py tests/runtime`

## Deduplication / Centralization

- Reused the same migration pattern across bundled workflows: preserve workflow-local handlers, lower agentic nodes to `do_review_step(...)`, lower deterministic nodes to decorated `python_step(...)`, and convert route metadata bundle-by-bundle to `Route.to(...)` once the declaration topology is stable
- Centralized the migration fallout fixes in framework code instead of patching workflows one-by-one: simple declarations now restore callable `on_<step>` aliases, compiled step discovery deduplicates reused declarations and orders execution from the resolved entry graph, workflow capability inspection preserves legacy terminal naming, and package runs persist a default session binding even when no step opened one explicitly
