# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c12
- Pair: implement
- Phase ID: company-operation-to-recursive-improvement-cycle
- Phase Directory Key: company-operation-to-recursive-improvement-cycle
- Phase Title: Ship Company Recursive Improvement Workflow
- Scope: phase-local producer artifact

## Files changed

- `workflows/company_operation_to_recursive_improvement_cycle/` (`__init__.py`, `workflow.toml`, `params.py`, `contracts.py`, `workflow.py`, `prompts/*`, `assets/recursive_improvement_cycle_checklist.md`)
- `docs/workflows/company_operation_to_recursive_improvement_cycle.md`
- `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `tests/test_architecture_baseline_docs.py`
- `.autoloop/tasks/recursive-framework-evolution-20260423t173132-c12/decisions.txt`

## Symbols touched

- `Parameters`
- `CompanyOperationFramingPayload`
- `RecursiveImprovementAnalysisPayload`
- `RecursiveImprovementCyclePayload`
- `build_workflow(...)`
- `on_bootstrap(...)`
- `on_capture_company_operation_context(...)`
- `on_frame_company_operation(...)`
- `on_analyze_recursive_improvement_pressures(...)`
- `on_package_recursive_improvement_cycle(...)`
- `on_publish_recursive_improvement_cycle(...)`

## Checklist mapping

- `1. Add the additive company-operation snapshot seam ...`: satisfied by the earlier `company-operation-snapshot-seam` dependency; this phase consumed that seam without widening it further.
- `2. Ship workflows/company_operation_to_recursive_improvement_cycle/, its prompts/assets/contracts/params/docs, and workflow-specific runtime proof.`: done.
- `3. Update .autoloop_recursive/ memory and tests/test_architecture_baseline_docs.py, then run the targeted closeout suite ...`: done.

## Assumptions

- The company-level learner remains scoped to repo-local `.autoloop` task history plus discovered workflow packages already visible in this checkout.

## Preserved invariants

- Runtime-injected control stays limited to `expected_output_schema`, `available_routes`, and `route_contracts`.
- The workflow stops at publication; it does not auto-run builder, governance, refinement, decomposition, or remediation follow-through.
- Authoritative workflow packages and `.autoloop` task/run history remain read-only inputs to this workflow.

## Intended behavior changes

- Added the end-to-end `company_operation_to_recursive_improvement_cycle` workflow package, its explicit step prompts, typed pair contracts, publication checklist asset, and workflow-local docs.
- Added workflow-local publish validation for missing snapshots, unknown focus task/workflow references, invalid priority categories, summary drift, and hidden downstream execution language.
- Advanced recursive memory and architecture-baseline proof to record cycle 12 as shipped.

## Known non-changes

- No CLI, provider, session, manifest, or runtime-owned orchestration contracts changed.
- No downstream workflow is invoked implicitly from the published recursive-improvement package.

## Expected side effects

- Operators can now publish a company-level recursive-improvement cycle package with capability, portfolio-health, and company-operation evidence plus explicit next actions and a deterministic receipt.

## Validation performed

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/pytest -q tests/runtime/test_company_operation_to_recursive_improvement_cycle.py` -> `24 passed`
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_builder_package.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/test_architecture_baseline_docs.py` -> `162 passed`

## Deduplication / centralization decisions

- Deterministic capture reuses the existing lifecycle, capability-snapshot, portfolio-health, and company-operation snapshot helpers instead of adding new runtime machinery.
- Publication drift checks stay workflow-local in `workflow.py` because they are specific to this workflow's candidate manifest, summary, and publication-only boundary.
