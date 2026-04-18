# ADR 011: Validation Architecture

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `8. Validation And Compilation Model`

Final decision:
- Validation happens at workflow definition time and enforces the strict shape before execution.
- The validator checks state shape, explicit entry, transitions, sessions, artifacts, and handler signatures.
- Validation errors are boundary errors, not late runtime surprises.
- The same rules apply to repo-root workflows and package-local workflows.

Rejected shape:
- no permissive validator for malformed workflows
- no delayed validation during execution
- no post-load compatibility normalization path
