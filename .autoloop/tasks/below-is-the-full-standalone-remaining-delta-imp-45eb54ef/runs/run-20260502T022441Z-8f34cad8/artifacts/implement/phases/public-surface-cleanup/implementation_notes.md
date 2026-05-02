# Implementation Notes

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: implement
- Phase ID: public-surface-cleanup
- Phase Directory Key: public-surface-cleanup
- Phase Title: Public Surface Cleanup
- Scope: phase-local producer artifact

## Files changed
- `tests/contract/test_engine_contracts.py`
- `autoloop/simple.py`
- `autoloop/core/__init__.py`
- `autoloop/core/descriptors.py`
- `autoloop/core/steps.py`
- `autoloop/core/discovery.py`
- `autoloop/core/hook_validation.py`
- `autoloop/core/compiler.py`
- `tests/unit/test_simple_surface.py`
- `tests/runtime/test_workspace_and_context.py`
- `workflows/autoloop_v1/workflow.py`
- `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/incident_to_hardening_program/workflow.py`
- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/release_candidate_to_go_no_go/workflow.py`
- `workflows/investigation_request_to_evidence_pack/workflow.py`
- `workflows/security_finding_to_verified_remediation/workflow.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
- `workflows/workflow_idea_to_workflow_package/workflow.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- `workflows/workflow_portfolio_to_operating_system/workflow.py`
- `workflows/workflow_run_history_to_failure_modes/workflow.py`
- `workflows/workflow_run_traces_to_optimization_candidates/workflow.py`
- `workflows/workflow_to_eval_suite/workflow.py`

## Symbols touched
- `autoloop.core.compiler._compile_outcome_handler`
- `autoloop.core.compiler._compile_system_handler`
- `autoloop.core.discovery.has_start_hook`
- `autoloop.core.hook_validation.validate_handlers`
- `autoloop.core.lowering.outcome_middleware_name`
- `autoloop.simple.Workflow`
- `autoloop.simple.ArtifactSpec`
- `autoloop.simple._NamedDeclaration`
- `autoloop.simple.StepDeclaration`
- `autoloop.simple.ProduceVerifyStepDeclaration`
- `autoloop.simple.PythonStepDeclaration`
- `autoloop.simple._WorkflowStepDeclaration`
- `autoloop.core.Workflow`
- `autoloop.core.descriptors.effective_state_model`
- `autoloop.core.descriptors.effective_parameters_model`
- `autoloop.core.steps.Step`
- `autoloop.core.steps.PromptStep`
- `autoloop.core.steps.ProduceVerifyStep`
- `autoloop.core.steps.PythonStep`
- `autoloop.core.steps.ChildWorkflowStep`
- `autoloop.core.discovery.WorkflowMeta`
- `autoloop.core.discovery.describe_workflow_class`
- `autoloop.core.discovery._is_simple_step_declaration`
- `autoloop.core.discovery._is_simple_artifact_spec`
- `autoloop.core.discovery._lower_simple_writes`
- `autoloop.core.discovery._lower_simple_verifier_writes`
- `autoloop.core.compiler.CompiledStep`
- explicit workflow `after_verifier` helpers across the migrated simple workflow packages and contract fixtures

## Checklist mapping
- Milestone 1 / public `on_route` removal: removed `on_route` from core step constructors, removed compiled `on_route_hook`, removed engine execution of step-level route hooks, removed static/topology references.
- Milestone 1 / vocabulary cleanup: simple declarations and lowering now use only `writes` / `verifier_writes`; legacy alias fields are no longer stored on declarations.
- Milestone 1 / dunder-marker cleanup: simple workflow/declaration/artifact detection now uses base-class / `isinstance(...)` checks instead of dunder markers.
- Milestone 1 / handler alias cleanup: removed auto-installation of `on_<step>` aliases for simple `python_step`.
- Milestone 1 / public class-handler cleanup: simple/public compilation now rejects class-level `on_start`, `on_outcome`, and `on_<step>` handlers; directly affected tests, runtime-generated fixtures, and the remaining exported public simple workflow packages were migrated to explicit `after` / `after_verifier` hooks or explicit session declarations.
- Remaining follow-up outside reviewer scope: repo-wide exported workflow compile sweeps still report separate route-handoff-to-`PythonStep` validation failures unrelated to the removed public handler surfaces.

## Assumptions
- Phase acceptance is centered on removing the deprecated public compiler surfaces and adding fail-fast coverage; unrelated route-handoff validation failures can remain for a later milestone if the removed public-simple surfaces are gone end to end.

## Preserved invariants
- Strict/internal workflows still compile through the existing transition-based path.
- Route-local `Route.to(..., on_taken=...)` remains supported.
- Public simple workflows still reject class-level `transitions` / `flow`.
- Step-local route metadata and required-write payloads remain unchanged apart from the removed `on_route` surface.
- Public simple `python_step` declarations still require an explicit handler on the declaration itself.

## Intended behavior changes
- `PromptStep`, `ProduceVerifyStep`, `PythonStep`, and `ChildWorkflowStep` no longer accept `on_route=...`.
- Compiled steps no longer expose `on_route_hook`.
- Route finalization no longer runs a separate step-level route hook before `on_taken`.
- Simple declaration objects no longer store `outputs` / `review_outputs`.
- Simple `python_step` no longer mutates the workflow class by installing `on_<step>` aliases.
- Public simple workflows now reject class-level `on_start`, `on_outcome`, and `on_<step>` handlers instead of compiling them implicitly.

## Known non-changes
- `AfterStepResult`, multi-arity hook support, and broader hook normalization remain for later milestones.
- Route effects remain supported in this phase.
- Strict/internal `autoloop.core.Workflow` class-method handlers remain unchanged in this pass.
- Repo compile sweeps still hit pre-existing route-handoff-to-`PythonStep` validation failures in multiple workflow packages.

## Expected side effects
- Legacy tests or call sites that construct core steps with `on_route=...` now fail immediately with `TypeError`.
- Topology/hash/static-graph consumers no longer see any compiled step-level route-hook field.
- Exported public simple workflows in the repo now route post-verifier state updates through explicit declaration hooks instead of removed class-level handlers.

## Validation performed
- `python3 -m compileall autoloop/simple.py autoloop/core/__init__.py autoloop/core/descriptors.py autoloop/core/steps.py autoloop/core/discovery.py autoloop/core/hook_validation.py autoloop/core/compiler.py autoloop/core/engine.py autoloop/runtime/static_graph.py`
- `./.venv/bin/python -m pytest tests/unit/test_simple_surface.py tests/runtime/test_runtime_static_graph.py -q`
- `./.venv/bin/python` signature spot-check for `Step`, `PromptStep`, `ProduceVerifyStep`, `PythonStep`, and `ChildWorkflowStep` constructor surfaces.
- `./.venv/bin/python -m pytest tests/unit/test_simple_surface.py -q`
- `./.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -q -k 'on_route or route_handoff_targeting_workflow_step or produce_verify_step_sends_split_phase_contracts_without_implicitly_requiring_producer_writes or verifier_session_override_uses_distinct_verifier_session_slot or verifier_requires_fail_before_verifier_when_declared or validates_selected_route_required_writes_per_route'`
- `./.venv/bin/python -m pytest tests/runtime/test_workspace_and_context.py -q`
- `./.venv/bin/python -m pytest tests/runtime/test_runtime_static_graph.py -q`
- `python3 -m compileall workflows/company_operation_to_recursive_improvement_cycle/workflow.py workflows/incident_to_hardening_program/workflow.py workflows/workflow_and_eval_to_refined_workflow_package/workflow.py workflows/workflow_idea_to_workflow_package/workflow.py workflows/workflow_package_to_composable_building_blocks/workflow.py workflows/workflow_portfolio_to_operating_system/workflow.py workflows/workflow_run_history_to_failure_modes/workflow.py workflows/workflow_run_traces_to_optimization_candidates/workflow.py workflows/workflow_to_eval_suite/workflow.py`
- `./.venv/bin/python -m pytest tests/unit/test_simple_surface.py tests/contract/test_engine_contracts.py tests/runtime/test_workspace_and_context.py tests/runtime/test_runtime_static_graph.py -q`
- `./.venv/bin/python - <<'PY' ... compile_workflow sweep over exported workflow packages ... PY`
  Result: removed public simple handler failures are gone; the remaining failures are route-handoff-to-`PythonStep` validation errors outside this phase.

## Deduplication / centralization
- Consolidated simple-authoring detection onto base-class inspection in both discovery and descriptor model selection.
- Kept route-hook cleanup centralized in the compiled metadata and route-finalization path rather than adding compatibility branches.
- Centralized public class-handler removal in discovery/lowering/compiler validation gates so simple workflows can only opt into explicit declaration hooks.
