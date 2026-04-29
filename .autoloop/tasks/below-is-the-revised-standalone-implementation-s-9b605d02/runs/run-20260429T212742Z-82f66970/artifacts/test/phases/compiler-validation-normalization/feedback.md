# Test Author ↔ Test Auditor Feedback

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: test
- Phase ID: compiler-validation-normalization
- Phase Directory Key: compiler-validation-normalization
- Phase Title: Compiler And Validation Canonicalization
- Scope: phase-local authoritative verifier artifact

- Added focused coverage in `tests/unit/test_simple_surface.py` for step-kind default-route injection, `control_routes=False`, runtime Pydantic step-state serialization/rehydration, and fast-fail suppression of incomplete `item_state` / `step_item_state` public access. Validation performed in this environment was syntax-only via `python3 -m py_compile tests/unit/test_simple_surface.py`.

- TST-001 `blocking` [`tests/unit/test_simple_surface.py`, `core/validation.py:1025-1027`, `core/validation.py:1407-1408`]: The new suite still leaves part of AC-3 unpinned. It checks `{item.state...}` rejection and `control_routes=False` for plain `step` and `produce_verify_step`, but it does not cover the separate `{step_name.item_state...}` prompt-validation branch or the `control_routes=False` branch for `python_step` / `workflow_step`, which is implemented separately in `_inject_reserved_routes()`. A regression that accidentally re-allows step-item placeholders or keeps injecting `"failed"` for python/workflow steps would pass the current tests. Minimal fix: add compile-time assertions for a `{review.item_state.attempts}` placeholder failure and for `python_step(..., control_routes=False)` / `workflow_step(..., control_routes=False)` route tables that omit injected control routes.
