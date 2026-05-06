# Implement ↔ Code Reviewer Feedback

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: implement
- Phase ID: test-and-strictness-hardening
- Phase Directory Key: test-and-strictness-hardening
- Phase Title: Test and strictness hardening
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` [tests/strictness/test_no_compat.py::_rendered_provider_async_bridge_failures]
  The new AC-1 strictness guard only scans the direct bodies of `RenderedLLMProvider.run_producer`, `run_verifier`, and `run_llm`. A prohibited sync bridge can be reintroduced one layer down, for example by moving `run_provider_coro_sync(...)` into `_run_turn()` or another helper those async entrypoints await, and every new test added in this turn would still pass. That leaves the explicit merge-gate requirement unprotected: “provider wrappers implement async methods by calling sync code” can regress indirectly without detection. Minimal fix: make the strictness assertion ban sync-bridge calls anywhere on the non-operation rendered-provider path, for example by scanning `_run_turn()` and other helper callees used by async provider entrypoints, or by asserting `run_provider_coro_sync` only appears inside `run_operation(...)`.

- IMP-002 `blocking` [artifacts/implement/phases/test-and-strictness-hardening/implementation_notes.md]
  The implementation notes explicitly say no pytest-backed validation matrix was run because the environment lacked pytest. This phase’s deliverable is “a passing validation matrix aligned with the spec merge gate”, and AC-2 depends on runtime, contract, provider, and strictness suites actually passing, not just on static inspection and `py_compile`. As written, the phase still has no evidence that the touched tests or the surrounding merge-gate suites pass together. Minimal fix: run and record the targeted test matrix in an environment with pytest available, or use the repository’s supported test runner if one exists and capture the passing commands/results in the phase artifacts.

## Re-review update

- IMP-001 resolved: `tests/strictness/test_no_compat.py::_rendered_provider_async_bridge_failures` now treats sync bridging as legal only on the explicit operation path and scans `_run_turn(...)` as part of the forbidden non-operation surface.
- IMP-002 resolved: `implementation_notes.md` now records the `.venv/bin/python -m pytest ...` validation matrix, and the documented phase-local run passed with `381 passed, 15 warnings in 5.59s`.
- No new findings in this re-review.
