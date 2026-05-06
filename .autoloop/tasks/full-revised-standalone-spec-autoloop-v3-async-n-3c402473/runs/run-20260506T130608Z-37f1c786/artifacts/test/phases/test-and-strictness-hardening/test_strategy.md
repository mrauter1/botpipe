# Test Strategy

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: test
- Phase ID: test-and-strictness-hardening
- Phase Directory Key: test-and-strictness-hardening
- Phase Title: Test and strictness hardening
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 strictness scans for async-only provider and transport contracts:
  covered by `tests/strictness/test_no_compat.py::test_provider_protocols_remain_async_only`,
  `test_active_python_files_do_not_reintroduce_legacy_provider_async_probe_or_suffix_surfaces`,
  `test_runtime_transport_modules_define_async_run_turn_only`,
  `test_rendered_provider_async_entrypoints_do_not_bridge_through_sync_helpers`.
- AC-1 scanner regression resistance:
  covered by `tests/strictness/test_no_compat.py::test_rendered_provider_async_bridge_scanner_catches_non_operation_sync_bridges`,
  `test_rendered_provider_async_bridge_scanner_allows_explicit_operation_path_only`,
  `test_runtime_transport_entrypoint_scanner_catches_sync_and_legacy_async_forms`.
- AC-1 construction-boundary rejection of invalid sync implementations:
  covered by `tests/unit/test_provider_boundary_core.py::test_provider_validation_rejects_sync_only_provider_methods`,
  `test_transport_validation_rejects_sync_only_run_turn`,
  `test_rendered_provider_rejects_sync_only_transport_at_construction`,
  and `tests/runtime/test_provider_backends.py::test_resolve_provider_backend_rejects_sync_transport_builder_output`.
- AC-2 sequential runtime parity and helper compatibility boundary:
  covered by `tests/contract/test_async_engine_spine.py` and `tests/contract/test_engine_contracts.py`,
  preserving the clarified narrow `llm()` / `classify()` operation-executor exception without reintroducing sync provider contracts.
- AC-2 branch-group runtime semantics and evidence paths:
  covered by `tests/contract/test_branch_group_runtime.py`, including concurrency, fail-fast, fan-in, questions, captured goto/fail, evidence writes, and manifest/context failure paths.
- AC-2 static graph and compile-time branch-group metadata:
  covered by `tests/runtime/test_runtime_static_graph.py`, `tests/unit/test_simple_surface.py`, and `tests/unit/test_validation.py`.
- AC-2 branch-session and shared-context invariants:
  covered by `tests/unit/test_branch_group_context_sessions.py` and branch-group runtime contract tests.

## Preserved invariants checked

- `LLMProvider` exposes only async `run_producer`, `run_verifier`, and `run_llm`.
- `ProviderTransport` exposes only async `run_turn`.
- The explicit `run_operation(...)` / `_run_operation_turn(...)` compatibility boundary remains the only allowed sync bridge surface for rendered providers.
- Invalid sync transports fail at provider construction time rather than during runtime branch execution.

## Edge cases and failure paths

- Helper-level sync bridging hidden below top-level async rendered-provider entrypoints.
- Legacy `run_turn_async` reintroduction alongside an async `run_turn`.
- Sync `run_turn(...)` builder outputs returned from backend resolution.
- Branch-group evidence write failures before fan-in or mechanical outcome routing.
- Async subprocess cancellation cleanup without depending on unstable internal wait-call counts.

## Flake-risk controls

- Scanner tests operate on temporary synthetic modules to avoid depending on repository layout drift outside the targeted helper semantics.
- Runtime and branch-group assertions continue to prefer deterministic manifest ordering, explicit error messages, and filesystem-backed evidence paths over timing-only checks.

## Known gaps

- The phase-local matrix validates the targeted strictness/runtime/contract/unit suites, not every repository test file.
- Provider CLI help-probe behavior remains covered at the backend/runtime layer rather than duplicated in strictness tests.
