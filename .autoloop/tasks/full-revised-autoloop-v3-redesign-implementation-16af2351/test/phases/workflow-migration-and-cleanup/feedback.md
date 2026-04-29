# Test Author ↔ Test Auditor Feedback

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: test
- Phase ID: workflow-migration-and-cleanup
- Phase Directory Key: workflow-migration-and-cleanup
- Phase Title: Workflow migration and cleanup
- Scope: phase-local authoritative verifier artifact

## Test Additions

- Added `tests/unit/test_simple_surface.py::test_python_step_entry_alias_preserves_bootstrap_order_and_installs_compat_handler` to pin the central migration shim that keeps explicit `entry = bootstrap` ordering and installs callable `on_<step>` helpers for canonical `python_step(...)` declarations.
- Updated `tests/unit/test_simple_surface.py::test_simple_system_step_lowers_to_core_system_handler_without_on_step_method` so it asserts the new preserved-compat behavior (`on_run` alias present) instead of the pre-migration absence check.
- Validated with targeted `pytest` on the two affected tests plus `py_compile` for the modified test file.

## Audit Result

- No audit findings in this cycle.
- The targeted unit coverage matches the shared migration decision to centralize the compatibility shim in simple-surface lowering, and the assertions are deterministic: they compile a local workflow class, inspect compiled step order, and check callable handler alias presence without timing or environment-sensitive setup.
