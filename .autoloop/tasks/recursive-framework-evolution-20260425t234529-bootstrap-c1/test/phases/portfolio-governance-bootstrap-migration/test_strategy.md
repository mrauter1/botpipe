# Test Strategy

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-c1
- Pair: test
- Phase ID: portfolio-governance-bootstrap-migration
- Phase Directory Key: portfolio-governance-bootstrap-migration
- Phase Title: Portfolio Family Migration
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Typed bootstrap projection:
  - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - `tests/runtime/test_workflow_portfolio_to_operating_system.py`
  - `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - Each bootstrap test constructs typed `ctx.params`, leaves `workflow_params={}`, calls `on_bootstrap(...)`, and asserts normalized state projection.
- Preserved lifecycle setup:
  - The same five bootstrap tests now assert that the declared workflow sessions were opened during bootstrap.
- Preserved invocation-contract behavior:
  - The same five bootstrap tests assert unchanged invocation-contract payloads written to `invocation_contract.json`.

## Preserved Invariants Checked

- No fallback to raw `ctx.workflow_params` is needed for the migrated family when typed params exist.
- Session opening remains explicit and workflow-local.
- Workflow-specific policy remains covered by the existing runtime suites for publish/system handlers; this phase does not rewrite those assertions.

## Edge Cases

- Normalized blank optional text still resolves to `None`.
- Deduped repeatable string/list fields still preserve each workflow’s local normalization behavior.
- Positive-int bootstrap fields still flow through the typed parameter model before bootstrap executes.

## Failure Paths

- Existing parameter-coercion tests in the five runtime suites still cover blank required text and invalid normalized input before bootstrap.
- Existing runtime package tests in the same suites still cover publish/system validation and hidden-execution rejection paths adjacent to the changed bootstraps.

## Flake Risk / Stabilization

- Tests are deterministic: in-memory session store, tmp-path workspaces, no network, no timing dependencies.
- Scoped proof command: `.venv/bin/pytest -q tests/runtime/test_workflow_run_history_to_failure_modes.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py tests/runtime/test_workflow_package_to_composable_building_blocks.py tests/test_architecture_baseline_docs.py`

## Known Gaps

- No extra unit helper seam tests were added because this phase did not introduce or modify a shared helper seam; coverage stays workflow-facing and runtime-facing.
