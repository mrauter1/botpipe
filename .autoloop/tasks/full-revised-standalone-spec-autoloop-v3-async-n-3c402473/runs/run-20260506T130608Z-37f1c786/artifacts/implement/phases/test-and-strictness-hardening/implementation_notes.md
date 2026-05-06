# Implementation Notes

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: implement
- Phase ID: test-and-strictness-hardening
- Phase Directory Key: test-and-strictness-hardening
- Phase Title: Test and strictness hardening
- Scope: phase-local producer artifact

## Files changed
- `tests/strictness/test_no_compat.py`
- `tests/unit/test_provider_boundary_core.py`
- `tests/runtime/test_provider_backends.py`
- `runs/run-20260506T130608Z-37f1c786/decisions.txt`

## Symbols touched
- `test_provider_protocols_remain_async_only`
- `test_active_python_files_do_not_reintroduce_legacy_provider_async_probe_or_suffix_surfaces`
- `test_rendered_provider_async_entrypoints_do_not_bridge_through_sync_helpers`
- `test_runtime_transport_modules_define_async_run_turn_only`
- `_rendered_provider_async_bridge_failures`
- `_runtime_transport_entrypoint_failures`
- `test_provider_validation_rejects_sync_only_provider_methods`
- `test_transport_validation_rejects_sync_only_run_turn`
- `test_rendered_provider_rejects_sync_only_transport_at_construction`
- `test_fake_provider_and_rendered_transport_surfaces_remain_async_only`
- `test_resolve_provider_backend_rejects_sync_transport_builder_output`

## Checklist mapping
- AC-1: added strictness coverage for async-only provider/transport protocols, forbidden legacy `_async` / `supports_async_*` surfaces, and rendered-provider async entrypoints that must not bridge through sync helpers.
- AC-2: added provider/backend coverage for early invalid-transport rejection during provider construction.

## Assumptions
- The explicit clarification preserving `llm()` / `classify()` compatibility remains authoritative, so strictness scans must not treat the narrow `operation_executor` bridge as a general transport regression.

## Preserved invariants
- Async provider protocol remains `run_producer`, `run_verifier`, `run_llm` only.
- Async transport protocol remains `run_turn` only.
- Invalid sync transports fail at construction time rather than during branch runtime.

## Intended behavior changes
- None in production code; this phase hardens test enforcement only.

## Known non-changes
- No runtime/provider implementation logic changed.
- No CLI capability-probe behavior changed.
- No branch-group runtime behavior changed.

## Expected side effects
- Future reintroduction of sync provider/transport contract surfaces or legacy async-probe helpers should fail faster at the strictness/unit layer.

## Validation performed
- Static repository inspection of provider, rendered-provider, branch-group, runtime-provider, backend, and existing test surfaces.
- Environment limitation: could not execute pytest because neither `pytest` nor a Python environment with the package installed is available in this workspace (`pytest`, `python`, and `python3 -m pytest` were unavailable or missing the module).

## Deduplication / centralization
- Strictness checks were centralized in `tests/strictness/test_no_compat.py` for tree-wide contract scanning.
- Construction-boundary validation stayed in provider-boundary/runtime-backend tests instead of duplicating transport assertions across branch-group suites.
