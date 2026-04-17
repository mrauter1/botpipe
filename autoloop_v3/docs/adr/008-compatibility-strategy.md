# ADR 008: Compatibility Strategy For Legacy And Workspace Drift

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `3. Compatibility Removal Strategy`

Final decision:
- The workflow core is strict and has no compatibility layer.
- Workflow modules must import the canonical symbols they actually use.
- Legacy-equivalent Autoloop-v1 behavior is preserved through migrated workflow code plus workflow-owned harness helpers.
- Persisted runtime compatibility is limited to targeted data-shape readers such as legacy session payload fields and status consumers.

Rejected shape:
- no hidden compatibility boundary in the compiler or loader
- no authoring drift preserved as a public contract
- no runtime-core branch that knows workflow-specific legacy behavior
