# Test Author ↔ Test Auditor Feedback

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: test
- Phase ID: public-surface-cleanup
- Phase Directory Key: public-surface-cleanup
- Phase Title: Canonical Public Surface
- Scope: phase-local authoritative verifier artifact

- Added `tests/runtime/test_workflow_integration_parity.py::test_all_repo_workflow_packages_resolve_and_compile_under_canonical_simple_surface` to catch repo-wide workflow-package regressions after the simple public-surface rename, especially banned `produce_verify_step(..., writes=...)` call sites that per-workflow tests could miss.
- Reused the focused public-surface suites (`tests/unit/test_simple_surface.py`, `tests/strictness/test_no_compat.py`) to keep AC-1 and AC-2 coverage explicit and deterministic.
- TST-001 `non-blocking` The new compile-sweep test still emits existing Pydantic warnings from `workflows/workflow_run_traces_to_optimization_candidates/contracts.py`, but the coverage itself is stable because it asserts successful discovery/compilation only and does not depend on warning text or ordering. No blocking audit findings remain for this phase.
