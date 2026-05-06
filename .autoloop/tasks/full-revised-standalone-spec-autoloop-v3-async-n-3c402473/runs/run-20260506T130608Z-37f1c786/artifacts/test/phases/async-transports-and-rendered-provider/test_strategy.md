# Test Strategy

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: test
- Phase ID: async-transports-and-rendered-provider
- Phase Directory Key: async-transports-and-rendered-provider
- Phase Title: Async transports and rendered provider
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- `RenderedLLMProvider` async-only execution:
  - `tests/unit/test_provider_boundary_core.py`
  - covers async `run_producer(...)`, `run_verifier(...)`, `run_llm(...)`, and preserved sync `run_operation(...)` helper behavior outside/inside an active loop.
- Built-in async CLI transport execution:
  - `tests/runtime/test_runtime_providers.py`
  - covers Codex/Claude `asyncio.create_subprocess_exec(...)` usage, prompt delivery, session persistence, output parsing, and non-zero-exit failures.
- Shared async cancellation handling:
  - `tests/runtime/test_runtime_providers.py`
  - covers cancellation cleanup via `communicate_text_subprocess(...)` and `ProcessLookupError` races during `terminate()` / `kill()`.
- Async-native fake provider behavior:
  - `tests/unit/test_provider_boundary_core.py`
  - covers awaited scripted async callbacks, recorded inbound `SessionBinding`, and sync-operation rejection for awaitable scripted responses.

## Preserved invariants checked

- No provider/transport `_async` method family is used in the request-relevant runtime/provider tests.
- Built-in turn execution stays on async transports; sync subprocess execution remains scoped to the explicitly preserved helper compatibility path and CLI help probes.
- The fake provider keeps the narrow sync `run_operation(...)` escape hatch without broadening sync provider execution elsewhere.

## Edge cases

- Malformed or unusable provider output for Codex/Claude.
- Cross-provider session resume rejection.
- Cancellation after subprocess launch but before normal completion.
- Already-exited child races during terminate/kill cleanup.

## Failure paths

- Transport non-zero exit codes.
- Missing assistant/result payloads in provider output.
- Awaitable scripted response passed into the fake provider’s sync `run_operation(...)` path.

## Flake control

- No real subprocesses or network calls; tests use in-memory async process stubs.
- Cancellation tests use explicit task cancellation and deterministic stubbed wait behavior instead of wall-clock timing beyond the helper’s own timeout branch simulation.

## Known gaps

- I could not execute `pytest` in this environment because the runner is not installed, so coverage is authored and syntax-checked but not runtime-executed here.
