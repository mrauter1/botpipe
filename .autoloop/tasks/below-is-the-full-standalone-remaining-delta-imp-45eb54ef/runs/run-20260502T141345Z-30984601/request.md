Follow-up implementation request:

Migrate the exported workflow packages under `workflows/*/workflow.py` to the final public runtime contract that the core engine now enforces.

Required scope:

1. Convert exported workflow lifecycle hooks to `hook(ctx)` only.
   - Remove multi-argument forms such as `(ctx, outcome)`.
   - Move any needed data access to `ctx.outcome`, `ctx.route`, `ctx.artifacts`, `ctx.meta`, and other `ctx` fields.

2. Remove hook state-replacement returns from exported workflow packages.
   - Hooks must mutate `ctx.state` directly.
   - Do not return `ctx.state`, `state.model_copy(...)`, or any replacement `BaseModel`.
   - Final hook returns must stay within the supported set: `None`, route-tag string, `Event(...)`, `RequestInput(...)`, `Goto(...)`, `Fail(...)`.

3. Convert exported `python_step` handlers to the final `python_step(ctx)` contract.
   - Remove `(state, ctx)` handlers.
   - Use `ctx.state` for reads and writes.
   - Keep route/control returns within the supported final set.

4. Update workflow-specific tests that directly call or assume the removed helper forms.
   - In particular, migrate tests that call legacy package-local methods such as `on_capture_frame_context(state, ctx)` or `on_route_*` helpers directly.

5. Add regression coverage for repo-level package compatibility with the final public contract.
   - A discovered-workflow compile sweep must succeed for the exported workflow packages instead of tolerating known compile failures.

Acceptance criteria:

- `compile_workflow(...)` succeeds for the exported workflow packages discovered from the repo.
- No exported workflow package still defines lifecycle hooks in multi-argument forms such as `(ctx, outcome)`.
- No exported workflow package still uses hook state-replacement returns such as `ctx.state.model_copy(...)` or `state.model_copy(...)`.
- No exported workflow package still defines `python_step(state, ctx)` handlers.
- Updated tests pass and protect the migrated package surfaces against regressions.

Packages confirmed as currently failing on the removed contract:

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
