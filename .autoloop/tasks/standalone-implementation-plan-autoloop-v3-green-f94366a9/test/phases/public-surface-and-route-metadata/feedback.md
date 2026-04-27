# Test Author ↔ Test Auditor Feedback

- Task ID: standalone-implementation-plan-autoloop-v3-green-f94366a9
- Pair: test
- Phase ID: public-surface-and-route-metadata
- Phase Directory Key: public-surface-and-route-metadata
- Phase Title: Public surface and route metadata
- Scope: phase-local authoritative verifier artifact

- Added phase-local regression coverage for the greenfield public surface: explicit `autoloop.simple` helper signatures, `autoloop` re-exports, `workflow` shim deactivation, `route_infos`/`route_required_outputs` normalization, stdlib `RouteInfo` helper bundles, and capability payload expectations updated away from `route_contracts`.
- Validation performed: `python3 -m py_compile` on all touched test modules. Targeted `pytest` execution was attempted but unavailable because `/usr/bin/python3` in this shell does not have `pytest` installed.

- TST-001 `blocking`: AC-1 is still missing direct regression coverage for the core constructor break itself. The new tests prove the positive `route_infos` path and the simple-helper signatures, but nothing in `tests/unit/test_validation.py` or `tests/unit/test_simple_surface.py` asserts that `LLMStep`, `PairStep`, `SystemStep`, or `WorkflowStep` reject a legacy `route_contracts=` keyword. A compatibility shim or accidental `**kwargs` reintroduction in core steps would slip through unnoticed. Minimal fix: add explicit negative tests that constructing core steps with `route_contracts=` raises `TypeError`, and keep the simple-surface signature assertions as the public-side guard.
- TST-002 `blocking`: The phase request explicitly calls out `system_step(fn)` supported callable and return semantics, but the added coverage in `tests/unit/test_simple_surface.py::test_simple_system_step_lowers_to_core_system_handler_without_on_step_method` only exercises one `(state, "done")` happy path. Regressions in the documented `fn(ctx)` signature or the supported return variants (`None`, `BaseModel`, `"route"`, `Event`, `(state, Event)`) would not be caught. Minimal fix: add focused normalization tests for each documented signature/return form on the simple `system_step(fn)` surface, ideally in `tests/unit/test_simple_surface.py`.
