# Implementation Notes

- Task ID: `framework-authoring-flexibility-change-spec-goal-2ee572cd`
- Pair: `implement`
- Phase ID: `inspection-docs-and-regression`
- Scope: phase-local producer artifact

## Files changed

- `autoloop/core/workflow_capabilities.py`
- `autoloop/runtime/static_graph.py`
- `autoloop/runtime/cli.py`
- `autoloop/core/artifacts.py`
- `autoloop/core/inventory.py`
- `docs/authoring.md`
- `docs/architecture.md`
- `tests/runtime/test_runtime_static_graph.py`
- `tests/runtime/test_package_cli.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `workflows/autoloop_v1/workflow.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
- `workflows/incident_to_hardening_program/workflow.py`
- `workflows/investigation_request_to_evidence_pack/workflow.py`
- `workflows/release_candidate_to_go_no_go/workflow.py`
- `workflows/security_finding_to_verified_remediation/workflow.py`
- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
- `workflows/workflow_idea_to_workflow_package/workflow.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `workflows/workflow_portfolio_to_operating_system/workflow.py`
- `workflows/workflow_run_history_to_failure_modes/workflow.py`
- `workflows/workflow_run_traces_to_optimization_candidates/workflow.py`
- `workflows/workflow_to_eval_suite/workflow.py`

## Symbols touched

- `WorkflowStepCapability`
- `WorkflowRouteCapability`
- `workflow_capability_payload`
- `_compiled_step_payload`
- `static_graph_payload`
- `_route_table_text`
- `_topology_mermaid`
- `_compile_report_text`
- `workflows_show`
- `Artifact`
- `Artifact.managed`
- `ArtifactRole`

## Checklist mapping

- Plan Phase 5 / inspection payload updates: completed via workflow capability, static graph, and CLI payload changes.
- Plan Phase 5 / docs refresh: completed in `docs/authoring.md` and `docs/architecture.md`.
- Plan Phase 5 / regression sweep: completed across runtime, contract, docs, and unit suites.
- Out-of-phase but required for regression acceptance: added and used explicit managed-artifact role so existing catalog workflows remain valid under the already-landed ownership diagnostic.

## Intended behavior changes

- Inspection/static graph/CLI payloads now expose authored routes, runtime control routes, and provider-visible routes for both interactive and full-auto policies.
- Route-table, Mermaid, and compile-report static artifacts now render authored-vs-runtime-control route class plus interactive/full-auto provider visibility instead of the old flat provider-visible view.
- Route payloads now report runtime-control and policy-specific provider visibility metadata.
- Documentation now states the shipped static-vs-runtime validation split, lazy worklist semantics, typed effects surface, validation helper contract, and artifact ownership rules.
- Existing dual-role catalog workflows now opt into an explicit managed-artifact role instead of relying on ambiguous workflow-level plus produced declarations.

## Preserved invariants

- `CompiledStep.available_routes` remains the full execution-legal route set.
- No legacy default `blocked` or `failed` routes were reintroduced.
- Runtime-owned failure handling, checkpoint behavior, and lazy worklist semantics from earlier phases remain unchanged.
- Same-identity accidental workflow-level plus produced artifacts still fail unless explicitly marked managed.

## Assumptions

- Existing catalog workflows using the same artifact as workflow-owned state and as a step write are intentional shared/managed cases, not accidental ownership mistakes.
- Downstream tooling can tolerate additive inspection payload fields while retaining prior top-level payload structure.

## Known non-changes

- No new workflow packages were added.
- No new runtime UX behavior beyond the requested inspection/documentation/reporting updates was introduced.
- Criteria artifact was left untouched.

## Expected side effects

- Snapshot consumers now see richer route metadata and may need to ignore/additive-handle the new keys.
- Text inspection artifacts (`route_table.md`, `topology.mmd`, `compile_report.md`) now have richer route annotations and updated column/summary text.
- Catalog workflows marked `role="managed"` now compile cleanly under the stricter ownership diagnostic.

## Validation performed

- `.venv/bin/python -m pytest -q tests/runtime/test_runtime_static_graph.py tests/runtime/test_package_cli.py tests/test_architecture_baseline_docs.py tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py tests/contract/test_canonical_runtime_contracts.py`
- Result: `229 passed`
- Additional compile scan of repository workflow packages after managed-artifact annotations: zero workflow load/contract failures.

## Deduplication / centralization decisions

- Route-view reporting stays centralized in compiled/workflow-capability payload builders so static graph and CLI surfaces consume one route metadata model.
- Reviewer follow-up extended that same compiled route metadata model to the route table, Mermaid topology, and compile report text renderers so the JSON and text inspection surfaces cannot diverge on route class or policy visibility.
- Managed-artifact compatibility uses the explicit artifact-role seam instead of weakening inventory diagnostics or adding package-specific exceptions.
