# Implementation Notes

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: implement
- Phase ID: async-transports-and-rendered-provider
- Phase Directory Key: async-transports-and-rendered-provider
- Phase Title: Async transports and rendered provider
- Scope: phase-local producer artifact

## Files changed
- `autoloop/runtime/providers/_common.py`
- `autoloop/core/providers/fake.py`
- `tests/unit/test_provider_boundary_core.py`
- `tests/runtime/test_runtime_providers.py`

## Symbols touched
- `terminate_text_subprocess`
- `ProviderCall`
- `ScriptedLLMProvider.run_producer`
- `ScriptedLLMProvider.run_verifier`
- `ScriptedLLMProvider.run_llm`
- `ScriptedLLMProvider.run_operation`
- `ScriptedLLMProvider._pop_async`
- `ScriptedLLMProvider._pop_sync`
- `communicate_text_subprocess(...)` coverage

## Checklist mapping
- `M3 Async rendered provider and built-in transports`: hardened the shared async subprocess cancellation helper against already-exited process races; built-in Codex/Claude turn execution remains on async-only `run_turn(...)` without `_async` variants.
- `M6 Test and strictness hardening`: added fake-provider async/session coverage and cancellation-path coverage for the shared transport helper.

## Assumptions
- The previously approved helper-only sync exception for `llm()` / `classify()` remains intentional and outlives this turn.
- Capability probes using `subprocess.run(...)` for CLI `--help` validation remain acceptable because the phase restriction is on provider turn execution, not install-time/help probing.

## Preserved invariants
- Built-in provider turn execution remains async-only through `ProviderTransport.run_turn(...)`.
- No sync provider protocol methods or `_async` provider/transport variants were reintroduced.
- The fake provider still preserves sync `run_operation(...)` only for the explicit helper compatibility path.

## Intended behavior changes
- Async subprocess cancellation now preserves the original task cancellation when the child process exits between the liveness check and the signal call.
- Scripted fake-provider async turns now accept awaited scripted callbacks, allowing deterministic scheduling tests to use `await asyncio.sleep(...)`.
- Fake-provider call records now include the inbound `SessionBinding`, which makes branch/session assertions possible without custom provider doubles.

## Known non-changes
- `autoloop/runtime/providers/codex.py`, `autoloop/runtime/providers/claude.py`, and `autoloop/runtime/provider_backends.py` were not semantically changed in this turn because their async-only turn surfaces were already in place from earlier phase work.
- No branch-group scheduler/runtime logic was changed in this phase-local turn.

## Expected side effects
- Tests that inspect `ScriptedLLMProvider.calls` can now assert session identity and can script async callback turns directly.
- Cancellation semantics remain centralized in the shared subprocess helper instead of duplicated in per-provider tests, including `ProcessLookupError` races on already-exited children.

## Validation performed
- `python3 -m py_compile autoloop/runtime/providers/_common.py autoloop/core/providers/fake.py tests/unit/test_provider_boundary_core.py tests/runtime/test_runtime_providers.py`
- `rg -n "run_turn_async|run_llm_async|run_producer_async|run_verifier_async" autoloop tests`
- `rg -n "asyncio.create_subprocess_exec\\(" autoloop/runtime/providers`
- `rg -n "subprocess\\.run\\(" autoloop/runtime/providers autoloop/core/providers`

## Validation not performed
- `pytest` could not be run in this environment because neither `pytest` nor `python3 -m pytest` is installed.

## Deduplication / centralization decisions
- Kept subprocess cancellation assertions at `communicate_text_subprocess(...)` / `terminate_text_subprocess(...)`, the shared helpers already used by both Codex and Claude transports, instead of cloning the same race handling in each transport class.
