# ADR 011: Validation Architecture

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `8. Workflow Compilation And Validation Model`

Final decision:
- Validation happens at workflow-definition time through the strict workflow machinery.
- The validator enforces state shape, explicit entry, transitions, session declarations, artifact ownership, and exact handler signatures.
- Validation errors are boundary errors, not runtime surprises.
- The same strict rules apply to repo-root workflows and package-local workflows.

Rejected shape:
- no permissive validator for malformed workflows
- no post-load normalization path
- no delayed validation during execution
