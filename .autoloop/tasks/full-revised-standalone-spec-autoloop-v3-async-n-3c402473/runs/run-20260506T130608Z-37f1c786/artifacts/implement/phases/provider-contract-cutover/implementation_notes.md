# Implementation Notes

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: implement
- Phase ID: provider-contract-cutover
- Phase Directory Key: provider-contract-cutover
- Phase Title: Provider contract cutover
- Scope: phase-local producer artifact

## Files changed
- `autoloop/core/providers/protocols.py`
- `autoloop/core/providers/__init__.py`
- `autoloop/core/providers/rendered.py`
- `autoloop/core/providers/fake.py`
- `autoloop/core/engine.py`
- `autoloop/core/engine_collaborators.py`
- `autoloop/core/branch_groups/runtime.py`
- `autoloop/core/operations.py`
- `autoloop/runtime/provider_backends.py`
- `autoloop/runtime/providers/_common.py`
- `autoloop/runtime/providers/codex.py`
- `autoloop/runtime/providers/claude.py`
- `tests/contract/test_async_step_dispatcher.py`
- `tests/contract/test_async_engine_spine.py`
- `tests/contract/test_branch_group_runtime.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_runtime_tracing.py`
- `tests/runtime/test_provider_backends.py`
- `tests/runtime/test_runtime_providers.py`
- `tests/runtime/test_package_cli.py`
- `tests/unit/test_provider_boundary_core.py`

## Symbols touched
- `LLMProvider`
- `ProviderTransport`
- `validate_llm_provider(...)`
- `validate_provider_transport(...)`
- `RenderedLLMProvider.run_producer/run_verifier/run_llm/run_operation`
- `RenderedLLMProvider.operation_executor`
- `ScriptedLLMProvider.run_producer/run_verifier/run_llm/run_operation`
- `Engine.__init__(...)`
- `StepDispatcher._call_provider(...)`
- `BranchGroupRuntime.run_async(...)`
- `OperationRuntime.provider`
- `provider_configuration(...)`
- `_run_operation_turn(...)`
- `communicate_text_subprocess(...)`
- `terminate_text_subprocess(...)`
- `run_text_subprocess(...)`
- `CodexTransport.run_turn(...)`
- `ClaudeTransport.run_turn(...)`
- `build_codex_operation_executor(...)`
- `build_claude_operation_executor(...)`

## Checklist mapping
- Plan `M2. Provider contract cutover`: completed for async-only provider/transport protocols, constructor validation, removal of async probing helpers, and dispatcher cutover to direct awaited provider calls.
- Plan `M3. Async rendered provider and built-in transports`: partially pulled forward to keep the contract coherent; rendered provider and built-in Codex/Claude transports now expose only async workflow-turn entrypoints, with a separate explicit rendered-provider operation executor retained as the temporary active-loop compatibility exception for exported `llm()` / `classify()`.
- Plan `M1/M4/M5/M6`: not targeted beyond the provider-touching regression updates required to keep the narrowed phase coherent.

## Assumptions
- Phase-local acceptance allows retaining `run_operation(...)` as a non-protocol compatibility boundary until a later operation-runtime rewrite lands.
- The clarification recorded in the raw log explicitly allows a temporary narrow sync exception for `llm()` / `classify()` compatibility inside synchronous Python-step execution under the async engine.
- Constructor-time rejection of sync-only providers is the intended replacement for the temporary sequential sync-provider fallback introduced in the prior phase.

## Preserved invariants
- Public non-parallel workflow authoring APIs remain unchanged.
- `Engine.run(...)`/`run_async(...)` entrypoints remain available.
- Exported sequential `llm()` and `classify()` helpers still use `run_operation(...)` and were not removed.
- Built-in provider capability probes (`codex --help`, `claude --help`) still use existing config validation surfaces.

## Intended behavior changes
- Core provider protocol now requires async `run_producer(...)`, `run_verifier(...)`, and `run_llm(...)` only.
- Core transport protocol now requires async `run_turn(...)` only.
- Sync-only providers and sync-only transports fail during construction instead of being discovered later during execution or branch scheduling.
- Branch-group runtime no longer probes provider async capability at runtime.
- Built-in Codex/Claude transports now execute workflow turns only through async subprocess paths.
- Rendered provider operation compatibility is now explicit at construction via `operation_executor=...` instead of implicit transport duck-typing, and the sync bridge is used only when `run_operation(...)` is invoked from an already-active event loop.

## Known non-changes
- `autoloop/core/operations.py` still relies on sync `run_operation(...)`; this method is no longer part of the core provider protocol and is validated locally when operation helpers are used.
- Built-in operation-helper compatibility still uses sync subprocess execution, but that path is now centralized outside the transport protocol, wired explicitly through rendered-provider/backend construction, and limited to active-loop helper execution rather than all sync operation calls.
- Operation branch enablement, child-workflow branch support, and broader branch-group follow-on work remain untouched.
- Help-surface capability probing for provider CLIs still uses `subprocess.run(...)`; only workflow turn execution was cut over.

## Expected side effects
- Any custom test/provider object that previously implemented only sync step methods must now switch to async methods or it will fail immediately at `Engine(...)` construction.
- Any custom transport used with `RenderedLLMProvider(...)` must now expose async `run_turn(...)`.
- Built-in rendered providers now prefer the async transport path for sync helper calls made outside an active event loop; the explicit sync operation executor is reserved for active-loop helper compatibility.
- Any custom `RenderedLLMProvider(...)` used with `llm()` / `classify()` inside an active workflow loop must now pass an explicit `operation_executor=...` if it needs operation-helper compatibility.

## Validation performed
- `python3 -m py_compile` over the touched runtime/core modules plus `tests/runtime/test_provider_backends.py`, `tests/runtime/test_runtime_providers.py`, and `tests/unit/test_provider_boundary_core.py`.
- Repository grep verification that `AsyncLLMProvider`, `AsyncProviderTransport`, `supports_async_llm_provider(...)`, `supports_async_provider_transport(...)`, `run_llm_async(...)`, `run_producer_async(...)`, `run_verifier_async(...)`, and `run_turn_async(...)` no longer appear in runtime code.
- Full pytest execution could not be run in this environment because `pytest` is not installed.
- Runtime smoke execution could not be run in this environment because `pydantic` is not installed.

## Deduplication / centralization decisions
- Centralized constructor validation in `autoloop/core/providers/protocols.py` so `Engine(...)` and `RenderedLLMProvider(...)` share the same async-contract enforcement.
- Centralized async subprocess cancellation handling in `autoloop/runtime/providers/_common.py` for both Codex and Claude transports.
- Centralized the explicit compatibility-only sync subprocess helper in `autoloop/runtime/providers/_common.py`, removed undocumented transport duck-typing from `RenderedLLMProvider.run_operation(...)`, and narrowed the sync compatibility exception to active-loop helper execution only.
