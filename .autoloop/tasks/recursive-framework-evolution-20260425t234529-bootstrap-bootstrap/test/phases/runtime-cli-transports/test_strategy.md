# Test Strategy

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-bootstrap
- Pair: test
- Phase ID: runtime-cli-transports
- Phase Directory Key: runtime-cli-transports
- Phase Title: Runtime CLI Transports
- Scope: phase-local producer artifact

## Behavior to coverage map
- AC-1 transport purity: `tests/runtime/test_provider_backends.py`
  - file-content purity checks ban semantic request/response types and shared parsing/rendering helper names in `runtime/providers/codex.py` and `runtime/providers/claude.py`
  - compatibility shims are allowed, but transport execution remains isolated behind `run_turn(...)`
- AC-2 backend wrapping: `tests/runtime/test_provider_backends.py`
  - backend resolver still dispatches by configured provider name
  - resolved backend is `RenderedLLMProvider` around `CodexTransport` / `ClaudeTransport`
  - compatibility builders and restored provider classes still resolve to rendered wrappers
- AC-3 runtime prompt transport and core parsing ownership: `tests/runtime/test_runtime_providers.py`
  - Codex transport sends `RenderedProviderTurn.prompt_text` to stdin
  - Claude transport sends `RenderedProviderTurn.prompt_text` via `-p`
  - transports return raw assistant text for outcome-bearing turns
  - `RenderedLLMProvider` performs verifier/LLM outcome parsing in core

## Preserved invariants checked
- cross-provider session resume is still rejected
- CLI capability validation and error messages remain intact
- restored compatibility names do not change backend selection semantics
- legacy Codex constructor shape `(config, commands)` still works

## Edge cases and failure paths
- unavailable CLI binaries
- unsupported CLI flags / capability mismatches
- malformed provider envelopes
- non-zero subprocess exit codes
- unusable Codex JSONL output
- compatibility re-exports and direct provider-class construction

## Stability notes
- tests are deterministic and monkeypatch CLI subprocess/help probes instead of invoking real binaries
- no timing, network, or filesystem race dependencies are introduced

## Known gaps
- no full-suite rerun in this phase-local test turn
- compatibility shims are validated for construction/wrapping, not for separate end-to-end provider execution because transport execution paths are already covered elsewhere in the runtime provider tests
