# Test Author ↔ Test Auditor Feedback

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: test
- Phase ID: branch-group-runtime-and-sessions
- Phase Directory Key: branch-group-runtime-and-sessions
- Phase Title: Branch-group runtime and sessions
- Scope: phase-local authoritative verifier artifact

- Added explicit AC-2 regression coverage in `tests/contract/test_branch_group_runtime.py` and `tests/unit/test_branch_group_context_sessions.py` for distinct branch-scoped fresh session keys, parent-session isolation, and preserved `session_id=None` first-turn behavior.
- Validation: `./.venv/bin/pytest -q tests/contract/test_branch_group_runtime.py tests/unit/test_branch_group_context_sessions.py` and `./.venv/bin/pytest -q tests/contract/test_branch_group_runtime.py tests/runtime/test_runtime_tracing.py tests/runtime/test_runtime_static_graph.py tests/unit/test_simple_surface.py tests/unit/test_primitives_and_stores.py tests/unit/test_branch_group_context_sessions.py` (`196 passed`).

- `TST-001` `non-blocking` No scoped audit findings. The added AC-2 assertions materially improve regression detection for branch-local fresh-session identity without introducing ordering or timing flake, and the phase-local branch-group bundle reran cleanly (`196 passed`).
