# Test Strategy

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-bootstrap
- Pair: test
- Phase ID: provider-boundary-core
- Phase Directory Key: provider-boundary-core
- Phase Title: Core Provider Boundary
- Scope: phase-local producer artifact

## Behavior-to-test map
- Core boundary models: `tests/unit/test_provider_boundary_core.py` covers rendered turn/result dataclasses indirectly through `RenderedLLMProvider` transport stubs and semantic response shaping.
- Shared renderer contract: `tests/unit/test_provider_boundary_core.py` covers required markdown sections, route/output tables, handoff/retry optional sections, and exclusion of raw provider output / telemetry phrases.
- Render policy surface: `tests/unit/test_provider_boundary_core.py` covers explicit truncation behavior and the default fail-on-overflow path.
- Core parsing ownership: `tests/unit/test_provider_boundary_core.py` and `tests/runtime/test_runtime_providers.py` cover outcome parsing via `RenderedLLMProvider` and the shared core parser helpers.
- Runtime provider integration: `tests/runtime/test_runtime_providers.py` covers producer compatibility, verifier/LLM rendered prompt usage, session resume behavior, CLI envelope parsing, and subprocess failure paths for Codex and Claude.

## Preserved invariants checked
- Engine-facing semantic provider methods still return `ProducerResponse` / `OutcomeResponse`.
- Runtime prompts for verifier/LLM no longer include producer raw output.
- Producer turns keep the direct prompt path in this phase.
- Session metadata and resume semantics remain unchanged across Codex and Claude.

## Edge cases and failure paths
- Missing resolved prompt text raises `ProviderExecutionError`.
- Outcome JSON rejects malformed payloads and missing required keys.
- Render policy rejects over-budget prompts by default and truncates only when explicitly requested.
- CLI transports reject malformed envelopes, non-zero exits, and cross-provider session resumes.

## Stabilization
- All provider CLI interactions are monkeypatched subprocess calls with deterministic stdout/stderr fixtures.
- No network, timing, filesystem race, or nondeterministic ordering dependencies are introduced in this phase slice.

## Known gaps
- Backend resolution returning `RenderedLLMProvider(transport)` is intentionally deferred to later phases and is not encoded here.
- Engine-level artifact metadata injection, retry semantics, and handoff delivery are out of scope for this phase and remain uncovered here by design.
