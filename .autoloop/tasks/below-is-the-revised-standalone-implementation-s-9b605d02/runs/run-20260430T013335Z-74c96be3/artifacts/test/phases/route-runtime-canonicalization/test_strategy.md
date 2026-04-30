# Test Strategy

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: test
- Phase ID: route-runtime-canonicalization
- Phase Directory Key: route-runtime-canonicalization
- Phase Title: Canonicalize Route And Runtime Internals
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Active validation rejects legacy live terminals:
  `tests/unit/test_validation.py::test_validation_rejects_legacy_success_terminal_string`
  Pins the removed `SUCCESS` authoring path by asserting a workflow with `"SUCCESS"` in `transitions` fails validation.
- `_compat` no longer exposes removed route/runtime helpers:
  `tests/unit/test_simple_surface.py::test_core_compat_surface_excludes_removed_route_runtime_helpers`
  Pins the narrowed compatibility surface by checking `SUCCESS`, `RouteInfo`, and legacy step wrappers are absent and fail to import from `autoloop_v3.core._compat`.
- Preserved canonical payload/runtime invariants already covered by maintained suites:
  `tests/strictness/test_no_compat.py`
  Scans the active tree for banned legacy names and asserts canonical topology/static-graph payload keys only.
- Preserved persisted compatibility seam already covered by maintained suites:
  `tests/runtime/test_compatibility_runtime.py`
  Keeps session/checkpoint normalization coverage while no longer exercising live `_compat` workflow authoring.

## Edge Cases

- Legacy terminal rejection is pinned at validation time, before compilation can silently canonicalize it.
- `_compat` regression coverage checks both attribute absence and explicit import failure so accidental re-exports are caught from either direction.

## Failure Paths

- Invalid live transition destination `"SUCCESS"` raises `WorkflowValidationError`.
- Importing removed `_compat` route/runtime helpers raises `ImportError`.

## Known Gaps

- `pytest` is unavailable in this environment.
- Direct runtime imports also fail here because `pydantic` is not installed, so executable validation was limited to source inspection and `python3 -m py_compile`.
