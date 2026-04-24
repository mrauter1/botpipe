# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c6
- Pair: implement
- Phase ID: candidate-workflow-adapted-execution-plan-package
- Phase Directory Key: candidate-workflow-adapted-execution-plan-package
- Phase Title: Adapted Execution Plan Package
- Scope: phase-local producer artifact

## Files changed

- `workflows/candidate_workflow_to_adapted_execution_plan/__init__.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/params.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/contracts.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.toml`
- `workflows/candidate_workflow_to_adapted_execution_plan/prompts/README.md`
- `workflows/candidate_workflow_to_adapted_execution_plan/prompts/frame_producer.md`
- `workflows/candidate_workflow_to_adapted_execution_plan/prompts/frame_verifier.md`
- `workflows/candidate_workflow_to_adapted_execution_plan/prompts/analyze_producer.md`
- `workflows/candidate_workflow_to_adapted_execution_plan/prompts/analyze_verifier.md`
- `workflows/candidate_workflow_to_adapted_execution_plan/prompts/package_producer.md`
- `workflows/candidate_workflow_to_adapted_execution_plan/prompts/package_verifier.md`
- `workflows/candidate_workflow_to_adapted_execution_plan/assets/adapted_execution_plan_checklist.md`
- `docs/workflows/candidate_workflow_to_adapted_execution_plan.md`
- `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- `workflows/task_to_workflow_strategy/prompts/select_producer.md`
- `workflows/task_to_workflow_strategy/prompts/package_producer.md`
- `workflows/task_to_workflow_strategy/prompts/package_verifier.md`
- `workflows/task_to_workflow_strategy/assets/strategy_package_checklist.md`
- `docs/workflows/task_to_workflow_strategy.md`
- `tests/runtime/test_task_to_workflow_strategy.py`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `tests/test_architecture_baseline_docs.py`

## Symbols touched

- `CandidateWorkflowToAdaptedExecutionPlan`
- `AdaptationRequestFramingPayload`
- `AdaptationSurfaceAnalysisPayload`
- `AdaptedExecutionPlanPayload`
- `FRAME_ADAPTATION_REQUEST_ROUTE_CONTRACTS`
- `ANALYZE_ADAPTATION_SURFACE_ROUTE_CONTRACTS`
- `PACKAGE_ADAPTED_EXECUTION_PLAN_ROUTE_CONTRACTS`
- `test_candidate_workflow_to_adapted_execution_plan_package_runs_and_publishes_terminal_adaptation_artifacts`
- `test_task_to_workflow_strategy_adapt_handoff_docs_and_prompts_reference_adaptation_building_block`

## Checklist mapping

- Phase 2 / add the new workflow package under `workflows/candidate_workflow_to_adapted_execution_plan/`: complete
- Phase 2 / implement params, contracts, prompts, asset checklist, workflow logic, publication validation, docs, and runtime tests: complete
- Phase 2 / reject invalid selected workflows, invalid proposed parameter payloads, missing authoritative artifacts, and summary drift at publication: complete
- Phase 3 / keep the existing `strategy_summary.json` and `StrategyPackagePayload` field set unchanged: preserved
- Phase 3 / make the front-door `adapt` handoff more concrete only through existing prompt/package/next-action surfaces: complete
- Phase 3 / update recursive memory and baseline-doc proof for cycle 6: complete

## Assumptions

- The repo-root `docs/`, `core/`, `runtime/`, `stdlib/`, and `workflows/` layout remains the authoritative replacement for the stale `src/autoloop/...` references in the original request.
- A provider-authored proposed parameter mapping should stay non-authoritative until publication revalidates it through the shared loader path.

## Preserved invariants

- Runtime-owned control surfaces remain limited to `expected_output_schema`, `available_routes`, and `route_contracts`.
- `workflow.toml` remains metadata-only.
- `task_to_workflow_strategy` still stops at strategy publication and does not auto-run the selected route.
- `strategy_summary.json` and `StrategyPackagePayload` field sets remain unchanged in cycle 6.

## Intended behavior changes

- Added `candidate_workflow_to_adapted_execution_plan` as a reusable building block that publishes:
- `selected_workflow_capability.json`
- `adapted_execution_plan.md`
- `adapted_execution_summary.json`
- `adapted_execution_next_action.md`
- `validated_workflow_parameters.json`
- `adapted_execution_plan_receipt.json`
- Front-door `adapt` handoff guidance now points explicitly to `candidate_workflow_to_adapted_execution_plan` through existing prompt/checklist/doc surfaces.

## Known non-changes

- No selected workflow is auto-run by the new building block.
- No selected workflow package is mutated at runtime.
- No new front-door summary fields or publish-time strategy-summary validators were introduced.

## Expected side effects

- Adaptation-oriented workflows can now reuse a selected-workflow contract snapshot plus shared workflow-parameter validation without importing runtime internals directly.
- Operators following a front-door `adapt` strategy now receive a named downstream building block instead of a generic prose-only adaptation handoff.
- Recursive memory now treats `workflow_to_eval_suite` as the clearest next deferred portfolio gap after adaptation planning shipped.

## Validation performed

- `.venv/bin/python -m py_compile workflows/candidate_workflow_to_adapted_execution_plan/workflow.py workflows/candidate_workflow_to_adapted_execution_plan/contracts.py workflows/candidate_workflow_to_adapted_execution_plan/params.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_task_to_workflow_strategy.py`
- `.venv/bin/pytest -q tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_task_to_workflow_strategy.py tests/test_architecture_baseline_docs.py`
- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_task_to_workflow_strategy.py tests/test_architecture_baseline_docs.py`

## Deduplication / centralization decisions

- Reused `stdlib/adaptation.py` for selected-workflow snapshotting and shared loader-backed workflow-parameter validation rather than duplicating repo-root resolution or parameter coercion logic in the new workflow package.
- Kept the front-door `adapt` update prompt/checklist/doc-only so the existing strategy summary schema and publication validators remain stable.

## Out-of-phase justification

- The `task_to_workflow_strategy` prompt/doc/checklist/test updates and the recursive memory/test updates are phase-3 follow-through from the cycle-6 plan, required to keep the `adapt` route handoff and standing memory coherent with the shipped building block.
