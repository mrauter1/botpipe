# ADR 014: Testing Strategy

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `18. Testing Strategy`

Final decision:
- Proof is layered across unit, contract, runtime integration, strictness, workflow, toy-workflow, and parity tests.
- No-compat claims are enforced by tests instead of documentation alone.
- The doc baseline freezes the strict kernel, optional extension seam, tiny stdlib, and narrow compatibility scope.
- Autoloop-v1 parity tests pin the workflow-owned operational artifacts and retained compatibility surface explicitly.

Rejected shape:
- no documentation-only proof of architecture
- no end-to-end-only test strategy
- no parity strategy that skips focused contract coverage
