# ADR 002: Workflow Compilation Model

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `8. Workflow Compilation And Validation Model`

Final decision:
- Workflows are validated strictly at definition time and compiled only when already canonical.
- Compilation produces an immutable compiled workflow model used directly by the engine.
- The compiler does not normalize malformed declarations or rewrite workflow modules.
- Deterministic compilation is part of the public contract.

Rejected shape:
- no compile-time normalization boundary
- no permissive compilation of malformed workflows
- no runtime-only validation strategy
