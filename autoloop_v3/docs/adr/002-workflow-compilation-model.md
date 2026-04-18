# ADR 002: Workflow Compilation Model

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `2. Canonical Public Surface` and `8. Validation And Compilation Model`

Final decision:
- The strict authoring surface exposes only the canonical workflow symbols plus `Event`, `Outcome`, `Checkpoint`, and `ResolvedArtifacts`.
- Workflows validate strictly and compile deterministically into an immutable model before execution.
- The compiler does not normalize malformed declarations or widen the public surface with internal helpers.
- Internal modules may still use engine/compiler internals without making them part of the authoring contract.

Rejected shape:
- no broad root export surface for engine/compiler internals
- no permissive compilation or hidden normalization path
- no runtime-only interpretation of raw workflow classes
