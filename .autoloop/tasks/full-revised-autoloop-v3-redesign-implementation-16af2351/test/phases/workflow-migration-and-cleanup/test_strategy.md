# Test Strategy

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: test
- Phase ID: workflow-migration-and-cleanup
- Phase Directory Key: workflow-migration-and-cleanup
- Phase Title: Workflow migration and cleanup
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Simple-surface migration compatibility:
  Covered by `tests/unit/test_simple_surface.py::test_python_step_entry_alias_preserves_bootstrap_order_and_installs_compat_handler`
  Checks that a canonical `python_step(...)` bootstrap declared after a review step still compiles with `entry = bootstrap`, preserves entry-first step ordering, and installs a callable `on_bootstrap` compatibility helper.

- Preserved system-step compatibility seam:
  Covered by `tests/unit/test_simple_surface.py::test_simple_system_step_lowers_to_core_system_handler_without_on_step_method`
  Checks that `python_step(handler, ...)` still lowers to a core `SystemStep` and now exposes a callable `on_<step>` alias as part of the shared migration shim.

## Preserved Invariants Checked

- Explicit `entry = bootstrap` remains authoritative even when class-body declaration order would otherwise place agentic review steps first.
- Canonical simple-surface lowering still produces core `SystemStep` handlers.
- Compatibility shims live in shared lowering behavior rather than workflow-local patches.

## Edge Cases

- Reused declaration aliasing through `entry = bootstrap` does not duplicate the bootstrap step in compiled order.
- Compatibility handler aliasing is verified on the class surface, not only through runtime package behavior.

## Failure Paths

- These tests would fail if simple-step discovery reintroduces duplicate declarations, if entry-rooted ordering regresses to raw class order, or if the `on_<step>` alias installation is removed.

## Validation

- `python3 -m py_compile tests/unit/test_simple_surface.py`
- `./.venv/bin/pytest tests/unit/test_simple_surface.py::test_simple_system_step_lowers_to_core_system_handler_without_on_step_method tests/unit/test_simple_surface.py::test_python_step_entry_alias_preserves_bootstrap_order_and_installs_compat_handler`

## Known Gaps

- I did not broaden validation to the full `tests/unit/test_simple_surface.py` file for phase signoff because it still contains an unrelated preexisting feedforward-operation failure around unsupported `callsite=` handling, which belongs to earlier feedforward-operation work rather than this migration-cleanup test slice.
