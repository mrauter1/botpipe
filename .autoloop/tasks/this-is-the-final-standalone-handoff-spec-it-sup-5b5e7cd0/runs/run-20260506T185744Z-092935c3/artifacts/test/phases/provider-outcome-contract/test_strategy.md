# Test Strategy

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: test
- Phase ID: provider-outcome-contract
- Phase Directory Key: provider-outcome-contract
- Phase Title: Canonical Provider Outcomes
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- Canonical parsing precedence:
  `tests/runtime/test_runtime_providers.py`
  Covers canonical `outcome.route_fields` winning over legacy top-level `question` / `reason`, including `route_fields.reason = null`.
- Canonical parsing no-fallback edge case:
  `tests/runtime/test_runtime_providers.py`
  Covers canonical `outcome` envelopes with empty `route_fields` not projecting a legacy top-level `question`.
- Engine failure path for canonical invalid question route:
  `tests/contract/test_engine_contracts.py`
  Covers rendered-provider retry when canonical `question` route omits `route_fields.questions`, even if a legacy top-level `question` is present.
- Engine recovery path after canonical invalid payload:
  `tests/contract/test_engine_contracts.py`
  Covers retry recovery from invalid canonical question route to valid canonical `route_fields.questions`.

## Preserved invariants checked
- Legacy top-level `tag` / `question` inputs still work in legacy-only mode.
- Canonical envelopes remain the only source of question/reason projection when `outcome` is present.
- Invalid canonical question payloads still surface `invalid_payload` retry feedback rather than silently pausing.

## Edge cases and failure paths
- Canonical `route_fields.reason = null` with stray legacy top-level `reason`.
- Canonical `route_fields = {}` with stray legacy top-level `question`.
- Rendered-provider retry feedback after canonical invalid question route.

## Known gaps
- This test slice does not add new coverage for simplified provider-schema fallback size limits.
- This test slice does not broaden compile-report or static-graph assertions because those behaviors are out of this phase's active test scope.

## Stabilization notes
- All added tests are deterministic unit/contract tests with inline JSON payloads and existing in-memory stubs; no timing or network dependencies were introduced.
