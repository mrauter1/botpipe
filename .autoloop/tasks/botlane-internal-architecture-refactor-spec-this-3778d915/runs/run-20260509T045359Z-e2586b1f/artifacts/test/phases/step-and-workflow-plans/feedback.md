# Test Author ↔ Test Auditor Feedback

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: test
- Phase ID: step-and-workflow-plans
- Phase Directory Key: step-and-workflow-plans
- Phase Title: Step And Workflow Plans
- Scope: phase-local authoritative verifier artifact

- Added branch-group parity regression coverage in `tests/unit/test_step_plans.py` for the explicit nested-parity failure path, alongside the existing top-level parity rebuild coverage.
- Confirmed focused adapter coverage passes with `.venv/bin/python -m pytest tests/unit/test_step_plans.py tests/unit/test_workflow_plan_adapters.py`.

- TST-001 `non-blocking` — Audit closure
  The added tests cover the changed adapter behavior at the right level: step-plan lowering, branch-group parity rebuild, the loud nested-parity failure path, topology-hash parity, route-table parity, and copied-map immutability. Focused audit rerun passed with `.venv/bin/python -m pytest tests/unit/test_step_plans.py tests/unit/test_workflow_plan_adapters.py`. No blocking audit findings in this phase scope.
