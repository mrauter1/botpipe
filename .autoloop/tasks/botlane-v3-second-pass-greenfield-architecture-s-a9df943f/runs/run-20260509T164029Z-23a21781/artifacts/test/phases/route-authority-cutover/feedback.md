# Test Author ↔ Test Auditor Feedback

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: test
- Phase ID: route-authority-cutover
- Phase Directory Key: route-authority-cutover
- Phase Title: Make WorkflowPlan Sole Route Authority
- Scope: phase-local authoritative verifier artifact

- Added a static-graph regression assertion set in `tests/runtime/test_runtime_static_graph.py` that locks the new dual requirement together: nested branch and fan-in routes remain visible through canonical `WorkflowPlan.routes`, while top-level transition exports and `route_table.md` still exclude internal branch-step rows.
