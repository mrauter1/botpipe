# ADR 008: Compatibility Strategy For Legacy And Workspace Drift

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `3. Compatibility Removal Strategy`

Final decision:
- The workflow authoring surface is strict and has no compatibility layer.
- Removed authoring aliases, injected names, and permissive adaptation paths are not preserved under new names.
- Retained compatibility is narrow and operational only: persisted runtime data, status readers where parity requires them, and config discovery from legacy `superloop.*` files.
- Autoloop-v1 parity remains workflow-owned rather than hidden in the runtime core.

Rejected shape:
- no hidden normalization boundary in compiler or loader
- no authoring alias layer
- no workflow-specific compatibility policy in the generic runtime
