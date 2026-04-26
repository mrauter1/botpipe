# Test Strategy

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: test
- Phase ID: provider-usage-plumbing
- Phase Directory Key: provider-usage-plumbing
- Phase Title: Provider Usage Plumbing
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- Provider usage models and response defaults
  - Covered by `tests/unit/test_provider_boundary_core.py`
  - Checks partial `TokenUsage` construction and default `usage=None` on `ProducerResponse` and `OutcomeResponse`
- Fake provider and rendered provider plumbing
  - Covered by `tests/unit/test_provider_boundary_core.py`
  - Checks fake provider emission of explicit usage and passthrough from `ProviderTurnResult` into semantic provider responses
- Runtime provider usage extraction
  - Covered by `tests/runtime/test_runtime_providers.py`
  - Checks Codex JSONL usage extraction, Claude JSON usage extraction, and no-usage behavior remaining `None`
- Persisted session metadata invariant
  - Covered by `tests/runtime/test_runtime_providers.py`
  - Checks per-turn usage fields are stripped from persisted `SessionBinding.provider_metadata` while other provider metadata remains
- Engine step-finish exposure
  - Covered by `tests/contract/test_engine_contracts.py`
  - Checks pair steps expose producer/verifier usage, llm steps expose llm usage, and system steps keep `provider_usage=None`
- Adjacent compatibility/runtime regression surface
  - Covered by `tests/runtime/test_provider_backends.py` and `tests/runtime/test_compatibility_runtime.py`
  - Checks provider backend resolution and session payload roundtrips remain stable after the transport/result shape change

## Preserved invariants checked
- Missing provider usage is non-fatal and remains `None`
- Existing provider rendering behavior and prompt hygiene remain unchanged
- Session resume metadata keeps stable identity fields and excludes transient usage blobs
- Workflow step routing, raw outputs, and optional handlers still behave as before

## Edge cases
- Partial usage payloads with sparse token fields
- Runtime provider output with malformed non-JSON lines but otherwise valid Codex JSONL
- Runtime provider output with usage present on one turn and absent on another

## Failure paths
- Codex missing assistant text or unusable JSONL still raises
- Claude malformed JSON or missing result still raises
- Cross-provider session resume remains rejected

## Flake-risk controls
- CLI provider tests stay deterministic by mocking subprocess calls and capability probes
- Engine tests use the scripted fake provider and temp directories only; no network or timing dependencies

## Known gaps
- No end-to-end filesystem runtime run is needed in this phase because git tracking, tracing, and workspace observability are explicitly out of scope
- Provider-specific usage key normalization is limited to the shapes covered by the current runtime adapters and tests
