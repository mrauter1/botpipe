# Test Strategy

- Task ID: recursive-framework-evolution-20260423t120129-bootstrap
- Pair: test
- Phase ID: session-id-schema-cleanup
- Phase Directory Key: session-id-schema-cleanup
- Phase Title: Canonicalize Session Continuation State
- Scope: phase-local producer artifact

## Behaviors covered

- Canonical payload helpers: placeholder creation, roundtrip persistence, missing-provider fallback, and no legacy aliasing in `tests/runtime/test_compatibility_runtime.py`.
- Filesystem session-store integration: canonical payloads reload through a fresh `FilesystemSessionStore`, and legacy `thread_id`-only payloads are treated as non-resumable and rewritten canonically on the next open.
- Autoloop-v1 parity: raw logs emit `session_id=` instead of legacy naming, and resumed clarification flows still persist through `session_id` and `provider_metadata`.

## Preserved invariants checked

- `SessionBinding.session_id` remains the runtime continuation handle.
- `provider_metadata` round-trips unchanged through helper functions and the concrete filesystem store.
- Adjacent engine/store/context/package-CLI regression suites remain green with the out-of-scope recursive-wrapper test excluded.

## Edge cases and failure paths

- Existing payload without `provider` uses the configured default provider.
- Existing payload with only legacy continuation data does not resume implicitly.
- Source scan guards the active runtime/parity files against reintroducing the legacy field name.

## Stabilization

- All tests use `tmp_path`-backed local filesystem fixtures and deterministic JSON assertions.
- No network, clock-sensitive ordering, or subprocess timing dependencies were introduced.

## Known gaps

- Docs and repo-wide strictness scans remain for later scoped phases.
- The recursive-wrapper package-only test remains intentionally excluded here because that cleanup belongs to a later phase.
