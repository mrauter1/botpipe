# Test Author ↔ Test Auditor Feedback

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: test
- Phase ID: backend-response-schema-delivery
- Phase Directory Key: backend-response-schema-delivery
- Phase Title: Backend Schema Delivery
- Scope: phase-local authoritative verifier artifact

- Added focused coverage hardening in `tests/runtime/test_provider_backends.py` so the simplified-schema path now asserts the backend-facing `--output-schema` file contains the distinct simplified schema payload, not just the `native_simplified` metadata flag.
