# Test Strategy

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-c1
- Pair: test
- Phase ID: typed-bootstrap-contract-and-first-family
- Phase Directory Key: typed-bootstrap-contract-and-first-family
- Phase Title: Typed Bootstrap Contract
- Scope: phase-local producer artifact

## Behavior Coverage Map

- `task_to_candidate_workflow_set.on_bootstrap(...)`
  - Covered: typed `ctx.params` drives state initialization and invocation-contract writing when `workflow_params` is empty.
  - Preserved invariants: normalized `constraints` and `evidence_expectations` still reach `invocation_contract.json`.
- `task_to_workflow_strategy.on_bootstrap(...)`
  - Covered: typed bootstrap projection plus unchanged invocation-contract payload shape.
  - Preserved invariants: explicit lifecycle helper output still matches normalized state.
- `candidate_workflow_to_adapted_execution_plan.on_bootstrap(...)`
  - Covered: typed selected-workflow/task framing fields populate state and invocation contract without raw revalidation.
  - Preserved invariants: selected workflow reference and normalized repeatable fields are unchanged.
- `workflow_to_eval_suite.on_bootstrap(...)`
  - Covered: typed selected-workflow framing drives state and invocation contract when raw compatibility dict is empty.
  - Preserved invariants: normalized repeatable fields remain durable in the invocation contract.
- `docs/authoring.md`
  - Covered: baseline doc test now requires explicit wording that `ctx.params` is the default typed bootstrap surface, `ctx.workflow_params` remains the compatibility/raw dict surface, and bootstrap setup stays explicit through `open_workflow_sessions(...)` and `write_invocation_contract(...)`.

## Edge Cases

- Empty `workflow_params` with populated `ctx.params` for each migrated workflow.
- Normalized whitespace/duplicate repeatable inputs preserved through typed params into workflow-local invocation contracts.

## Failure Paths

- Existing parameter-coercion tests remain the failure-path guard for blank required fields and invalid raw workflow-parameter mappings.
- The refined bootstrap tests would fail if the implementation regressed to reading `ctx.workflow_params` directly.

## Validation Run

- `.venv/bin/pytest -q tests/runtime/test_task_to_candidate_workflow_set.py tests/runtime/test_task_to_workflow_strategy.py tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py tests/runtime/test_workflow_to_eval_suite.py tests/test_architecture_baseline_docs.py`
- Result: `126 passed`

## Flake Risk / Stabilization

- No timing or network dependence.
- Tests use `tmp_path`, `InMemorySessionStore`, explicit request snapshots, and direct module imports after cache clearing to keep setup deterministic.

## Known Gaps

- Later-family typed-bootstrap adoption is intentionally out of scope for this phase.
- This phase does not expand prompt README coverage or CLI/runtime contract testing beyond the existing preserved-behavior suites.
