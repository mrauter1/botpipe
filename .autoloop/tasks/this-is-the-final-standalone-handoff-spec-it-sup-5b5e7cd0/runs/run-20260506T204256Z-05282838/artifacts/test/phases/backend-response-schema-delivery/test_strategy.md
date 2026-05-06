# Test Strategy

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: test
- Phase ID: backend-response-schema-delivery
- Phase Directory Key: backend-response-schema-delivery
- Phase Title: Backend Schema Delivery
- Scope: phase-local producer artifact

## Coverage map

- AC-1 native schema delivery:
  - `tests/runtime/test_provider_backends.py::test_codex_backend_delivers_full_response_schema_via_output_schema_file`
  - Confirms Codex start turns receive `turn.response_schema` via `--output-schema` and records `native_full`.
- AC-2 simplified schema delivery:
  - `tests/runtime/test_provider_backends.py::test_codex_backend_records_simplified_schema_delivery`
  - Confirms a distinct simplified schema payload is what the backend-facing schema file contains and records `native_simplified`.
- AC-3 unsupported-backend fallback:
  - `tests/runtime/test_provider_backends.py::test_codex_backend_records_prompt_only_fallback_when_resume_lacks_output_schema`
  - `tests/runtime/test_provider_backends.py::test_claude_backend_records_prompt_only_fallback_for_response_schema`
  - Confirms prompt-only fallback omits `--output-schema` and records explicit fallback reasons.
- AC-4 documentation / invariant coverage:
  - `tests/test_architecture_baseline_docs.py -k "authoring or controlroutes or route"`
  - Checks the authoritative docs still parse and remain consistent after adding explicit delivery-mode language.

## Preserved invariants checked

- Backend fallback changes generation guidance only; engine-side route legality and schema validation remain strict.
- Delivery-mode observability stays on `metadata["structured_output"]`.
- No new backend abstraction layer or transport redesign is required for coverage.

## Edge cases and failure paths

- Resume-session Codex path without native schema support stays prompt-only.
- Claude path stays prompt-only even when a response schema is present.
- Simplified-schema regression uses a schema payload distinct from the full-schema test so content mismatches cannot hide behind the delivery-mode flag alone.

## Stability notes

- Tests are deterministic and fully stubbed; they do not invoke live provider CLIs or the network.
- Capability probing is monkeypatched per test to avoid host-environment drift.

## Known gaps

- No test currently simulates a future Codex resume surface that genuinely supports `--output-schema`; current product decisions explicitly treat resume as prompt-only.
