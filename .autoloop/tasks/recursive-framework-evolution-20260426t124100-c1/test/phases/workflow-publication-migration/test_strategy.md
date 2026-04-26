# Test Strategy

- Task ID: recursive-framework-evolution-20260426t124100-c1
- Pair: test
- Phase ID: workflow-publication-migration
- Phase Directory Key: workflow-publication-migration
- Phase Title: Workflow Publish Migration
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- Publish handlers consume typed artifacts first:
  - `tests/runtime/test_workflow_portfolio_to_operating_system.py`
    - happy path: existing publish success and receipt assertions
    - failure path: missing `governance_posture_counts` now raises `ValidationError` through the typed summary read
  - `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
    - happy path: existing publish success and receipt assertions
    - failure path: missing `priority_category_counts` now raises `ValidationError` through the typed summary read
  - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
    - preserved coverage: missing `publication_boundary` in `improvement_opportunities.json` already raises `ValidationError` through the typed summary read

- Cross-artifact drift and state alignment remain explicit:
  - portfolio summary drift, invalid lifecycle posture, and hidden-downstream checks remain covered in `test_workflow_portfolio_to_operating_system.py`
  - company summary drift, invalid priority category, and hidden-downstream checks remain covered in `test_company_operation_to_recursive_improvement_cycle.py`
  - diagnostic manifest/summary drift, selected-workflow alignment, and hidden-downstream checks remain covered in `test_workflow_run_history_to_failure_modes.py`

- Preserved invariants checked:
  - artifact filenames and receipt payloads stay compatible on the happy path
  - publication-boundary literals remain enforced
  - no runtime/provider behavior change is encoded in the tests

## Edge Cases

- Missing required typed-summary fields in portfolio and company publish paths
- Missing required typed-summary field in diagnostic publish path via the existing runtime test

## Failure Paths

- publish-time typed artifact validation failure before workflow-local drift checks
- workflow-local drift rejection after typed artifact load
- hidden downstream execution rejection in both summary `next_action` fields and markdown next-actions artifacts

## Stabilization

- Filesystem-only fixtures under `tmp_path`
- No network, timing, subprocess orchestration, or nondeterministic ordering dependencies in the new assertions

## Known Gaps

- No new refinement/decomposition publish tests were added because that family is explicitly out of scope unless it reuses the exact same seam.
