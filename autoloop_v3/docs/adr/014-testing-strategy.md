# ADR 014: Testing Strategy

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `15. Parity-Testing Strategy`

Final decision:
- The proof suite is layered: unit tests, engine-contract tests, generic-runtime integration tests, and legacy parity tests.
- No-compat proofs are first-class tests, not documentation claims.
- A toy workflow with unrelated step names proves runtime agnosticism.
- Autoloop-v1 parity tests pin workspace layout, events, checkpoints, clarification persistence, blocked/failed flows, and session-sharing behavior.

Rejected shape:
- no parity strategy that relies only on unit coverage
- no oversized end-to-end suite without focused contract tests
- no documentation-only proof of strictness or parity
