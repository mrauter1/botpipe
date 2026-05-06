# Test Strategy

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: test
- Phase ID: provider-contract-cutover
- Phase Directory Key: provider-contract-cutover
- Phase Title: Provider contract cutover
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- Async-only provider contract:
  Covered by `tests/unit/test_provider_boundary_core.py` and `tests/contract/test_async_engine_spine.py` assertions that sync-only provider methods fail at construction and async-only methods remain accepted.
- Async-only transport contract:
  Covered by `tests/unit/test_provider_boundary_core.py` transport validation checks and `tests/runtime/test_runtime_providers.py` transport execution tests using `asyncio.create_subprocess_exec(...)`.
- Rendered-provider helper compatibility with explicit executor:
  Covered by `tests/contract/test_engine_contracts.py::test_python_step_feedforward_helpers_accept_plain_string_prompts_with_rendered_provider`.
- Rendered-provider helper failure without explicit executor in active loop:
  Covered by `tests/contract/test_engine_contracts.py::test_python_step_feedforward_helpers_require_operation_executor_for_rendered_provider_in_active_loop`.
- Narrowed sync exception outside active loop:
  Covered by `tests/unit/test_provider_boundary_core.py::test_rendered_llm_provider_prefers_async_transport_for_sync_operations_outside_active_loop`.
- Built-in backend wiring and test isolation:
  Covered by `tests/runtime/test_provider_backends.py::test_resolve_provider_backend_dispatches_by_provider_name`, which now stubs both backend and operation-executor builder maps.
- Async subprocess regression coverage for Codex and Claude transports:
  Covered by the affected transport and rendered-provider tests in `tests/runtime/test_runtime_providers.py`, which now fake `asyncio.create_subprocess_exec(...)` and `communicate(...)`.

## Preserved invariants checked
- `LLMProvider` and `ProviderTransport` remain async-only public contracts.
- Invalid providers and transports fail before runtime branch execution begins.
- Exported sequential `llm()` / `classify()` behavior remains available when the rendered provider is constructed with the explicit compatibility executor.
- The temporary sync compatibility exception stays narrower than the transport/provider protocol surface.

## Edge cases and failure paths
- Missing `operation_executor=...` for rendered-provider helper calls in an active workflow loop raises a clear runtime error and does not execute a transport turn.
- Sync helper calls outside an active loop continue to use the async transport bridge rather than the compatibility executor.
- Transport tests still cover malformed output, non-zero exit codes, cross-provider resume rejection, and prompt/input propagation.

## Stabilization notes
- Provider transport tests use in-memory async subprocess stubs instead of real CLIs.
- No timing-based assertions were added.
- No network or external process availability is required beyond existing CLI-help probe tests.

## Known gaps
- Full `pytest` execution could not be run in this environment because `pytest` is not installed.
- End-to-end runtime smoke coverage for the built-in CLIs remains environment-dependent and is not extended here.
