# ADR 004: Artifact Registry And Resolution

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `6. Artifact Registry And Required-Artifact Enforcement`

Final decision:
- Workflow-declared artifacts compile into one registry with uniqueness and dependency validation.
- Required-artifact existence is asserted before step execution.
- Resolved artifact handles are passed into handlers as part of the strict contract.
- Workflow-specific naming conventions remain in workflow code, not in the generic runtime.

Rejected shape:
- no ad hoc file-path resolution inside handlers
- no best-effort required-artifact warnings
- no runtime-owned artifact conventions for one workflow
