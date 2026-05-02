# Test Author ↔ Test Auditor Feedback

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: test
- Phase ID: migrate-runtime-test-surfaces
- Phase Directory Key: migrate-runtime-test-surfaces
- Phase Title: Migrate Runtime Test Surfaces
- Scope: phase-local authoritative verifier artifact

- Refined `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py` helper annotations to match the final direct-call contract (`control result` + `ctx.state`), and documented the behavior-to-test coverage map for bootstrap, capture, route-skip, publish, and after-verifier surfaces.
- Validation: `./.venv/bin/pytest -q tests/runtime/test_workflow_run_traces_to_optimization_candidates.py` -> `39 passed` with existing contract warnings only.
